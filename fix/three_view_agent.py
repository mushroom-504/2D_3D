import base64
import json
import mimetypes
import os
import re
from pathlib import Path

from config_loader import get_section

VIEW_LABELS = {
    "front": "front view",
    "back": "back view",
    "top": "top view",
    "bottom": "bottom view",
    "left": "left view",
    "right": "right view",
}

DIMENSION_PATTERNS = [
    r"(?P<name>length|width|height|thickness|diameter|radius|len|w|h)\s*[:=]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m)?",
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m)\s*(?P<name>length|width|height|thickness|diameter|radius|len|w|h)?",
    r"(?P<name>[\u4e00-\u9fff]{1,4})\s*[:\uff1a=]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m|\u6beb\u7c73|\u5398\u7c73|\u7c73)?",
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m|\u6beb\u7c73|\u5398\u7c73|\u7c73)\s*(?P<name>[\u4e00-\u9fff]{0,4})",
]


def read_image_as_data_url(path):
    image_path = Path(path)
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{data}"


def extract_dimensions_from_text(text):
    dimensions = []
    seen = set()

    for pattern in DIMENSION_PATTERNS:
        for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
            item = match.groupdict()
            name = (item.get("name") or "dimension").strip() or "dimension"
            value = item.get("value")
            unit = item.get("unit") or "mm"
            key = (name.lower(), value, unit.lower())

            if key in seen:
                continue

            seen.add(key)
            dimensions.append(
                {
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "source": "user_text",
                    "uncertain": False,
                }
            )

    return dimensions


def existing_images(image_paths):
    result = {}
    for view, path in (image_paths or {}).items():
        if path and Path(path).exists():
            result[view] = str(Path(path))
    return result


def local_analyze(user_request, image_paths):
    images = existing_images(image_paths)
    dimensions = extract_dimensions_from_text(user_request)

    return {
        "mode": "local_rules",
        "summary": user_request or "Generate a 3D model from all provided views.",
        "available_views": list(images.keys()),
        "dimensions": dimensions,
        "view_analysis": {
            view: {
                "label": VIEW_LABELS.get(view, view),
                "image": path,
                "note": (
                    "The image is available and will be saved as a named reference. "
                    "Rule mode cannot compare pixels or read drawn annotations."
                ),
            }
            for view, path in images.items()
        },
        "modeling_plan": [
            "Use the front image as the TripoSR base mesh source.",
            "Use every other uploaded view as a named reference, not as decoration.",
            "If front and back views differ, preserve the front-side details and add/modify the opposite-side visible details in Blender.",
            "Do not add any automatic black base cylinder or display pedestal.",
            "Straighten the imported model, center it, put its bottom on the ground plane, and use a front-facing camera.",
            "Use dimensions typed in the natural language request when available.",
        ],
        "blender_modification_goals": [
            "Remove generated helper artifacts such as Base or Base_Dark.",
            "Preserve the generated mesh, then correct visible proportions using all named views.",
            "Apply smoothing, weighted normals, bevels, materials, lights, and a level camera.",
        ],
        "uncertainty": [
            "RULE MODE: image contents are not visually understood or compared.",
            "Configure a vision-capable API key/model to inspect differences and image annotations.",
        ],
    }


def get_vision_api_settings():
    config = get_section("vision_api")
    key_env = str(config.get("api_key_env", "OPENAI_API_KEY"))
    api_key = os.environ.get(key_env, "").strip() or os.environ.get(
        "OPENAI_API_KEY", ""
    ).strip()
    base_env = str(config.get("base_url_env", "OPENAI_API_BASE"))
    base_url = os.environ.get(base_env, "").strip()
    model_env = str(config.get("model_env", "OPENAI_VISION_MODEL"))
    fallback_env = str(config.get("fallback_model_env", "AIDER_MODEL"))
    model = os.environ.get(model_env, "").strip() or os.environ.get(
        fallback_env, ""
    ).strip()
    if "/" in model:
        model = model.split("/", 1)[1]
    return {
        "enabled": bool(config.get("enabled", True)),
        "api_key": api_key,
        "base_url": base_url,
        "model": model or "gpt-4o",
        "key_env": key_env,
    }


def get_analysis_capability():
    settings = get_vision_api_settings()
    if settings["enabled"] and settings["api_key"]:
        return {
            "mode": "vision_api",
            "label": f"视觉模型模式：{settings['model']}",
            "can_see_images": True,
        }
    return {
        "mode": "local_rules",
        "label": "规则模式：不具备图片内容理解能力",
        "can_see_images": False,
    }


