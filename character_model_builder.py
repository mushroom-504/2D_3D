import json
import subprocess
from pathlib import Path


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"


def _detect_style(image_path, intent):
    text = (intent or "").lower()
    style = {
        "hair_color": "pink",
        "main_color": "pink",
        "cloth_color": "white",
        "accent_color": "black",
        "has_maid_cap": any(word in text for word in ["女仆", "maid", "帽", "发饰", "头饰"]),
        "has_bows": any(word in text for word in ["蝴蝶结", "bow", "丝带", "ribbon"]),
        "is_chibi": any(word in text for word in ["q版", "q 版", "chibi", "可爱", "卡通", "动漫"]),
    }

    try:
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        image.thumbnail((120, 120))
        pixels = list(image.getdata())
        pink = yellow = black = white = 0
        for r, g, b in pixels:
            if r > 180 and g < 170 and b > 130:
                pink += 1
            if r > 180 and g > 150 and b < 120:
                yellow += 1
            if r < 70 and g < 70 and b < 70:
                black += 1
            if r > 210 and g > 210 and b > 210:
                white += 1
        if yellow > pink:
            style["hair_color"] = "blonde"
            style["main_color"] = "yellow"
        if pink > max(yellow, 20):
            style["hair_color"] = "pink"
            style["main_color"] = "pink"
        if black > 80:
            style["accent_color"] = "black"
        if white > 200:
            style["cloth_color"] = "white"
    except Exception:
        pass

    if any(word in text for word in ["粉", "pink"]):
        style["hair_color"] = "pink"
        style["main_color"] = "pink"
    if any(word in text for word in ["金", "黄", "blonde", "yellow"]):
        style["hair_color"] = "blonde"
        style["main_color"] = "yellow"
    if any(word in text for word in ["女仆", "maid"]):
        style["has_maid_cap"] = True
        style["has_bows"] = True
    return style


def looks_like_stylized_character_image(image_path, intent=""):
    text = (intent or "").lower()
    if any(word in text for word in ["动漫", "二次元", "卡通", "人物", "角色", "q版", "q 版", "chibi", "anime", "character"]):
        return True

    try:
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        image.thumbnail((160, 160))
        pixels = list(image.getdata())
        if not pixels:
            return False

        pink = yellow = skin = dark_line = white = 0
        for r, g, b in pixels:
            if r > 150 and g < 190 and b > 120:
                pink += 1
            if r > 180 and g > 145 and b < 150:
                yellow += 1
            if r > 160 and 100 < g < 220 and 80 < b < 210:
                skin += 1
            if r < 120 and g < 120 and b < 120:
                dark_line += 1
            if r > 215 and g > 215 and b > 215:
                white += 1

        total = len(pixels)
        color_ratio = (pink + yellow + skin) / total
        line_ratio = dark_line / total
        white_ratio = white / total
        return color_ratio > 0.08 and line_ratio > 0.01 and white_ratio > 0.18
    except Exception:
        return False


