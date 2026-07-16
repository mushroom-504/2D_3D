import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from agent_brain import analyze_request, build_modeling_intent, create_modeling_plan, save_agent_analysis
from auto_repair import MAX_REPAIR_ATTEMPTS, analyze_error_message, build_repair_intent
from backend_manager import (
    BACKEND_AUTO,
    BACKEND_EXTERNAL_MULTIVIEW,
    BACKEND_LOCAL_CHARACTER,
    BACKEND_TRIPOSR,
    WORK_ROOT,
    copy_reference_images,
    run_external_multiview_backend,
    run_triposr_backend,
)
from blender_executor import run_blender_with_repair
from character_model_builder import looks_like_stylized_character_image, run_local_character_backend
from model_checker import check_generation_outputs
from project_history import append_history, write_error_report


DESKTOP = Path.home() / "Desktop"
VIEW_KEYS = ["back", "top", "bottom", "left", "right"]

LANG = "zh"
current_result_dir = None
current_blend = None
current_obj = None
history = []
is_running = False

TEXT = {
    "zh": {
        "title": "图片转 3D 建模智能体",
        "language": "语言",
        "chinese": "中文",
        "english": "English",
        "main_image": "主图片（正面）",
        "choose_main": "选择正面图",
        "views": "参考图片（背面 / 上面 / 下面 / 左侧 / 右侧）",
        "back": "背面",
        "top": "上面",
        "bottom": "下面",
        "left": "左侧",
        "right": "右侧",
        "choose": "选择",
        "clear": "清空",
        "request_label": "自然语言需求",
        "generate": "生成 .blend",
        "modify": "修改当前模型",
        "open_folder": "打开结果文件夹",
        "agent_log": "智能体日志",
        "default_request": "请根据正面主图生成基础模型，并参考背面、上面、下面、左侧、右侧图修正；模型要放正，不要黑色底座或圆柱。",
        "choose_title": "选择图片",
        "image_files": "图片文件",
        "all_files": "所有文件",
        "error": "错误",
        "failed": "失败",
        "done": "完成",
        "no_image": "正面主图不存在：",
        "no_blend": "还没有当前 .blend 文件，请先生成一个模型。",
        "need_request": "请输入修改需求。",
        "step1": "步骤 1：复制图片并分析需求",
        "step2": "步骤 2：调用建模后端生成基础模型",
        "step3": "步骤 3：调用 Blender 生成 .blend",
        "request": "用户需求",
        "attempt": "Blender 脚本尝试",
        "repair": "Blender 脚本失败，正在自动修复...",
        "complete": "生成完成。",
        "model_generated": "模型已生成到：",
        "files": "包含文件：\ninput_front.png\nreference_images\nagent_analysis.json\nmesh.*\nresult.blend\nmodel.glb\nmodel.fbx\nmodel.stl\npreview.png",
        "multi": "多轮修改模型",
        "modified_saved": "修改后的模型已保存：",
        "api_hint": "说明：智能体会先分析需求和参考图，再调用后端与 Blender 生成模型。",
        "backend_label": "生成后端",
    },
    "en": {
        "title": "Image to 3D Modeling Agent",
        "language": "Language",
        "chinese": "中文",
        "english": "English",
        "main_image": "Main image (front view)",
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
        "generate": "Generate .blend",
        "modify": "Modify Current Model",
        "open_folder": "Open Result Folder",
        "agent_log": "Agent log",
        "default_request": "Generate a base model from the front image, use the other views as references, keep the model upright, and do not create a black base or cylinder.",
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
        "step2": "Step 2: Running modeling backend",
        "step3": "Step 3: Running Blender to generate .blend",
        "request": "User request",
        "attempt": "Blender script attempt",
        "repair": "Blender script failed. Trying to repair...",
        "complete": "Done.",
        "model_generated": "Model generated:",
        "files": "Files:\ninput_front.png\nreference_images\nagent_analysis.json\nmesh.*\nresult.blend\nmodel.glb\nmodel.fbx\nmodel.stl\npreview.png",
        "multi": "Multi-round modification",
        "modified_saved": "Modified model saved:",
        "api_hint": "Note: the agent analyzes the request and references before running the backend and Blender.",
        "backend_label": "Backend",
    },
}


def tr(key):
    return TEXT[LANG][key]


def log(text):
    if threading.current_thread() is not threading.main_thread():
        root.after(0, lambda: log(text))
        return
    output_box.insert(tk.END, str(text) + "\n")
    output_box.see(tk.END)
    root.update()


def set_progress(value, text=None):
    if threading.current_thread() is not threading.main_thread():
        root.after(0, lambda: set_progress(value, text))
        return
    progress_var.set(value)
    if text:
        log(text)
    root.update()


def set_busy(running):
    global is_running
    is_running = running
    state = "disabled" if running else "normal"
    generate_button.config(state=state)
    modify_button.config(state=state)
    choose_main_button.config(state=state)
    backend_box.config(state="disabled" if running else "readonly")
    for key in VIEW_KEYS:
        view_choose_buttons[key].config(state=state)
        view_clear_buttons[key].config(state=state)


