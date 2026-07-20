from pathlib import Path

from auto_repair import make_ai_code
from backend_manager import run_command


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"


def make_blender_runner(script_path, obj_path, blend_path, user_code, open_existing=False):
    if open_existing:
        loader = f'bpy.ops.wm.open_mainfile(filepath=r"{blend_path}")'
    else:
        suffix = Path(obj_path).suffix.lower()
        if suffix in [".glb", ".gltf"]:
            loader = f"""
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=r"{obj_path}")
"""
        elif suffix == ".ply":
            loader = f"""
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
try:
    bpy.ops.wm.ply_import(filepath=r"{obj_path}")
except Exception:
    bpy.ops.import_mesh.ply(filepath=r"{obj_path}")
"""
        else:
            loader = f"""
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
try:
    bpy.ops.wm.obj_import(filepath=r"{obj_path}")
except Exception:
    bpy.ops.import_scene.obj(filepath=r"{obj_path}")
"""

    script_path.write_text(
        f"""
import bpy
import os
from mathutils import Vector

{loader}

def cleanup_auto_artifacts():
    for obj in list(bpy.context.scene.objects):
        name = obj.name.lower()
        material_names = [mat.name.lower() for mat in getattr(obj.data, "materials", []) if mat]
        if name.startswith("base") or "base_dark" in material_names or "pedestal" in name:
            bpy.data.objects.remove(obj, do_unlink=True)

def normalize_model_pose():
    mesh_objects = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.name.lower().startswith("base")
    ]
    if not mesh_objects:
        return
    for obj in mesh_objects:
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    try:
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    except Exception:
        pass
    corners = []
    for obj in mesh_objects:
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
    for obj in mesh_objects:
        obj.location += offset
        obj.select_set(False)

def setup_level_camera_and_lights():
    for obj in list(bpy.context.scene.objects):
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.camera_add(location=(0, -4.0, 1.8), rotation=(1.5708, 0.0, 0.0))
    bpy.context.scene.camera = bpy.context.object
    if not any(obj.type == "LIGHT" for obj in bpy.context.scene.objects):
        bpy.ops.object.light_add(type="AREA", location=(0, -3.5, 4.0))
        light = bpy.context.object
        light.name = "Key_Light"
        light.data.energy = 700
        light.data.size = 4

cleanup_auto_artifacts()
normalize_model_pose()

{user_code}

cleanup_auto_artifacts()
normalize_model_pose()
setup_level_camera_and_lights()

os.makedirs(os.path.dirname(r"{blend_path}"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=r"{blend_path}")

export_dir = os.path.dirname(r"{blend_path}")

try:
    bpy.ops.export_scene.gltf(filepath=os.path.join(export_dir, "model.glb"), export_format="GLB")
except Exception as exc:
    print("GLB export failed:", exc)

try:
    bpy.ops.export_scene.fbx(filepath=os.path.join(export_dir, "model.fbx"))
except Exception as exc:
    print("FBX export failed:", exc)

try:
    bpy.ops.wm.stl_export(filepath=os.path.join(export_dir, "model.stl"))
except Exception:
    try:
        bpy.ops.export_mesh.stl(filepath=os.path.join(export_dir, "model.stl"))
    except Exception as exc:
        print("STL export failed:", exc)

try:
    bpy.context.scene.render.filepath = os.path.join(export_dir, "preview.png")
    bpy.context.scene.render.resolution_x = 1200
    bpy.context.scene.render.resolution_y = 900
    try:
        bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    except Exception:
        pass
    bpy.ops.render.render(write_still=True)
except Exception as exc:
    print("Preview render failed:", exc)
""",
        encoding="utf-8",
    )


def run_blender_with_repair(
    obj_path,
    blend_path,
    intent,
    open_existing=False,
    log_callback=None,
    attempt_label="Blender script attempt",
    repair_label="Blender script failed. Trying to repair...",
    max_script_attempts=3,
):
    def log(text):
        if log_callback:
            log_callback(text)

    error_message = None
    for attempt in range(1, max_script_attempts + 1):
        log(f"{attempt_label} {attempt}/{max_script_attempts} ...")
        user_code = make_ai_code(intent, error_message)
        script_path = Path(blend_path).parent / f"agent_blender_script_attempt_{attempt}.py"
        make_blender_runner(script_path, obj_path, blend_path, user_code, open_existing=open_existing)
        try:
            run_command([BLENDER_EXE, "--background", "--python", str(script_path)])
            return user_code
        except Exception as e:
            error_message = str(e)
            log(repair_label)
            log(error_message[:1200])
    raise RuntimeError(f"Blender auto-repair failed after {max_script_attempts} attempts.")