def _write_blender_script(script_path, image_path, result_dir, style):
    script_path.write_text(
        f'''
import math
import os
import bpy
from mathutils import Vector

RESULT_DIR = r"{result_dir}"
IMAGE_PATH = r"{image_path}"
STYLE = {repr(style)}

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

def mat(name, color, roughness=0.55):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return material

skin = mat("warm_skin", (1.0, 0.78, 0.64, 1))
pink = mat("soft_pink", (1.0, 0.45, 0.68, 1))
blonde = mat("soft_blonde", (1.0, 0.82, 0.25, 1))
white = mat("warm_white", (0.96, 0.93, 0.88, 1))
black = mat("soft_black", (0.03, 0.025, 0.03, 1))
gray = mat("soft_gray", (0.55, 0.52, 0.55, 1))
hair_mat = blonde if STYLE.get("hair_color") == "blonde" else pink
main_mat = blonde if STYLE.get("main_color") == "yellow" else pink

def add_uv(name, loc, scale, material, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    return obj

def add_cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("soft_edges", "BEVEL")
    bevel.width = 0.08
    bevel.segments = 8
    obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    return obj

def add_cylinder(name, loc, radius, depth, material, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    return obj

def add_cone(name, loc, radius1, radius2, depth, material):
    bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=radius1, radius2=radius2, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    return obj

def add_bow(name, loc, material, scale=1.0):
    left = add_uv(name + "_left_loop", (loc[0] - 0.13 * scale, loc[1], loc[2]), (0.16 * scale, 0.05 * scale, 0.10 * scale), material)
    right = add_uv(name + "_right_loop", (loc[0] + 0.13 * scale, loc[1], loc[2]), (0.16 * scale, 0.05 * scale, 0.10 * scale), material)
    knot = add_uv(name + "_knot", loc, (0.07 * scale, 0.04 * scale, 0.07 * scale), material)
    return [left, right, knot]

def add_hair_clump(name, x, y, z, sx, sy, sz, rz=0.0):
    obj = add_uv(name, (x, y, z), (sx, sy, sz), hair_mat, 32, 16)
    obj.rotation_euler[2] = rz
    return obj

# Body proportions: Q/chibi shape, upright and centered.
head = add_uv("large_chibi_head", (0, 0, 2.55), (0.72, 0.58, 0.68), skin)
body = add_uv("small_body", (0, 0, 1.45), (0.42, 0.28, 0.55), white)
skirt = add_cone("layered_pink_skirt", (0, 0, 1.15), 0.65, 0.32, 0.42, main_mat)
apron = add_cube("front_white_apron", (0, -0.31, 1.18), (0.34, 0.035, 0.24), white)

for x in (-0.25, 0.25):
    add_cylinder("leg", (x, 0, 0.62), 0.095, 0.75, skin)
    shoe = add_uv("round_shoe", (x, -0.03, 0.18), (0.17, 0.24, 0.11), white)
    shoe.rotation_euler[0] = math.radians(90)
    add_bow("shoe_bow", (x, -0.24, 0.28), main_mat, 0.55)

for x, angle in [(-0.58, -18), (0.58, 18)]:
    arm = add_cylinder("puffy_sleeve_arm", (x, -0.02, 1.34), 0.085, 0.70, white)
    arm.rotation_euler[1] = math.radians(angle)
    hand = add_uv("small_hand", (x * 1.12, -0.03, 1.03), (0.105, 0.085, 0.095), skin)

# Hair volume and front bangs.
add_hair_clump("back_hair_mass", 0, 0.12, 2.65, 0.80, 0.52, 0.58)
for i, x in enumerate([-0.48, -0.25, 0, 0.25, 0.48]):
    add_hair_clump("front_bang_" + str(i + 1), x, -0.43, 2.63 - abs(x) * 0.15, 0.19, 0.10, 0.45, rz=x * -0.7)
for side, x in [("left", -0.82), ("right", 0.82)]:
    pony = add_hair_clump(side + "_side_ponytail", x, 0.02, 2.37, 0.26, 0.19, 0.62, rz=0.35 if x < 0 else -0.35)
    tail = add_hair_clump(side + "_curl_tail", x * 1.03, -0.03, 2.05, 0.20, 0.14, 0.38, rz=0.65 if x < 0 else -0.65)
    add_bow(side + "_hair_bow", (x * 0.88, -0.34, 2.58), main_mat, 0.7)

# Face: large stylized eyes, small mouth.
for x in (-0.27, 0.27):
    eye = add_uv("large_dark_eye", (x, -0.55, 2.55), (0.105, 0.035, 0.14), black, 32, 12)
    shine = add_uv("eye_highlight", (x - 0.03, -0.585, 2.60), (0.025, 0.01, 0.035), white, 16, 8)
mouth = add_uv("tiny_mouth", (0, -0.585, 2.35), (0.07, 0.014, 0.025), pink, 16, 8)

if STYLE.get("has_maid_cap", True):
    cap = add_uv("maid_headpiece", (0, -0.18, 3.20), (0.46, 0.15, 0.10), white, 32, 12)
    for x in [-0.32, -0.16, 0, 0.16, 0.32]:
        add_uv("headpiece_frill", (x, -0.28, 3.15), (0.08, 0.035, 0.09), white, 16, 8)

if STYLE.get("has_bows", True):
    add_bow("chest_bow", (0, -0.34, 1.65), main_mat, 0.85)

# Put the original 2D image behind the model as a named reference plane, not as a base.
try:
    bpy.ops.mesh.primitive_plane_add(size=2.2, location=(0, 0.78, 1.78), rotation=(math.radians(90), 0, 0))
    plane = bpy.context.object
    plane.name = "front_image_reference_plane"
    image = bpy.data.images.load(IMAGE_PATH)
    ref_mat = bpy.data.materials.new("front_reference_image")
    ref_mat.use_nodes = True
    nodes = ref_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    bsdf = nodes.get("Principled BSDF")
    ref_mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Alpha"].default_value = 0.35
    ref_mat.blend_method = "BLEND"
    plane.data.materials.append(ref_mat)
    plane.hide_render = True
except Exception as exc:
    print("Reference plane skipped:", exc)

# Clean orientation: no display base, centered, feet on ground.
mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
corners = []
for obj in mesh_objects:
    if obj.name == "front_image_reference_plane":
        continue
    for corner in obj.bound_box:
        corners.append(obj.matrix_world @ Vector(corner))
if corners:
    min_x = min(v.x for v in corners)
    max_x = max(v.x for v in corners)
    min_y = min(v.y for v in corners)
    max_y = max(v.y for v in corners)
    min_z = min(v.z for v in corners)
    offset = Vector((-(min_x + max_x) / 2, -(min_y + max_y) / 2, -min_z))
    for obj in mesh_objects:
        if obj.name != "front_image_reference_plane":
            obj.location += offset

bpy.ops.object.light_add(type="AREA", location=(0, -3.5, 5.0))
light = bpy.context.object
light.name = "large_softbox"
light.data.energy = 650
light.data.size = 5
bpy.ops.object.camera_add(location=(0, -5.2, 2.1), rotation=(math.radians(72), 0, 0))
bpy.context.scene.camera = bpy.context.object

os.makedirs(RESULT_DIR, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(RESULT_DIR, "result.blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(RESULT_DIR, "model.glb"), export_format="GLB")
try:
    bpy.ops.export_scene.fbx(filepath=os.path.join(RESULT_DIR, "model.fbx"))
except Exception as exc:
    print("FBX export failed:", exc)
try:
    bpy.ops.wm.stl_export(filepath=os.path.join(RESULT_DIR, "model.stl"))
except Exception:
    try:
        bpy.ops.export_mesh.stl(filepath=os.path.join(RESULT_DIR, "model.stl"))
    except Exception as exc:
        print("STL export failed:", exc)

bpy.context.scene.render.filepath = os.path.join(RESULT_DIR, "preview.png")
bpy.context.scene.render.resolution_x = 1200
bpy.context.scene.render.resolution_y = 900
try:
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
except Exception:
    pass
bpy.ops.render.render(write_still=True)
''',
        encoding="utf-8",
    )


def run_local_character_backend(front_image, result_dir, intent="", log_callback=None):
    result_dir = Path(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)
    style = _detect_style(front_image, intent)
    style_path = result_dir / "character_style.json"
    style_path.write_text(json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8")

    script_path = result_dir / "local_character_builder.py"
    _write_blender_script(script_path, front_image, result_dir, style)
    if log_callback:
        log_callback("Local Character: building a free Blender chibi character model.")
    completed = subprocess.run(
        [BLENDER_EXE, "--background", "--python", str(script_path)],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Local Character backend failed.\n\nSTDOUT:\n"
            + completed.stdout[-3000:]
            + "\n\nSTDERR:\n"
            + completed.stderr[-3000:]
        )
    glb_path = result_dir / "model.glb"
    if not glb_path.exists():
        raise RuntimeError(f"Local Character backend did not create model.glb:\n{glb_path}")
    return glb_path
