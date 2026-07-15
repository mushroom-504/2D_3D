import os
import json
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from three_view_agent import analyze_three_view_request, build_blender_intent, save_analysis


TRIPOSR_PYTHON = r"D:\conda\envs\triposr\python.exe"
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

HOME = Path.home()
DESKTOP = HOME / "Desktop"
TRIPOSR_DIR = DESKTOP / "TSR" / "TripoSR-main"
WORK_ROOT = Path(r"C:\TSR_Work")
HISTORY_FILE = DESKTOP / "3d_agent_history.jsonl"
LAST_ERROR_FILE = DESKTOP / "3d_agent_last_error.txt"
BACKEND_TRIPOSR = "TripoSR"
BACKEND_EXTERNAL_MULTIVIEW = "External Multi-View"

LANG = "zh"
current_result_dir = None
current_blend = None
current_obj = None
history = []

VIEW_KEYS = ["back", "top", "bottom", "left", "right"]

TEXT = {
    "zh": {
        "title": "\u56fe\u7247\u8f6c 3D \u5efa\u6a21\u667a\u80fd\u4f53",
        "language": "\u8bed\u8a00",
        "chinese": "\u4e2d\u6587",
        "english": "English",
        "main_image": "\u4e3b\u56fe\u7247\uff08\u6b63\u9762\uff0cTripoSR \u4f7f\u7528\u8fd9\u5f20\u56fe\u751f\u6210\u57fa\u7840\u6a21\u578b\uff09",
        "choose_main": "\u9009\u62e9\u6b63\u9762\u56fe",
        "views": "\u53c2\u8003\u56fe\u7247\uff08\u80cc\u9762 / \u4e0a\u9762 / \u4e0b\u9762 / \u5de6\u4fa7 / \u53f3\u4fa7\uff09",
        "back": "\u80cc\u9762",
        "top": "\u4e0a\u9762",
        "bottom": "\u4e0b\u9762",
        "left": "\u5de6\u4fa7",
        "right": "\u53f3\u4fa7",
        "choose": "\u9009\u62e9",
        "clear": "\u6e05\u7a7a",
        "request_label": "\u81ea\u7136\u8bed\u8a00\u9700\u6c42",
        "generate": "\u8c03\u7528 TripoSR \u751f\u6210 .blend",
        "modify": "\u4fee\u6539\u5f53\u524d\u6a21\u578b",
        "open_folder": "\u6253\u5f00\u7ed3\u679c\u6587\u4ef6\u5939",
        "agent_log": "\u667a\u80fd\u4f53\u65e5\u5fd7",
        "default_request": "\u8bf7\u5148\u7528\u6b63\u9762\u4e3b\u56fe\u751f\u6210\u57fa\u7840\u6a21\u578b\uff0c\u518d\u53c2\u8003\u80cc\u9762\u3001\u4e0a\u9762\u3001\u4e0b\u9762\u3001\u5de6\u4fa7\u3001\u53f3\u4fa7\u56fe\u5728 Blender \u4e2d\u4fee\u6b63\uff1b\u6a21\u578b\u8981\u653e\u6b63\uff0c\u4e0d\u8981\u9ed1\u8272\u5e95\u5ea7\u6216\u5706\u67f1\u3002",
        "choose_title": "\u9009\u62e9\u56fe\u7247",
        "image_files": "\u56fe\u7247\u6587\u4ef6",
        "all_files": "\u6240\u6709\u6587\u4ef6",
        "error": "\u9519\u8bef",
        "failed": "\u5931\u8d25",
        "done": "\u5b8c\u6210",
        "no_image": "\u6b63\u9762\u4e3b\u56fe\u4e0d\u5b58\u5728\uff1a",
        "no_blend": "\u8fd8\u6ca1\u6709\u5f53\u524d .blend \u6587\u4ef6\uff0c\u8bf7\u5148\u751f\u6210\u4e00\u4e2a\u6a21\u578b\u3002",
        "need_request": "\u8bf7\u8f93\u5165\u4fee\u6539\u9700\u6c42\u3002",
        "step1": "\u6b65\u9aa4 1\uff1a\u590d\u5236\u56fe\u7247\u5e76\u5206\u6790\u9700\u6c42",
        "step2": "\u6b65\u9aa4 2\uff1a\u8c03\u7528 TripoSR \u751f\u6210 OBJ",
        "step3": "\u6b65\u9aa4 3\uff1a\u8c03\u7528 Blender \u751f\u6210 .blend",
        "request": "\u7528\u6237\u9700\u6c42",
        "attempt": "Blender \u811a\u672c\u5c1d\u8bd5",
        "repair": "Blender \u811a\u672c\u5931\u8d25\uff0c\u6b63\u5728\u81ea\u52a8\u4fee\u590d...",
        "complete": "\u751f\u6210\u5b8c\u6210\u3002",
        "model_generated": "\u6a21\u578b\u5df2\u751f\u6210\u5230\uff1a",
        "files": "\u5305\u542b\u6587\u4ef6\uff1a\ninput_front.png\nreference_images\nagent_analysis.json\nmesh.obj\nresult.blend\nmodel.glb\nmodel.fbx\nmodel.stl\npreview.png",
        "multi": "\u591a\u8f6e\u4fee\u6539\u6a21\u578b",
        "modified_saved": "\u4fee\u6539\u540e\u7684\u6a21\u578b\u5df2\u4fdd\u5b58\uff1a",
        "api_hint": "\u8bf4\u660e\uff1aTripoSR \u53ea\u7528\u6b63\u9762\u4e3b\u56fe\u751f\u6210\u57fa\u7840\u6a21\u578b\uff1b\u5176\u4ed6\u56fe\u4f1a\u8fdb\u5165\u667a\u80fd\u4f53\u5206\u6790\u548c Blender \u4fee\u6539\u63d0\u793a\u3002",
    },
    "en": {
        "title": "Image to 3D Modeling Agent",
        "language": "Language",
        "chinese": "\u4e2d\u6587",
        "english": "English",
        "main_image": "Main image (front view, used by TripoSR)",
        "choose_main": "Choose Front Image",
        "views": "Reference images (back / top / bottom / left / right)",
        "back": "Back",
        "top": "Top",
        "bottom": "Bottom",
        "left": "Left",
        "right": "Right",
        "choose": "Choose",
        "clear": "Clear",
        "request_label": "Natural language request",
        "generate": "Generate .blend with TripoSR",
        "modify": "Modify Current Model",
        "open_folder": "Open Result Folder",
        "agent_log": "Agent log",
        "default_request": "Use the front image to generate the base model with TripoSR, then use the other views to correct it in Blender. Keep the model upright and do not create a black base or cylinder.",
        "choose_title": "Choose an image",
        "image_files": "Image files",
        "all_files": "All files",
        "error": "Error",
        "failed": "Failed",
        "done": "Done",
        "no_image": "Front image not found:",
        "no_blend": "No current .blend file. Generate a model first.",
        "need_request": "Please enter a modification request.",
        "step1": "Step 1: Copying images and analyzing request",
        "step2": "Step 2: Running TripoSR to generate OBJ",
        "step3": "Step 3: Running Blender to generate .blend",
        "request": "User request",
        "attempt": "Blender script attempt",
        "repair": "Blender script failed. Trying to repair...",
        "complete": "Done.",
        "model_generated": "Model generated:",
        "files": "Files:\ninput_front.png\nreference_images\nagent_analysis.json\nmesh.obj\nresult.blend\nmodel.glb\nmodel.fbx\nmodel.stl\npreview.png",
        "multi": "Multi-round modification",
        "modified_saved": "Modified model saved:",
        "api_hint": "Note: TripoSR uses only the front image for the base mesh. Other views are used by the agent analysis and Blender modification prompt.",
    },
}


