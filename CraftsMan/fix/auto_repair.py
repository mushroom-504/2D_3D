import os
from pathlib import Path


MAX_REPAIR_ATTEMPTS = 3


def read_error_report(report_path):
    path = Path(report_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def analyze_error_message(error_text, model_check=None):
    text = str(error_text or "")
    lower = text.lower()
    problems = list((model_check or {}).get("problems", []))
    problem_text = "\n".join(problems).lower()
    combined = lower + "\n" + problem_text

    categories = []
    actions = []

    if "no such file" in combined or "not found" in combined or "cannot find" in combined:
        categories.append("missing_file_or_path")
        actions.append("check paths and search for generated model files")
    if "cuda" in combined or "out of memory" in combined or "memory" in combined:
        categories.append("memory_or_device")
        actions.append("retry with lower resolution or CPU-safe settings")
    if "external multi-view" in combined or "mast3r" in combined:
        categories.append("multiview_backend")
        actions.append("retry multi-view once, then fall back to TripoSR")
    if "obj file not found" in combined or "no obj/glb" in combined:
        categories.append("missing_mesh_output")
        actions.append("search recursively for obj/glb/gltf/ply output")
    if "blender" in combined or "python traceback" in combined or "script" in combined:
        categories.append("blender_script")
        actions.append("regenerate Blender script with the error included")
    if "empty" in combined:
        categories.append("empty_model")
        actions.append("re-import source mesh and preserve all mesh objects")
    if "tilted" in combined or "upright" in combined or "center" in combined:
        categories.append("pose_problem")
        actions.append("straighten, center, and place bottom on ground")
    if "black base" in combined or "cylinder" in combined or "pedestal" in combined:
        categories.append("unwanted_base")
        actions.append("remove base, pedestal, black flat cylinder, and Base_Dark materials")
    if "material" in combined:
        categories.append("material_problem")
        actions.append("assign safe default materials to mesh objects without materials")

    if not categories:
        categories.append("unknown")
        actions.append("retry with conservative defaults and keep more diagnostic logs")

    return {
        "categories": categories,
        "actions": actions,
        "raw_error": text[-4000:],
        "model_problems": problems,
    }


def build_repair_intent(base_intent, repair_report, model_check=None):
    model_check = model_check or {}
    lines = [
        base_intent or "Repair the generated Blender model.",
        "",
        "Automatic repair report:",
        f"Categories: {', '.join(repair_report.get('categories', []))}",
        "Actions:",
    ]
    for action in repair_report.get("actions", []):
        lines.append(f"- {action}")

    if model_check.get("problems"):
        lines.extend(["", "Model checker problems:"])
        for problem in model_check["problems"]:
            lines.append(f"- {problem}")

    lines.extend(
        [
            "",
            "Repair requirements:",
            "- Do not delete the main imported model.",
            "- If the model is empty, preserve and re-import visible mesh objects.",
            "- Remove unwanted black bases, flat cylinders, pedestal objects, Base objects, and Base_Dark materials.",
            "- Straighten the model, center it, and place its bottom on the ground plane.",
            "- Add simple safe materials to mesh objects that have no material.",
            "- Export result.blend, model.glb, model.fbx, model.stl, and preview.png again.",
        ]
    )
    return "\n".join(lines)


def make_rule_based_code(intent):
    lower = (intent or "").lower()
    code = """
import bpy

def apply_request():
    for obj in list(bpy.context.scene.objects):
        name = obj.name.lower()
        mat_names = [mat.name.lower() for mat in getattr(obj.data, "materials", []) if mat] if hasattr(obj, "data") else []
        if obj.type == "MESH" and (
            name.startswith("base")
            or "pedestal" in name
            or ("cylinder" in name and obj.dimensions.z < max(obj.dimensions.x, obj.dimensions.y) * 0.25)
            or "base_dark" in mat_names
        ):
            bpy.data.objects.remove(obj, do_unlink=True)

    default_mat = bpy.data.materials.get("Auto_Default_Material") or bpy.data.materials.new("Auto_Default_Material")
    default_mat.diffuse_color = (0.82, 0.78, 0.68, 1.0)

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    for obj in mesh_objects:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        if not obj.data.materials:
            obj.data.materials.append(default_mat)
        try:
            bpy.ops.object.shade_smooth()
        except Exception:
            pass
        if not obj.modifiers.get("Weighted_Normals"):
            mod = obj.modifiers.new("Weighted_Normals", "WEIGHTED_NORMAL")
            mod.keep_sharp = True
        obj.select_set(False)
"""

    if "metal" in lower or "金属" in (intent or ""):
        code += """
    metal = bpy.data.materials.get("Metal_Material") or bpy.data.materials.new("Metal_Material")
    metal.use_nodes = True
    bsdf = metal.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.28
        bsdf.inputs["Base Color"].default_value = (0.8, 0.75, 0.65, 1)
    for obj in mesh_objects:
        obj.data.materials.clear()
        obj.data.materials.append(metal)
"""

    code += """
    if not any(obj.type == "LIGHT" for obj in bpy.context.scene.objects):
        bpy.ops.object.light_add(type="AREA", location=(3, -5, 4))
        light = bpy.context.object
        light.name = "Softbox"
        light.data.energy = 500
        light.data.size = 5

apply_request()
"""
    return code


def make_ai_code(intent, error_message=None):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return make_rule_based_code(intent)

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    repair_text = ""
    if error_message:
        repair_text = f"\nThe previous Blender script failed with this error:\n{error_message}\nFix it."

    prompt = f"""
You are controlling Blender with Python.
Write ONLY executable Python code. Do not use markdown.
Do not delete the imported model unless explicitly required.

User request and plan:
{intent}

Requirements:
- Use bpy only.
- Add lights and camera if useful.
- Improve clarity with shade_smooth and weighted normals.
- If the user asks for material, create Blender materials.
- Use named view references as modeling guidance.
- Do not create a base, pedestal, or black flat cylinder unless the user explicitly asks for one.
- Remove any object named Base or using a Base_Dark material.
- Remove unwanted black flat cylinders and display pedestals.
- Keep the model upright, centered, and level.
- Add a simple default material to mesh objects that have no material.
- Do not access network.
- Do not use external files.
{repair_text}
"""

    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_CODE_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "Return only valid Blender Python code."},
            {"role": "user", "content": prompt},
        ],
    )
    code = response.choices[0].message.content.strip()
    return code.replace("```python", "").replace("```", "").strip()
