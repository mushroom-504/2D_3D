import bpy
import sys
import os

args = sys.argv[sys.argv.index("--") + 1:]
obj_path = args[0]
blend_path = args[1]

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

try:
    bpy.ops.wm.obj_import(filepath=obj_path)
except Exception:
    bpy.ops.import_scene.obj(filepath=obj_path)

for obj in bpy.context.scene.objects:
    obj.select_set(True)

bpy.ops.object.shade_smooth()

bpy.ops.object.light_add(type="AREA", location=(0, -3, 5))
light = bpy.context.object
light.name = "主光源"
light.data.energy = 500
light.data.size = 5

bpy.ops.object.camera_add(location=(0, -4, 2), rotation=(1.2, 0, 0))
bpy.context.scene.camera = bpy.context.object

os.makedirs(os.path.dirname(blend_path), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)