def show_info(title, message):
    root.after(0, lambda: messagebox.showinfo(title, message))


def show_error(title, message):
    root.after(0, lambda: messagebox.showerror(title, message))


def run_in_worker(task):
    if is_running:
        messagebox.showwarning(tr("error"), "当前已经有任务在运行，请等待完成。")
        return

    def worker():
        try:
            task()
        finally:
            root.after(0, lambda: set_busy(False))

    set_busy(True)
    threading.Thread(target=worker, daemon=True).start()


def get_reference_map():
    return {key: view_vars[key].get().strip() for key in VIEW_KEYS}


def build_image_paths_for_agent(result_dir, final_input, copied_refs):
    image_paths = {"front": str(final_input)}
    image_paths.update({view: str(path) for view, path in copied_refs.items()})
    return image_paths


def run_backend_with_auto_repair(selected_backend, image_paths_for_agent, result_dir, safe_input, triposr_output_dir, intent=""):
    current_backend = selected_backend
    triposr_resolutions = [384, 256, 128]
    last_error = None

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        try:
            log(f"Backend attempt {attempt}/{MAX_REPAIR_ATTEMPTS}: {current_backend}")
            if current_backend == BACKEND_LOCAL_CHARACTER:
                return run_local_character_backend(
                    image_paths_for_agent.get("front") or safe_input,
                    result_dir,
                    intent=intent,
                    log_callback=log,
                ), current_backend

            if current_backend == BACKEND_EXTERNAL_MULTIVIEW:
                log("External Multi-View may take several minutes on CPU. The window will stay responsive while it runs.")
                return run_external_multiview_backend(image_paths_for_agent, result_dir), current_backend

            resolution = triposr_resolutions[min(attempt - 1, len(triposr_resolutions) - 1)]
            log(f"TripoSR mc-resolution: {resolution}")
            return run_triposr_backend(safe_input, triposr_output_dir, mc_resolution=resolution), BACKEND_TRIPOSR
        except Exception as exc:
            last_error = exc
            report = analyze_error_message(str(exc))
            log("Backend failed. Auto-repair analysis:")
            for category in report.get("categories", []):
                log(f"- category: {category}")
            for action in report.get("actions", []):
                log(f"- action: {action}")

            if attempt >= MAX_REPAIR_ATTEMPTS:
                break

            if current_backend == BACKEND_EXTERNAL_MULTIVIEW:
                current_backend = BACKEND_TRIPOSR
                log("Auto-repair: falling back to TripoSR for the next attempt.")
            else:
                log("Auto-repair: retrying TripoSR with safer lower-resolution settings.")

    raise RuntimeError(f"Backend auto-repair failed after {MAX_REPAIR_ATTEMPTS} attempts.\nLast error:\n{last_error}")


def run_blender_and_check_with_auto_repair(final_obj, final_blend, blender_intent, result_dir):
    latest_code = ""
    current_intent = blender_intent
    latest_check = None

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        log(f"Blender/check attempt {attempt}/{MAX_REPAIR_ATTEMPTS}")
        latest_code = run_blender_with_repair(
            final_obj,
            final_blend,
            current_intent,
            open_existing=False,
            log_callback=log,
            attempt_label=tr("attempt"),
            repair_label=tr("repair"),
            max_script_attempts=1,
        )

        latest_check = check_generation_outputs(result_dir)
        if latest_check["ok"]:
            return latest_code, latest_check

        log("Model check failed. Auto-repair analysis:")
        for problem in latest_check.get("problems", []):
            log(f"- {problem}")

        repair_report = analyze_error_message("\n".join(latest_check.get("problems", [])), latest_check)
        for action in repair_report.get("actions", []):
            log(f"- repair action: {action}")

        if attempt >= MAX_REPAIR_ATTEMPTS:
            break

        current_intent = build_repair_intent(blender_intent, repair_report, latest_check)
        log("Auto-repair: regenerating Blender script and rerunning.")

    return latest_code, latest_check


