import json
import os
import subprocess
from pathlib import Path


def run_command(command, cwd=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n\n"
            + " ".join(str(x) for x in command)
            + "\n\nSTDOUT:\n"
            + result.stdout
            + "\n\nSTDERR:\n"
            + result.stderr
        )
    return result


def make_local_builder_code():
    return r'''
import bpy
import math


def make_mat(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


skin = make_mat("skin_soft", (1.0, 0.72, 0.58, 1.0))
hair = make_mat("hair_blonde", (1.0, 0.82, 0.18, 1.0))
line = make_mat("warm_line", (0.45, 0.22, 0.09, 1.0))
white = make_mat("cloth_white", (0.9, 0.86, 0.78, 1.0))
yellow = make_mat("eye_gold", (1.0, 0.82, 0.1, 1.0))


def add_uv(name, loc, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj


def add_curve(name, points, bevel, mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = bevel
    curve.bevel_resolution = 4
    spl = curve.splines.new("POLY")
    spl.points.add(len(points) - 1)
    for p, co in zip(spl.points, points):
        p.co = (co[0], co[1], co[2], 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def create_reference_plane(view_name, image_path, loc, rot, size=1.45):
    if not image_path:
        return None
    try:
        img = bpy.data.images.load(image_path)
    except Exception:
        return None

    mat = bpy.data.materials.new("ref_" + view_name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Alpha"].default_value = 0.72
    mat.blend_method = "BLEND"

    aspect = img.size[0] / max(img.size[1], 1)
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc, rotation=rot)
    plane = bpy.context.object
    plane.name = "reference_" + view_name
    plane.scale.x = aspect
    plane.data.materials.append(mat)
    return plane


for item in REFERENCE_IMAGES:
    view = item.get("view")
    path = item.get("path")
    if view == "front":
        create_reference_plane(view, path, (0, -2.2, 1.2), (math.radians(90), 0, 0))
    elif view == "back":
        create_reference_plane(view, path, (0, 2.2, 1.2), (math.radians(90), 0, math.radians(180)))
    elif view == "left":
        create_reference_plane(view, path, (-2.2, 0, 1.2), (math.radians(90), 0, math.radians(90)))
    elif view == "right":
        create_reference_plane(view, path, (2.2, 0, 1.2), (math.radians(90), 0, math.radians(-90)))
    elif view == "top":
        create_reference_plane(view, path, (0, 0, 2.8), (0, 0, 0), 1.25)
    elif view == "bottom":
        create_reference_plane(view, path, (0, 0, -0.05), (0, 0, 0), 1.25)


add_uv("main_head_from_multiview_plan", (0, 0, 1.25), (0.78, 0.56, 0.9), skin)
add_uv("front_face_volume", (0, -0.22, 1.25), (0.66, 0.18, 0.62), skin)
add_uv("left_eye", (-0.22, -0.42, 1.38), (0.075, 0.035, 0.075), yellow)
add_uv("right_eye", (0.22, -0.42, 1.38), (0.075, 0.035, 0.075), yellow)
add_curve("front_mouth_or_expression", [(-0.26, -0.55, 1.12), (-0.08, -0.58, 1.04), (0.08, -0.58, 1.04), (0.26, -0.55, 1.12)], 0.018, line)

for i in range(13):
    x = -0.62 + i * 0.105
    z1 = 2.02 - abs(i - 6) * 0.025
    z2 = 1.15 + (i % 4) * 0.08
    add_curve("front_hair_lock_%02d" % i, [(x, -0.5, z1), (x * 0.6, -0.56, 1.65), (x * 0.85, -0.50, z2)], 0.035, hair)

for i in range(10):
    x = -0.82 if i < 5 else 0.82
    side = -1 if i < 5 else 1
    z = 1.9 - (i % 5) * 0.17
    add_curve("side_hair_%02d" % i, [(x, -0.12, z), (x + side * 0.18, -0.05, z - 0.22), (x + side * 0.08, -0.02, z - 0.45)], 0.04, hair)

body = add_uv("upper_body_simple", (0, 0.02, 0.35), (0.58, 0.34, 0.38), white)
body.rotation_euler[0] = math.radians(8)

for obj in bpy.context.scene.objects:
    if obj.type == "MESH":
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            bpy.ops.object.shade_smooth()
        except Exception:
            pass
        obj.select_set(False)

bpy.ops.object.light_add(type="AREA", location=(0, -3.5, 4.2))
light = bpy.context.object
light.name = "Key_Light"
light.data.energy = 650
light.data.size = 4

bpy.ops.object.camera_add(location=(0, -4.4, 1.55), rotation=(math.radians(76), 0, 0))
bpy.context.scene.camera = bpy.context.object
'''