def openai_vision_analyze(user_request, image_paths):
    from openai import OpenAI

    settings = get_vision_api_settings()
    client_kwargs = {"api_key": settings["api_key"]}
    if settings["base_url"]:
        client_kwargs["base_url"] = settings["base_url"]
    client = OpenAI(**client_kwargs)
    content = [
        {
            "type": "text",
            "text": (
                "You are a multi-view 3D modeling assistant for Blender.\n"
                "The user may upload front, back, top, bottom, left, and right reference images.\n"
                "You MUST compare all uploaded images. Do not assume front and back are identical.\n"
                "If two views are different, explicitly describe the difference and how Blender should represent it.\n"
                "Extract any marked dimensions, text annotations, holes, protrusions, recesses, color/material changes, asymmetry, and orientation.\n"
                "The output will be used to edit a Blender model, so be practical and concrete.\n"
                "Never ask Blender to add a black display base unless the user explicitly requested a base.\n"
                "Always ask Blender to straighten and center the model.\n"
                "Return ONLY valid JSON. Do not use markdown.\n\n"
                "Required JSON keys:\n"
                "summary, available_views, important_differences_between_views, dimensions, view_analysis, modeling_plan, blender_modification_goals, orientation_goals, structured_actions, uncertainty.\n\n"
                "Dimension object format:\n"
                "{name, value, unit, source_view, uncertain, note}\n\n"
                "structured_actions must be a JSON array. Allowed action types:\n"
                "cleanup_artifacts, center_ground, smooth, ensure_material,\n"
                "bevel {width, segments}, scale_axes {scale:[x,y,z]},\n"
                "add_primitive {primitive:cube|sphere|cylinder, name, location:[x,y,z], scale:[x,y,z], color:[r,g,b]}.\n"
                "Only add primitives when a missing simple part is clearly visible and its position is sufficiently certain.\n\n"
                f"User request:\n{user_request or ''}"
            ),
        }
    ]

    for view, path in existing_images(image_paths).items():
        content.append(
            {
                "type": "text",
                "text": f"The next image is the {VIEW_LABELS.get(view, view)}. Analyze this exact view and compare it with the other uploaded views.",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": read_image_as_data_url(path),
                    "detail": "high",
                },
            }
        )

    response = client.chat.completions.create(
        model=settings["model"],
        messages=[{"role": "user", "content": content}],
        temperature=0,
    )
    text = response.choices[0].message.content.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "mode": "openai_vision_raw_text",
            "raw_analysis": text,
            "dimensions": extract_dimensions_from_text(text + "\n" + (user_request or "")),
            "modeling_plan": [text],
            "uncertainty": ["The model returned text that was not valid JSON."],
        }


def analyze_three_view_request(user_request, image_paths):
    capability = get_analysis_capability()
    if capability["mode"] == "local_rules":
        return local_analyze(user_request, image_paths)

    try:
        analysis = openai_vision_analyze(user_request, image_paths)
        if isinstance(analysis, dict):
            analysis.setdefault("mode", "openai_vision")
            return analysis
    except Exception as exc:
        analysis = local_analyze(user_request, image_paths)
        analysis["mode"] = "local_rules_after_vision_error"
        analysis["vision_error"] = str(exc)
        return analysis

    return local_analyze(user_request, image_paths)


def save_analysis(result_dir, analysis):
    result_path = Path(result_dir) / "agent_analysis.json"
    result_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result_path


def build_blender_intent(user_request, analysis, copied_refs):
    lines = [
        "User natural language request:",
        user_request or "Generate a clear 3D model from every provided view.",
        "",
        "Multi-view and dimension analysis:",
        json.dumps(analysis, ensure_ascii=False, indent=2),
        "",
        "Copied reference images:",
    ]

    if copied_refs:
        for view, path in copied_refs.items():
            lines.append(f"- {view}: {Path(path).name}")
    else:
        lines.append("- No side reference images were copied.")

    lines.extend(
        [
            "",
            "Mandatory Blender execution rules:",
            "- Use every named reference view in the analysis. Front and back must not be treated as identical unless the analysis says they are identical.",
            "- Remove any black flat cylinder, Base object, Base_Dark material object, or automatic display pedestal.",
            "- Do not create a new base, pedestal, or black cylinder unless the user explicitly asks for one.",
            "- Straighten the imported model: reset object rotations, center the model at the origin, put the bottom on Z=0, and set a level front camera.",
            "- Keep the imported base mesh unless the user explicitly asks to replace it.",
            "- Use extracted dimensions as scale and proportion guidance.",
            "- Use front/back/top/bottom/left/right analysis to correct proportions and visible differences.",
            "- Add simple corrective geometry only when requested or strongly implied by the multi-view analysis.",
            "- Improve clarity with shade_smooth, weighted normals, bevels, materials, lights, and camera.",
            "- Save the final .blend file.",
        ]
    )

    return "\n".join(lines)
