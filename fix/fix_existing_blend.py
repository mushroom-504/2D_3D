import sys
from pathlib import Path

import bpy
from mathutils import Vector


def cleanup_auto_artifacts():
    for obj in list(bpy.context.scene.objects):
        name = obj.name.lower()
        material_names = [mat.name.lower() for mat in getattr(obj.data, "materials", []) if mat]
        if name.startswith("base") or "base_dark" in material_names:
            bpy.data.objects.remove(obj, do_unlink=True)


def normalize_model_pose():
    mesh_objects = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.name.lower().startswith("base")
    ]
    if not mesh_objects:
        return

    bpy.ops.object.select_all(action="DESELECT")
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


def main():
    args = sys.argv
    if "--" not in args:
        raise SystemExit("Usage: blender --background --python fix_existing_blend.py -- input.blend output.blend")

    script_args = args[args.index("--") + 1 :]
    input_blend = Path(script_args[0])
    output_blend = Path(script_args[1])

    bpy.ops.wm.open_mainfile(filepath=str(input_blend))
    cleanup_auto_artifacts()
    normalize_model_pose()
    setup_level_camera_and_lights()
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))


main()