def make_ai_builder_code(user_request, analysis):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return make_local_builder_code()

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = f"""
Write Blender Python code to create an editable 3D model from this multi-view analysis.
Return ONLY executable Python code. No markdown.

Important:
- The script will run after REFERENCE_IMAGES has been defined.
- Use every uploaded reference view as modeling guidance.
- Create reference image planes for all views or keep existing reference planes if they are already created.
- Do not use TripoSR.
- Do not add a black flat cylinder, base, or pedestal.
- Keep the model upright, centered, and with a level camera.
- Prefer simple clean Blender geometry: mesh primitives, bevels, curves, materials, lights, camera.
- If the image is an anime/cartoon character, create a stylized bust or relief-like 3D approximation.
- Save nothing yourself; the runner saves the file.

User request:
{user_request}

Analysis JSON:
{json.dumps(analysis, ensure_ascii=False, indent=2)}
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


def make_runner_script(script_path, blend_path, user_request, analysis, copied_images, open_existing=None):
    reference_images = [
        {"view": view, "path": str(path)}
        for view, path in copied_images.items()
        if path and Path(path).exists()
    ]
    builder_code = make_ai_builder_code(user_request, analysis)

    if open_existing:
        opener = f'bpy.ops.wm.open_mainfile(filepath=r"{open_existing}")'
    else:
        opener = 'bpy.ops.object.select_all(action="SELECT")\nbpy.ops.object.delete()'

    script_path.write_text(
        f"""
import bpy
import json
import math
import os
from mathutils import Vector

REFERENCE_IMAGES = {json.dumps(reference_images, ensure_ascii=False)}
ANALYSIS = {json.dumps(analysis, ensure_ascii=False)}

{opener}

def remove_forbidden_artifacts():
    for obj in list(bpy.context.scene.objects):
        name = obj.name.lower()
        material_names = [mat.name.lower() for mat in getattr(obj.data, "materials", []) if mat]
        if name.startswith("base") or "base_dark" in material_names or "pedestal" in name:
            bpy.data.objects.remove(obj, do_unlink=True)

def normalize_scene():
    meshes = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.name.lower().startswith("reference_")
    ]
    if not meshes:
        return
    for obj in meshes:
        obj.rotation_euler = (0.0, 0.0, 0.0)
    corners = []
    for obj in meshes:
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    if not corners:
        return
    min_x = min(v.x for v in corners)
    max_x = max(v.x for v in corners)
    min_y = min(v.y for v in corners)
    max_y = max(v.y for v in corners)
    min_z = min(v.z for v in corners)
    offset = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    for obj in meshes:
        obj.location += offset

remove_forbidden_artifacts()

{builder_code}

remove_forbidden_artifacts()
normalize_scene()

os.makedirs(os.path.dirname(r"{blend_path}"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=r"{blend_path}")
""",
        encoding="utf-8",
    )
    return builder_code


def build_model_with_blender(blender_exe, result_dir, user_request, analysis, copied_images, output_name="result.blend", open_existing=None):
    result_dir = Path(result_dir)
    blend_path = result_dir / output_name
    script_path = result_dir / "blender_multiview_builder.py"
    user_code = make_runner_script(script_path, blend_path, user_request, analysis, copied_images, open_existing=open_existing)
    run_command([blender_exe, "--background", "--python", str(script_path)])
    return blend_path, script_path, user_code