def run_blender_triposr_enhanced(obj_path, blend_path, image_paths_for_agent, intent="", log_callback=None):
    def log(text):
        if log_callback:
            log_callback(text)

    blend_path = Path(blend_path)
    result_dir = blend_path.parent
    script_path = result_dir / "triposr_enhanced_blender.py"
    refs = {
        view: str(path)
        for view, path in (image_paths_for_agent or {}).items()
        if view != "front" and path
    }
    front_image = (image_paths_for_agent or {}).get("front", "")

    user_code = f"""TripoSR Enhanced clean deterministic Blender post-process.
- Source mesh: {obj_path}
- Front image: {front_image}
- Reference views: {refs}
- Intent: {intent}
- Final scene keeps only the TripoSR mesh, camera, and light.
"""

    script_path.write_text(
        f'''
import json
import math
import os
import bpy
from mathutils import Vector

OBJ_PATH = r"{obj_path}"
BLEND_PATH = r"{blend_path}"
FRONT_IMAGE = r"{front_image}"
REFERENCE_IMAGES = {repr(refs)}

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

try:
    bpy.ops.wm.obj_import(filepath=OBJ_PATH)
except Exception:
    bpy.ops.import_scene.obj(filepath=OBJ_PATH)


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.58
    return mat


skin = material("enhanced_warm_skin", (1.0, 0.78, 0.64, 1))
pink = material("enhanced_pink", (1.0, 0.42, 0.48, 1))
white = material("enhanced_white", (0.96, 0.93, 0.88, 1))
dark = material("enhanced_dark", (0.035, 0.03, 0.03, 1))


def mesh_objects(include_refs=False):
    result = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if not include_refs and "reference_plane" in obj.name:
            continue
        if obj.name.lower().startswith("base") or "pedestal" in obj.name.lower():
            continue
        result.append(obj)
    return result


def bounds(objects):
    corners = []
    for obj in objects:
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    if not corners:
        return None
    return {{
        "min_x": min(v.x for v in corners),
        "max_x": max(v.x for v in corners),
        "min_y": min(v.y for v in corners),
        "max_y": max(v.y for v in corners),
        "min_z": min(v.z for v in corners),
        "max_z": max(v.z for v in corners),
    }}


def center_and_ground(objects):
    b = bounds(objects)
    if not b:
        return
    offset = Vector((
        -(b["min_x"] + b["max_x"]) / 2.0,
        -(b["min_y"] + b["max_y"]) / 2.0,
        -b["min_z"],
    ))
    for obj in objects:
        obj.location += offset


def make_upright_and_smooth():
    objects = mesh_objects()
    for obj in objects:
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        except Exception:
            pass
    for obj in objects:
        if not obj.data.materials:
            obj.data.materials.append(white)
        try:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.shade_smooth()
            obj.modifiers.new("enhanced_weighted_normals", "WEIGHTED_NORMAL")
            bevel = obj.modifiers.new("tiny_softening_bevel", "BEVEL")
            bevel.width = 0.008
            bevel.segments = 2
            obj.select_set(False)
        except Exception:
            pass
    center_and_ground(objects)


def thicken_if_flat():
    objects = mesh_objects()
    b = bounds(objects)
    if not b:
        return {{"changed": False, "reason": "no mesh"}}
    width = max(b["max_x"] - b["min_x"], 0.001)
    depth = max(b["max_y"] - b["min_y"], 0.001)
    height = max(b["max_z"] - b["min_z"], 0.001)
    target_depth = max(width * 0.90, height * 0.28)
    if REFERENCE_IMAGES.get("left") or REFERENCE_IMAGES.get("right"):
        target_depth = max(target_depth, width * 1.05)
    if REFERENCE_IMAGES.get("back"):
        target_depth = max(target_depth, width * 0.95)
    scale_factor = min(max(target_depth / depth, 1.0), 5.0)
    if scale_factor <= 1.05:
        return {{"changed": False, "width": width, "depth": depth, "height": height, "scale_factor": scale_factor}}
    for obj in objects:
        obj.scale.y *= scale_factor
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    try:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    except Exception:
        pass
    for obj in objects:
        obj.select_set(False)
    center_and_ground(objects)
    return {{"changed": True, "width": width, "old_depth": depth, "target_depth": target_depth, "scale_factor": scale_factor}}


def inflate_main_mesh():
    objects = mesh_objects()
    b = bounds(objects)
    if not b:
        return {{"changed": False, "reason": "no mesh"}}
    width = max(b["max_x"] - b["min_x"], 0.001)
    height = max(b["max_z"] - b["min_z"], 0.001)
    strength = min(max(width, height) * 0.025, 0.08)
    changed = False
    for obj in objects:
        disp = obj.modifiers.new("clean_subtle_inflate", "DISPLACE")
        disp.strength = strength
        changed = True
        try:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.modifier_apply(modifier=disp.name)
            obj.select_set(False)
        except Exception:
            obj.select_set(False)
    center_and_ground(objects)
    return {{"changed": changed, "strength": strength}}


def cleanup_generated_helpers():
    for obj in list(bpy.context.scene.objects):
        name = obj.name.lower()
        if (
            "reference_plane" in name
            or name.startswith("enhanced_back")
            or name.startswith("enhanced_left")
            or name.startswith("enhanced_right")
            or name.startswith("enhanced_top")
            or name.startswith("enhanced_bottom")
        ):
            bpy.data.objects.remove(obj, do_unlink=True)


def setup_camera_and_light():
    for obj in list(bpy.context.scene.objects):
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)
    b = bounds(mesh_objects())
    if not b:
        return
    cx = (b["min_x"] + b["max_x"]) / 2.0
    cy = (b["min_y"] + b["max_y"]) / 2.0
    height = b["max_z"] - b["min_z"]
    bpy.ops.object.camera_add(location=(cx, b["min_y"] - height * 2.2, b["min_z"] + height * 0.58), rotation=(math.radians(72), 0, 0))
    bpy.context.scene.camera = bpy.context.object
    bpy.ops.object.light_add(type="AREA", location=(cx, b["min_y"] - height * 1.3, b["max_z"] + height * 0.8))
    light = bpy.context.object
    light.name = "Enhanced_Softbox"
    light.data.energy = 700
    light.data.size = max(height, 2.0)


make_upright_and_smooth()
thickness_report = thicken_if_flat()
inflate_report = inflate_main_mesh()
cleanup_generated_helpers()
setup_camera_and_light()

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
with open(os.path.join(os.path.dirname(BLEND_PATH), "triposr_enhanced_report.json"), "w", encoding="utf-8") as f:
    json.dump({{
        "mode": "clean_mesh_only",
        "thickness": thickness_report,
        "inflate": inflate_report,
        "reference_images_used_as_guidance_only": REFERENCE_IMAGES,
    }}, f, ensure_ascii=False, indent=2)

bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
export_dir = os.path.dirname(BLEND_PATH)

try:
    bpy.ops.export_scene.gltf(filepath=os.path.join(export_dir, "model.glb"), export_format="GLB")
except Exception as exc:
    print("GLB export failed:", exc)

try:
    bpy.ops.export_scene.fbx(filepath=os.path.join(export_dir, "model.fbx"))
except Exception as exc:
    print("FBX export failed:", exc)

try:
    bpy.ops.wm.stl_export(filepath=os.path.join(export_dir, "model.stl"))
except Exception:
    try:
        bpy.ops.export_mesh.stl(filepath=os.path.join(export_dir, "model.stl"))
    except Exception as exc:
        print("STL export failed:", exc)

try:
    bpy.context.scene.render.filepath = os.path.join(export_dir, "preview.png")
    bpy.context.scene.render.resolution_x = 1200
    bpy.context.scene.render.resolution_y = 900
    try:
        bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    except Exception:
        pass
    bpy.ops.render.render(write_still=True)
except Exception as exc:
    print("Preview render failed:", exc)
''',
        encoding="utf-8",
    )

    log("TripoSR Enhanced: running Blender thickness repair and reference shaping.")
    run_command([BLENDER_EXE, "--background", "--python", str(script_path)])
    return user_code