def tr(key):
    return TEXT[LANG][key]


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


def log(text):
    output_box.insert(tk.END, str(text) + "\n")
    output_box.see(tk.END)
    root.update()


def set_progress(value, text=None):
    progress_var.set(value)
    if text:
        log(text)
    root.update()


def write_error_report(error):
    LAST_ERROR_FILE.write_text(
        "3D Agent Error Report\n"
        + "=" * 60
        + "\n\n"
        + str(error)
        + "\n\nTraceback:\n"
        + traceback.format_exc(),
        encoding="utf-8",
    )
    return LAST_ERROR_FILE


def append_history(event):
    event = dict(event)
    event["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def make_rule_based_code(intent):
    lower = intent.lower()
    code = """
import bpy

def apply_request():
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.shade_smooth()
            mod = obj.modifiers.new("Weighted_Normals", "WEIGHTED_NORMAL")
            mod.keep_sharp = True
            obj.select_set(False)
"""

    if "\u91d1\u5c5e" in intent or "metal" in lower:
        code += """
    mat = bpy.data.materials.new("Metal_Material")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.28
    bsdf.inputs["Base Color"].default_value = (0.8, 0.75, 0.65, 1)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(mat)
"""

    if "\u706f" in intent or "\u4eae" in intent or "light" in lower:
        code += """
    bpy.ops.object.light_add(type="AREA", location=(0, -4, 5))
    light = bpy.context.object
    light.name = "Key_Light"
    light.data.energy = 900
    light.data.size = 5
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
- Keep the model upright, centered, and level.
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


def run_blender_with_repair(obj_path, blend_path, intent, open_existing=False):
    error_message = None
    for attempt in range(1, 4):
        log(f"{tr('attempt')} {attempt}/3 ...")
        user_code = make_ai_code(intent, error_message)
        script_path = Path(blend_path).parent / f"agent_blender_script_attempt_{attempt}.py"
        make_blender_runner(script_path, obj_path, blend_path, user_code, open_existing=open_existing)
        try:
            run_command([BLENDER_EXE, "--background", "--python", str(script_path)])
            return user_code
        except Exception as e:
            error_message = str(e)
            log(tr("repair"))
            log(error_message[:1200])
    raise RuntimeError("Blender auto-repair failed after 3 attempts.")


def copy_reference_images(ref_map, result_dir):
    refs_dir = result_dir / "reference_images"
    refs_dir.mkdir(parents=True, exist_ok=True)
    copied_refs = {}
    for view_key, ref in ref_map.items():
        if not ref:
            continue
        ref_path = Path(ref)
        if ref_path.exists():
            ext = ref_path.suffix.lower()
            dst = refs_dir / f"{view_key}{ext}"
            shutil.copy2(ref_path, dst)
            copied_refs[view_key] = dst
    return copied_refs


def get_reference_map():
    return {key: view_vars[key].get().strip() for key in VIEW_KEYS}


def run_external_multiview_backend(image_paths_for_agent, result_dir):
    script = os.environ.get("MULTIVIEW_RECON_SCRIPT")
    python_exe = os.environ.get("MULTIVIEW_RECON_PYTHON", TRIPOSR_PYTHON)
    default_mast3r_runner = Path(__file__).with_name("mast3r_multiview_runner.py")
    default_mast3r_python = Path(r"D:\conda\envs\mast3r\python.exe")
    if not script or "your_multiview" in script or "path\\to" in script or not Path(script).exists():
        script = str(default_mast3r_runner)
    if not python_exe or "your_multiview" in python_exe or not Path(python_exe).exists():
        python_exe = str(default_mast3r_python if default_mast3r_python.exists() else TRIPOSR_PYTHON)
    if Path(script) == default_mast3r_runner and default_mast3r_python.exists():
        python_exe = str(default_mast3r_python)

    output_dir = Path(result_dir) / "multiview_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [python_exe, script, "--output-dir", str(output_dir)]
    for view, path in image_paths_for_agent.items():
        if path and Path(path).exists():
            command.extend([f"--{view}", str(path)])

    run_command(command)

    candidates = [
        output_dir / "mesh.obj",
        output_dir / "model.obj",
        output_dir / "scene.obj",
        output_dir / "scene.glb",
        output_dir / "model.glb",
        output_dir / "mesh.glb",
        output_dir / "scene.gltf",
        output_dir / "model.gltf",
        output_dir / "mesh.gltf",
        output_dir / "scene.ply",
        output_dir / "model.ply",
        output_dir / "mesh.ply",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    for suffix in [".glb", ".obj", ".gltf", ".ply"]:
        matches = sorted(output_dir.rglob(f"*{suffix}"), key=lambda p: p.stat().st_size, reverse=True)
        if matches:
            return matches[0]

    raise RuntimeError(
        "External Multi-View backend finished, but no OBJ/GLB file was found.\n"
        f"Expected one of:\n" + "\n".join(str(p) for p in candidates)
    )


def generate_3d(image_path, intent, ref_map=None):
    global current_result_dir, current_blend, current_obj
    ref_map = ref_map or {}

    image_path = Path(image_path)
    if not image_path.exists():
        messagebox.showerror(tr("error"), f"{tr('no_image')}\n{image_path}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = DESKTOP / f"Generated_3D_Model_{timestamp}"
    result_dir.mkdir(parents=True, exist_ok=True)
    current_result_dir = result_dir
    set_progress(5, f"Output folder: {result_dir}")

    work_dir = WORK_ROOT / f"job_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)

    safe_input = work_dir / "input_front.png"
    shutil.copy2(image_path, safe_input)
    triposr_output_dir = work_dir / "triposr_output"

    final_input = result_dir / "input_front.png"
    shutil.copy2(image_path, final_input)
    copied_refs = copy_reference_images(ref_map, result_dir)

    image_paths_for_agent = {"front": str(final_input)}
    image_paths_for_agent.update({view: str(path) for view, path in copied_refs.items()})

    set_progress(15, tr("step1"))
    log(f"{tr('request')}: {intent or tr('default_request')}")
    selected_backend = backend_var.get()
    log(tr("api_hint"))
    log(f"Backend: {selected_backend}")
    analysis = analyze_three_view_request(intent, image_paths_for_agent)
    analysis_path = save_analysis(result_dir, analysis)
    log(f"agent_analysis.json: {analysis_path}")
    set_progress(30)

    set_progress(35, tr("step2"))
    if selected_backend == BACKEND_EXTERNAL_MULTIVIEW:
        obj_path = run_external_multiview_backend(image_paths_for_agent, result_dir)
    else:
        run_command(
            [
                TRIPOSR_PYTHON,
                "run.py",
                str(safe_input),
                "--output-dir",
                str(triposr_output_dir),
                "--mc-resolution",
                "384",
            ],
            cwd=str(TRIPOSR_DIR),
        )
        obj_path = triposr_output_dir / "0" / "mesh.obj"
        if not obj_path.exists():
            raise RuntimeError(f"OBJ file not found:\n{obj_path}")
    set_progress(70)

    final_obj = result_dir / f"mesh{obj_path.suffix.lower()}"
    final_blend = result_dir / "result.blend"
    shutil.copy2(obj_path, final_obj)

    blender_intent = build_blender_intent(intent or tr("default_request"), analysis, copied_refs)

    set_progress(75, tr("step3"))
    user_code = run_blender_with_repair(final_obj, final_blend, blender_intent, open_existing=False)
    set_progress(95)

    (result_dir / "agent_history.txt").write_text(
        "Initial request and plan:\n"
        + blender_intent
        + "\n\nGenerated Blender code:\n"
        + user_code,
        encoding="utf-8",
    )

    current_blend = final_blend
    current_obj = final_obj
    history.append(blender_intent)
    append_history(
        {
            "action": "generate",
            "backend": selected_backend,
            "result_dir": str(result_dir),
            "blend": str(final_blend),
            "obj": str(final_obj),
            "analysis": str(analysis_path),
        }
    )

    set_progress(100, tr("complete"))
    messagebox.showinfo(tr("done"), f"{tr('model_generated')}\n{result_dir}\n\n{tr('files')}")


def modify_current_model(intent):
    global current_blend

    if not current_blend or not Path(current_blend).exists():
        messagebox.showerror(tr("error"), tr("no_blend"))
        return

    timestamp = datetime.now().strftime("%H%M%S")
    result_dir = Path(current_blend).parent
    next_blend = result_dir / f"result_modified_{timestamp}.blend"
    copied_refs = copy_reference_images(get_reference_map(), result_dir)

    image_paths_for_agent = {"front": str(result_dir / "input_front.png")}
    image_paths_for_agent.update({view: str(path) for view, path in copied_refs.items()})
    analysis = analyze_three_view_request(intent, image_paths_for_agent)
    analysis_path = save_analysis(result_dir, analysis)
    blender_intent = build_blender_intent(intent, analysis, copied_refs)

    log(tr("multi"))
    log(f"{tr('request')}: {intent}")
    log(f"agent_analysis.json: {analysis_path}")
    set_progress(40)

    user_code = run_blender_with_repair(current_obj, next_blend, blender_intent, open_existing=True)
    set_progress(90)

    current_blend = next_blend
    history.append(blender_intent)
    append_history(
        {
            "action": "modify",
            "backend": "Blender",
            "result_dir": str(result_dir),
            "blend": str(next_blend),
            "analysis": str(analysis_path),
        }
    )

    with (result_dir / "agent_history.txt").open("a", encoding="utf-8") as f:
        f.write("\n\nModification request and plan:\n")
        f.write(blender_intent)
        f.write("\n\nGenerated Blender code:\n")
        f.write(user_code)

    log(f"{tr('modified_saved')} {next_blend}")
    set_progress(100)
    messagebox.showinfo(tr("done"), f"{tr('modified_saved')}\n{next_blend}")


def choose_image_for_var(target_var):
    file_path = filedialog.askopenfilename(
        title=tr("choose_title"),
        filetypes=[
            (tr("image_files"), "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
            (tr("all_files"), "*.*"),
        ],
    )
    if file_path:
        target_var.set(file_path)


def clear_var(target_var):
    target_var.set("")


def start_generate():
    try:
        set_progress(0)
        output_box.delete("1.0", tk.END)
        generate_3d(
            main_image_var.get().strip(),
            request_box.get("1.0", tk.END).strip(),
            get_reference_map(),
        )
    except Exception as e:
        report = write_error_report(e)
        log(str(e))
        log(f"Error report: {report}")
        messagebox.showerror(tr("failed"), f"{e}\n\nError report:\n{report}")


def start_modify():
    try:
        set_progress(0)
        intent = request_box.get("1.0", tk.END).strip()
        if not intent:
            messagebox.showerror(tr("error"), tr("need_request"))
            return
        modify_current_model(intent)
    except Exception as e:
        report = write_error_report(e)
        log(str(e))
        log(f"Error report: {report}")
        messagebox.showerror(tr("failed"), f"{e}\n\nError report:\n{report}")


def open_result_folder():
    if current_result_dir and Path(current_result_dir).exists():
        os.startfile(current_result_dir)


def change_language(event=None):
    global LANG
    selected = language_var.get()
    LANG = "zh" if selected == TEXT["zh"]["chinese"] else "en"
    apply_language()


def apply_language():
    root.title(tr("title"))
    title_label.config(text=tr("title"))
    language_label.config(text=tr("language"))
    main_image_label.config(text=tr("main_image"))
    choose_main_button.config(text=tr("choose_main"))
    views_label.config(text=tr("views"))
    request_label.config(text=tr("request_label"))
    generate_button.config(text=tr("generate"))
    modify_button.config(text=tr("modify"))
    open_folder_button.config(text=tr("open_folder"))
    log_label.config(text=tr("agent_log"))
    for key in VIEW_KEYS:
        view_labels[key].config(text=tr(key))
        view_choose_buttons[key].config(text=tr("choose"))
        view_clear_buttons[key].config(text=tr("clear"))
    current_text = request_box.get("1.0", tk.END).strip()
    defaults = {TEXT["zh"]["default_request"], TEXT["en"]["default_request"], ""}
    if current_text in defaults:
        request_box.delete("1.0", tk.END)
        request_box.insert("1.0", tr("default_request"))


root = tk.Tk()
root.title(tr("title"))
root.geometry("940x780")

main_image_var = tk.StringVar()
view_vars = {key: tk.StringVar() for key in VIEW_KEYS}
language_var = tk.StringVar(value=TEXT["zh"]["chinese"])
progress_var = tk.IntVar(value=0)
backend_var = tk.StringVar(value=BACKEND_TRIPOSR)
view_labels = {}
view_choose_buttons = {}
view_clear_buttons = {}

top_bar = tk.Frame(root)
top_bar.pack(fill="x", padx=16, pady=10)

title_label = tk.Label(top_bar, text=tr("title"), font=("Microsoft YaHei", 18))
title_label.pack(side="left")

language_frame = tk.Frame(top_bar)
language_frame.pack(side="right")
language_label = tk.Label(language_frame, text=tr("language"))
language_label.pack(side="left", padx=(0, 6))
language_box = ttk.Combobox(
    language_frame,
    textvariable=language_var,
    values=[TEXT["zh"]["chinese"], TEXT["en"]["english"]],
    state="readonly",
    width=10,
)
language_box.pack(side="left")
language_box.bind("<<ComboboxSelected>>", change_language)

backend_frame = tk.Frame(root)
backend_frame.pack(fill="x", padx=16, pady=(0, 8))
tk.Label(backend_frame, text="Backend / 生成后端").pack(side="left")
backend_box = ttk.Combobox(
    backend_frame,
    textvariable=backend_var,
    values=[BACKEND_TRIPOSR, BACKEND_EXTERNAL_MULTIVIEW],
    state="readonly",
    width=24,
)
backend_box.pack(side="left", padx=8)

main_image_label = tk.Label(root, text=tr("main_image"))
main_image_label.pack(anchor="w", padx=16)
main_row = tk.Frame(root)
main_row.pack(fill="x", padx=16, pady=(4, 10))
tk.Entry(main_row, textvariable=main_image_var).pack(side="left", fill="x", expand=True)
choose_main_button = tk.Button(main_row, text=tr("choose_main"), command=lambda: choose_image_for_var(main_image_var))
choose_main_button.pack(side="left", padx=8)

views_label = tk.Label(root, text=tr("views"))
views_label.pack(anchor="w", padx=16)
views_frame = tk.Frame(root)
views_frame.pack(fill="x", padx=16, pady=(4, 8))

for view_key in VIEW_KEYS:
    row = tk.Frame(views_frame)
    row.pack(fill="x", pady=2)
    label = tk.Label(row, text=tr(view_key), width=8, anchor="w")
    label.pack(side="left")
    view_labels[view_key] = label
    tk.Entry(row, textvariable=view_vars[view_key]).pack(side="left", fill="x", expand=True)
    choose_button = tk.Button(row, text=tr("choose"), command=lambda key=view_key: choose_image_for_var(view_vars[key]))
    choose_button.pack(side="left", padx=6)
    view_choose_buttons[view_key] = choose_button
    clear_button = tk.Button(row, text=tr("clear"), command=lambda key=view_key: clear_var(view_vars[key]))
    clear_button.pack(side="left")
    view_clear_buttons[view_key] = clear_button

request_label = tk.Label(root, text=tr("request_label"))
request_label.pack(anchor="w", padx=16, pady=(4, 0))
request_box = tk.Text(root, height=5)
request_box.pack(fill="x", padx=16)
request_box.insert("1.0", tr("default_request"))

btn_row = tk.Frame(root)
btn_row.pack(pady=10)
generate_button = tk.Button(btn_row, text=tr("generate"), width=26, command=start_generate)
generate_button.pack(side="left", padx=8)
modify_button = tk.Button(btn_row, text=tr("modify"), width=22, command=start_modify)
modify_button.pack(side="left", padx=8)
open_folder_button = tk.Button(btn_row, text=tr("open_folder"), width=18, command=open_result_folder)
open_folder_button.pack(side="left", padx=8)

log_label = tk.Label(root, text=tr("agent_log"))
log_label.pack(anchor="w", padx=16)
progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
progress_bar.pack(fill="x", padx=16, pady=(0, 8))
output_box = scrolledtext.ScrolledText(root, height=15)
output_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))

apply_language()
root.mainloop()