def generate_3d(image_path, intent, ref_map=None):
    global current_result_dir, current_blend, current_obj
    ref_map = ref_map or {}

    image_path = Path(image_path)
    if not image_path.exists():
        show_error(tr("error"), f"{tr('no_image')}\n{image_path}")
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
    image_paths_for_agent = build_image_paths_for_agent(result_dir, final_input, copied_refs)

    set_progress(15, tr("step1"))
    log(f"{tr('request')}: {intent or tr('default_request')}")
    requested_backend = backend_var.get()
    log(tr("api_hint"))
    log(f"Requested backend: {requested_backend}")

    analysis = analyze_request(intent, image_paths_for_agent)
    plan = create_modeling_plan(intent, image_paths_for_agent, analysis, requested_backend)
    analysis["agent_plan"] = plan
    selected_backend = plan["backend"]
    if (
        requested_backend == BACKEND_AUTO
        and selected_backend == BACKEND_TRIPOSR
        and looks_like_stylized_character_image(final_input, intent)
    ):
        selected_backend = BACKEND_LOCAL_CHARACTER
        plan["backend"] = BACKEND_LOCAL_CHARACTER
        plan.setdefault("reasons", []).append(
            "The front image looks like a stylized character, so Auto switched to the free local Blender character builder."
        )
    analysis_path = save_agent_analysis(result_dir, analysis)
    log(f"agent_analysis.json: {analysis_path}")
    log(f"Agent selected backend: {selected_backend}")
    for reason in plan.get("reasons", []):
        log(f"- {reason}")
    for warning in plan.get("warnings", []):
        log(f"Warning: {warning}")
    set_progress(30)

    set_progress(35, tr("step2"))
    obj_path, actual_backend = run_backend_with_auto_repair(
        selected_backend,
        image_paths_for_agent,
        result_dir,
        safe_input,
        triposr_output_dir,
        intent,
    )
    selected_backend = actual_backend
    set_progress(70)

    final_blend = result_dir / "result.blend"
    blender_intent = build_modeling_intent(intent or tr("default_request"), analysis, copied_refs)
    if selected_backend == BACKEND_LOCAL_CHARACTER:
        final_obj = result_dir / obj_path.name
        user_code = "Local Character backend generated the Blender scene directly."
        set_progress(85, "Step 3: Checking local character model")
        check = check_generation_outputs(result_dir)
    else:
        final_obj = result_dir / f"mesh{obj_path.suffix.lower()}"
        shutil.copy2(obj_path, final_obj)
        set_progress(75, tr("step3"))
        user_code, check = run_blender_and_check_with_auto_repair(final_obj, final_blend, blender_intent, result_dir)
    set_progress(95)
    if not check["ok"]:
        log("Model check warnings after auto-repair:")
        for problem in check.get("problems", []):
            log(f"- {problem}")

    (result_dir / "agent_history.txt").write_text(
        "Initial request and plan:\n"
        + build_modeling_intent(intent or tr("default_request"), analysis, copied_refs)
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
            "requested_backend": requested_backend,
            "plan": plan,
            "result_dir": str(result_dir),
            "blend": str(final_blend),
            "obj": str(final_obj),
            "analysis": str(analysis_path),
            "check": check,
        }
    )

    set_progress(100, tr("complete"))
    show_info(tr("done"), f"{tr('model_generated')}\n{result_dir}\n\n{tr('files')}")


def modify_current_model(intent):
    global current_blend

    if not current_blend or not Path(current_blend).exists():
        show_error(tr("error"), tr("no_blend"))
        return

    timestamp = datetime.now().strftime("%H%M%S")
    result_dir = Path(current_blend).parent
    next_blend = result_dir / f"result_modified_{timestamp}.blend"
    copied_refs = copy_reference_images(get_reference_map(), result_dir)

    image_paths_for_agent = {"front": str(result_dir / "input_front.png")}
    image_paths_for_agent.update({view: str(path) for view, path in copied_refs.items()})
    analysis = analyze_request(intent, image_paths_for_agent)
    analysis_path = save_agent_analysis(result_dir, analysis)
    blender_intent = build_modeling_intent(intent, analysis, copied_refs)

    log(tr("multi"))
    log(f"{tr('request')}: {intent}")
    log(f"agent_analysis.json: {analysis_path}")
    set_progress(40)

    user_code = run_blender_with_repair(
        current_obj,
        next_blend,
        blender_intent,
        open_existing=True,
        log_callback=log,
        attempt_label=tr("attempt"),
        repair_label=tr("repair"),
    )
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
    show_info(tr("done"), f"{tr('modified_saved')}\n{next_blend}")


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
    image_path = main_image_var.get().strip()
    intent = request_box.get("1.0", tk.END).strip()
    ref_map = get_reference_map()

    def task():
        try:
            set_progress(0)
            root.after(0, lambda: output_box.delete("1.0", tk.END))
            generate_3d(image_path, intent, ref_map)
        except Exception as e:
            report = write_error_report(e)
            log(str(e))
            log(f"Error report: {report}")
            show_error(tr("failed"), f"{e}\n\nError report:\n{report}")

    run_in_worker(task)


def start_modify():
    intent = request_box.get("1.0", tk.END).strip()
    if not intent:
        messagebox.showerror(tr("error"), tr("need_request"))
        return

    def task():
        try:
            set_progress(0)
            modify_current_model(intent)
        except Exception as e:
            report = write_error_report(e)
            log(str(e))
            log(f"Error report: {report}")
            show_error(tr("failed"), f"{e}\n\nError report:\n{report}")

    run_in_worker(task)


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
    backend_label.config(text=tr("backend_label"))
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
backend_var = tk.StringVar(value=BACKEND_AUTO)
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
backend_label = tk.Label(backend_frame, text=tr("backend_label"))
backend_label.pack(side="left")
backend_box = ttk.Combobox(
    backend_frame,
    textvariable=backend_var,
    values=[BACKEND_AUTO, BACKEND_LOCAL_CHARACTER, BACKEND_TRIPOSR, BACKEND_EXTERNAL_MULTIVIEW],
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