def run_blender_triposr_fusion(mesh_paths, blend_path, image_paths_for_agent, intent="", log_callback=None):
    def log(text):
        if log_callback:
            log_callback(text)

    blend_path = Path(blend_path)
    result_dir = blend_path.parent
    script_path = result_dir / "triposr_fusion_blender.py"
    mesh_paths = {view: str(path) for view, path in (mesh_paths or {}).items() if path}
    refs = {
        view: str(path)
        for view, path in (image_paths_for_agent or {}).items()
        if path
    }

    user_code = f"""TripoSR Fusion deterministic Blender post-process.
- Each available view is first converted by TripoSR.
- Blender imports front/back/side meshes, aligns them, rotates them by view, voxel-remeshes them into one mesh, then smooths and exports.
- Meshes: {mesh_paths}
- Images: {refs}
- Intent: {intent}
"""

    script_path.write_text(
        f'''
import json
import math
import os
import bpy
from mathutils import Vector

BLEND_PATH = r"{blend_path}"
MESH_PATHS = {repr(mesh_paths)}
IMAGE_PATHS = {repr(refs)}
INTENT = {repr(intent)}

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()


def import_obj(path, view):
    before = set(bpy.context.scene.objects)
    try:
        bpy.ops.wm.obj_import(filepath=path)
    except Exception:
        bpy.ops.import_scene.obj(filepath=path)
    imported = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    for obj in imported:
        obj.name = f"triposr_{{view}}_mesh"
        obj.data.name = f"triposr_{{view}}_mesh_data"
    return imported


def bounds(objects):
    corners = []
    for obj in objects:
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))
    if not corners:
        return None
    return {{
        "min_x": min(v.x for v in corners),
        "max_x": max(v.x for v in corners),
        "min_y": min(v.y for v in corners),
        "max_y": max(v.y for v in corners),
        "min_z": min(v.z for v in corners),
        "max_z": max(v.z for v in corners),
    }}


def normalize_group(objects, target_height=2.4):
    b = bounds(objects)
    if not b:
        return
    width = max(b["max_x"] - b["min_x"], 0.001)
    depth = max(b["max_y"] - b["min_y"], 0.001)
    height = max(b["max_z"] - b["min_z"], 0.001)
    scale = target_height / max(width, depth, height)
    center = Vector((
        (b["min_x"] + b["max_x"]) / 2.0,
        (b["min_y"] + b["max_y"]) / 2.0,
        (b["min_z"] + b["max_z"]) / 2.0,
    ))
    for obj in objects:
        obj.location -= center
        obj.scale *= scale
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        try:
            bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
        except Exception:
            pass
    for obj in objects:
        obj.select_set(False)


def rotate_group(objects, view):
    rotations = {{
        "front": (0.0, 0.0, 0.0),
        "back": (0.0, 0.0, math.radians(180)),
        "left": (0.0, 0.0, math.radians(-90)),
        "right": (0.0, 0.0, math.radians(90)),
        "top": (math.radians(90), 0.0, 0.0),
        "bottom": (math.radians(-90), 0.0, 0.0),
    }}
    rot = rotations.get(view, (0.0, 0.0, 0.0))
    for obj in objects:
        obj.rotation_euler = rot
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        except Exception:
            pass
    for obj in objects:
        obj.select_set(False)


def make_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.62
    return mat


def make_image_texture_material(name, image_path, fallback_color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = fallback_color
        bsdf.inputs["Roughness"].default_value = 0.58
    if image_path and os.path.exists(image_path) and bsdf:
        try:
            image = bpy.data.images.load(image_path)
            image.pack()
            tex = nodes.new(type="ShaderNodeTexImage")
            tex.name = "front_image_texture"
            tex.image = image
            tex.extension = "EXTEND"
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        except Exception as exc:
            print("Image texture material failed:", exc)
    mat.diffuse_color = fallback_color
    return mat


def center_and_ground(objects):
    b = bounds(objects)
    if not b:
        return
    offset = Vector((
        -(b["min_x"] + b["max_x"]) / 2.0,
        -(b["min_y"] + b["max_y"]) / 2.0,
        -b["min_z"],
    ))
    for obj in objects:
        obj.location += offset


all_meshes = []
for view in ["front", "back", "left", "right", "top", "bottom"]:
    path = MESH_PATHS.get(view)
    if not path or not os.path.exists(path):
        continue
    imported = import_obj(path, view)
    normalize_group(imported)
    rotate_group(imported, view)
    all_meshes.extend(imported)

if not all_meshes:
    raise RuntimeError("No TripoSR Fusion meshes were imported.")

for obj in bpy.context.scene.objects:
    obj.select_set(False)
for obj in all_meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = all_meshes[0]
try:
    bpy.ops.object.join()
except Exception:
    pass

fused = bpy.context.view_layer.objects.active
fused.name = "fused_triposr_mesh"
fused.data.name = "fused_triposr_mesh_data"
if fused.data.materials:
    fused.data.materials.clear()
fused.data.materials.append(
    make_image_texture_material(
        "fusion_front_image_material",
        IMAGE_PATHS.get("front", ""),
        (0.92, 0.86, 0.82, 1.0),
    )
)

try:
    bpy.context.view_layer.objects.active = fused
    fused.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
except Exception as exc:
    print("UV projection failed:", exc)
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

try:
    remesh = fused.modifiers.new("fusion_voxel_remesh", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = 0.035
    remesh.adaptivity = 0.08
    bpy.ops.object.modifier_apply(modifier=remesh.name)
except Exception as exc:
    print("Voxel remesh failed:", exc)

try:
    smooth = fused.modifiers.new("fusion_corrective_smooth", "CORRECTIVE_SMOOTH")
    smooth.factor = 0.45
    smooth.iterations = 3
    bpy.ops.object.modifier_apply(modifier=smooth.name)
except Exception as exc:
    print("Corrective smooth failed:", exc)

try:
    disp = fused.modifiers.new("fusion_subtle_inflate", "DISPLACE")
    disp.strength = 0.035
    bpy.ops.object.modifier_apply(modifier=disp.name)
except Exception as exc:
    print("Inflate failed:", exc)

try:
    bpy.ops.object.shade_smooth()
except Exception:
    pass

try:
    fused.modifiers.new("fusion_weighted_normals", "WEIGHTED_NORMAL")
except Exception:
    pass

center_and_ground([fused])

try:
    bpy.context.view_layer.objects.active = fused
    fused.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
except Exception as exc:
    print("Final UV projection failed:", exc)
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

for obj in list(bpy.context.scene.objects):
    name = obj.name.lower()
    if name.startswith("base") or "pedestal" in name or "reference_plane" in name:
        bpy.data.objects.remove(obj, do_unlink=True)

b = bounds([fused])
if b:
    height = max(b["max_z"] - b["min_z"], 1.0)
    bpy.ops.object.light_add(type="AREA", location=(0, -3.2, height * 1.6))
    light = bpy.context.object
    light.name = "Fusion_Softbox"
    light.data.energy = 800
    light.data.size = 4.0
    bpy.ops.object.camera_add(location=(0, -4.5, height * 0.72), rotation=(math.radians(72), 0.0, 0.0))
    bpy.context.scene.camera = bpy.context.object

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
export_dir = os.path.dirname(BLEND_PATH)

with open(os.path.join(export_dir, "triposr_fusion_report.json"), "w", encoding="utf-8") as f:
    json.dump({{
        "mode": "triposr_fusion",
        "mesh_paths": MESH_PATHS,
        "image_paths": IMAGE_PATHS,
        "intent": INTENT,
        "fusion_steps": [
            "TripoSR per view",
            "normalize each mesh",
            "rotate by view",
            "join meshes",
            "voxel remesh",
            "smooth and subtle inflate",
            "export blend/glb/fbx/stl/obj/preview",
        ],
    }}, f, ensure_ascii=False, indent=2)

bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)

try:
    bpy.ops.wm.obj_export(filepath=os.path.join(export_dir, "fused_mesh.obj"))
except Exception:
    try:
        bpy.ops.export_scene.obj(filepath=os.path.join(export_dir, "fused_mesh.obj"))
    except Exception as exc:
        print("OBJ export failed:", exc)

try:
    bpy.ops.export_scene.gltf(filepath=os.path.join(export_dir, "model.glb"), export_format="GLB")
except Exception as exc:
    print("GLB export failed:", exc)

try:
    bpy.ops.export_scene.fbx(filepath=os.path.join(export_dir, "model.fbx"))
except Exception as exc:
    print("FBX export failed:", exc)

try:
    bpy.ops.wm.stl_export(filepath=os.path.join(export_dir, "model.stl"))
except Exception:
    try:
        bpy.ops.export_mesh.stl(filepath=os.path.join(export_dir, "model.stl"))
    except Exception as exc:
        print("STL export failed:", exc)

try:
    bpy.context.scene.render.filepath = os.path.join(export_dir, "preview.png")
    bpy.context.scene.render.resolution_x = 1200
    bpy.context.scene.render.resolution_y = 900
    try:
        bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    except Exception:
        pass
    bpy.ops.render.render(write_still=True)
except Exception as exc:
    print("Preview render failed:", exc)
''',
        encoding="utf-8",
    )

    log("TripoSR Fusion: running Blender multi-mesh alignment and voxel remesh.")
    run_command([BLENDER_EXE, "--background", "--python", str(script_path)])
    return user_code
