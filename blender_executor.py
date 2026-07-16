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
