import subprocess

BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

OBJ_PATH = r"C:\Users\荣\Desktop\TSR\TripoSR-main\output_aa4\0\mesh.obj"
BLENDER_SCRIPT = r"C:\Users\荣\PycharmProjects\PythonProject4\blender_auto_import.py"
OUT_BLEND = r"C:\Users\荣\Desktop\TSR\TripoSR-main\output_aa4\0\result.blend"

subprocess.run([
    BLENDER_EXE,
    "--background",
    "--python",
    BLENDER_SCRIPT,
    "--",
    OBJ_PATH,
    OUT_BLEND
], check=True)

print("Blender 工程已生成：", OUT_BLEND)