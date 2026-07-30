from three_view_agent import (
    analyze_three_view_request,
    build_blender_intent,
    save_analysis,
)
from config_loader import get_section


BACKEND_AUTO = "Auto"
BACKEND_CRAFTSMAN = "CraftsMan 远程服务"
BACKEND_TRIPOSR = "TripoSR"
BACKEND_TRIPOSR_ENHANCED = "TripoSR Enhanced"
BACKEND_EXTERNAL_MULTIVIEW = "External Multi-View"
EXTERNAL_MULTIVIEW_ENABLED = bool(
    get_section("external_multiview").get("enabled", False)
)

VIEW_ORDER = ["front", "back", "left", "right", "top", "bottom"]

DIMENSION_KEYWORDS = [
    "尺寸",
    "标注",
    "长度",
    "宽度",
    "高度",
    "厚度",
    "直径",
    "半径",
    "毫米",
    "厘米",
    "mm",
    "cm",
]

STYLE_IMAGE_KEYWORDS = [
    "动漫",
    "二次元",
    "卡通",
    "草图",
    "手绘",
    "插画",
    "头像",
    "挂件",
    "角色",
    "人物",
    "立绘",
    "玩偶",
    "娃娃",
    "发饰",
    "q版",
    "可爱",
    "cartoon",
    "anime",
    "sketch",
    "illustration",
    "character",
    "doll",
    "figure",
    "chibi",
]

REAL_MULTIVIEW_KEYWORDS = [
    "真实照片",
    "实物",
    "摄影",
    "多视图重建",
    "照片重建",
    "扫描",
    "real photo",
    "photogrammetry",
    "scan",
    "multi-view reconstruction",
]

TRIPOSR_ENHANCED_KEYWORDS = [
    "TripoSR Enhanced",
    "triposr enhanced",
    "TripoSR 精修",
    "不要扁平",
    "加厚",
    "厚度修正",
    "圆润",
]


def analyze_request(intent, image_paths_for_agent):
    return analyze_three_view_request(intent, image_paths_for_agent)


def _existing_views(image_paths_for_agent):
    return [
        view
        for view in VIEW_ORDER
        if (image_paths_for_agent or {}).get(view)
    ]


def _contains_any(text, keywords):
    lower = (text or "").lower()
    return any(keyword.lower() in lower for keyword in keywords)


def create_modeling_plan(
    intent,
    image_paths_for_agent,
    analysis=None,
    requested_backend=BACKEND_AUTO,
):
    available_views = _existing_views(image_paths_for_agent)
    reference_views = [view for view in available_views if view != "front"]
    has_dimensions = bool((analysis or {}).get("dimensions")) or _contains_any(
        intent, DIMENSION_KEYWORDS
    )
    looks_stylized = _contains_any(intent, STYLE_IMAGE_KEYWORDS)
    explicitly_real_multiview = _contains_any(
        intent, REAL_MULTIVIEW_KEYWORDS
    )
    reasons = []
    warnings = []

    if requested_backend and requested_backend != BACKEND_AUTO:
        if (
            requested_backend == BACKEND_EXTERNAL_MULTIVIEW
            and not EXTERNAL_MULTIVIEW_ENABLED
        ):
            backend = BACKEND_CRAFTSMAN if reference_views else BACKEND_TRIPOSR
            warnings.append(
                "External Multi-View is disabled. The request was routed to "
                f"{backend} instead."
            )
            reasons.append(
                "The optional MASt3R backend is disabled in config.json."
            )
        else:
            backend = requested_backend
            reasons.append(f"User selected backend: {requested_backend}.")
    elif (
        reference_views
        and explicitly_real_multiview
        and EXTERNAL_MULTIVIEW_ENABLED
    ):
        backend = BACKEND_EXTERNAL_MULTIVIEW
        reasons.append(
            "Multiple real-photo views were requested, so Auto selected the "
            "external reconstruction backend."
        )
    elif reference_views:
        backend = BACKEND_CRAFTSMAN
        reasons.append(
            "Reference views are available, so Auto selected CraftsMan to send "
            "the main image, reference views, and text in one remote request."
        )
        if explicitly_real_multiview and not EXTERNAL_MULTIVIEW_ENABLED:
            warnings.append(
                "External Multi-View is disabled, so Auto selected CraftsMan. "
                "This optional MASt3R backend can be enabled after its source "
                "and Python environment are installed."
            )
    else:
        backend = BACKEND_TRIPOSR
        reasons.append(
            "Only one primary view is available, so Auto selected TripoSR for "
            "a stable, fast base mesh."
        )

    if "front" not in available_views:
        warnings.append(
            "No front image is available. Generation requires a main image."
        )
    if not reference_views:
        warnings.append(
            "No reference views were uploaded. Back/side/top details must be inferred."
        )
    if backend == BACKEND_TRIPOSR and reference_views:
        warnings.append(
            "TripoSR only uses the main image for base-model generation. "
            "Reference images are used only by visual analysis and Blender repair."
        )
    if backend == BACKEND_CRAFTSMAN and not reference_views:
        warnings.append(
            "CraftsMan received only the main image. Add at least one reference "
            "view to use multi-view request mode."
        )
    if has_dimensions:
        reasons.append(
            "Dimension words or extracted dimensions were found, so Blender "
            "should preserve typed/measured proportions."
        )

    backend_step = (
        "Run TripoSR with the main image only to create one base mesh."
        if backend == BACKEND_TRIPOSR
        else f"Run {backend} once to create one base mesh."
    )
    steps = [
        "Copy all uploaded images into the result folder and keep their view names.",
        "Analyze the natural-language request and all available views.",
        backend_step,
        "Import the single generated mesh into Blender.",
        "Remove black bases, display cylinders, and helper artifacts.",
        "Straighten, center, and ground the model.",
        "Use reference views and the request to correct visible details.",
        "Export result.blend, model.glb, model.fbx, model.stl, and preview.png.",
        "Run model checks after export.",
    ]
    quality_checks = [
        "model file exists",
        "model is not empty",
        "model is upright and centered",
        "no black base or unwanted flat cylinder",
        "Blender can open the file",
        "materials are present when expected",
        "reference views were included in the Blender modification prompt",
        "no per-view meshes were generated or joined",
    ]

    return {
        "backend": backend,
        "requested_backend": requested_backend or BACKEND_AUTO,
        "available_views": available_views,
        "reference_views": reference_views,
        "has_dimensions": has_dimensions,
        "looks_stylized_or_sketch": looks_stylized,
        "explicitly_real_multiview": explicitly_real_multiview,
        "reasons": reasons,
        "warnings": warnings,
        "steps": steps,
        "quality_checks": quality_checks,
    }


def build_modeling_intent(intent, analysis, copied_refs):
    return build_blender_intent(intent, analysis, copied_refs)


def save_agent_analysis(result_dir, analysis):
    return save_analysis(result_dir, analysis)
