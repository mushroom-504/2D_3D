# -*- coding: utf-8 -*-

import os
import json
import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from agent_brain import analyze_request, build_modeling_intent, create_modeling_plan, save_agent_analysis
from auto_repair import MAX_REPAIR_ATTEMPTS, analyze_error_message, build_repair_intent
from blender_actions import build_action_plan, save_action_plan
from backend_health import check_backend_health, format_health_report
from backend_manager import (
    BACKEND_AUTO,
    BACKEND_CRAFTSMAN,
    BACKEND_EXTERNAL_MULTIVIEW,
    BACKEND_TRIPOSR,
    BACKEND_TRIPOSR_FUSION,
    TaskCancelledError,
    WORK_ROOT,
    clear_cancel_request,
    copy_reference_images,
    get_last_backend_details,
    run_craftsman_backend,
    run_external_multiview_backend,
    run_triposr_backend,
    run_triposr_fusion_backend,
    stop_current_process,
)
from blender_executor import run_blender_triposr_fusion, run_blender_with_repair
from mesh_refiner import write_refinement_report
from model_checker import check_generation_outputs
from project_history import append_history, write_error_report
from config_loader import get_path, get_runtime
from task_manager import (
    clear_active_job,
    create_job,
    finish_job,
    get_job,
    list_jobs,
    list_stages,
    record_stage,
    recover_interrupted_jobs,
    requeue_job,
    set_active_job,
    start_job,
    task_stage,
    update_job,
)
from three_view_agent import get_analysis_capability


DESKTOP = get_path("output_root")
DEFAULT_BACKEND = str(get_runtime("default_backend", BACKEND_TRIPOSR))
VIEW_KEYS = ["back", "top", "bottom", "left", "right"]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

LANG = "zh"
current_result_dir = None
current_blend = None
current_obj = None
history = []
is_running = False
active_job_id = None
job_queue = queue.Queue()
enqueued_job_ids = set()
job_worker_running = False
job_worker_lock = threading.Lock()
last_image_dir = DESKTOP

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

TEXT["zh"] = {
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
    "default_request": "请根据正面主图生成基础模型，并参考背面、上面、下面、左侧、右侧图片修正；模型要摆正，不要黑色底座或圆柱。",
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
    "repair": "Blender 脚本失败，正在自动修复……",
    "complete": "生成完成。",
    "model_generated": "模型已生成到：",
    "files": "包含文件：\ninput_front.png\nreference_images\nagent_analysis.json\nmesh.*\nresult.blend\nmodel.glb\nmodel.fbx\nmodel.stl\npreview.png",
    "multi": "多轮修改模型",
    "modified_saved": "修改后的模型已保存：",
    "api_hint": "说明：智能体会先分析需求和参考图，再调用后端与 Blender 生成模型。",
    "backend_label": "生成后端",
}


def cancel_task():
    if not is_running:
        return
    log(f"正在终止当前任务及其子进程：{active_job_id or '未记录任务 ID'}")
    cancel_button.config(state="disabled")
    stop_current_process()
    log("已发送取消请求，正在等待任务线程退出。")


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
    generate_button.config(state="normal")
    modify_button.config(state="normal")
    choose_main_button.config(state="normal")
    backend_box.config(state="readonly")
    health_button.config(state="disabled" if running else "normal")
    cancel_button.config(state="normal" if running else "disabled")
    for key in VIEW_KEYS:
        view_choose_buttons[key].config(state="normal")
        view_clear_buttons[key].config(state="normal")


def show_info(title, message):
    root.after(0, lambda: messagebox.showinfo(title, message))


def show_error(title, message):
    root.after(0, lambda: messagebox.showerror(title, message))


def run_in_worker(task):
    if is_running:
        messagebox.showwarning(tr("error"), "当前已经有任务在运行，请等待完成。")
        return

    clear_cancel_request()

    def worker():
        try:
            task()
        except TaskCancelledError:
            log("任务已取消。")
        finally:
            root.after(0, lambda: set_busy(False))

    set_busy(True)
    threading.Thread(target=worker, daemon=True).start()


def enqueue_persistent_job(job_id, task):
    global job_worker_running
    with job_worker_lock:
        if job_id in enqueued_job_ids or job_id == active_job_id:
            log(f"任务已经在队列或正在运行：{job_id}")
            return
        enqueued_job_ids.add(job_id)
    job_queue.put((job_id, task))
    update_job(job_id, status="queued")
    log(f"任务已进入队列：{job_id}，前方等待 {max(job_queue.qsize() - 1, 0)} 个任务。")
    with job_worker_lock:
        if job_worker_running:
            return
        job_worker_running = True
    set_busy(True)
    threading.Thread(target=_persistent_job_worker, daemon=True).start()


def _persistent_job_worker():
    global active_job_id, job_worker_running
    while True:
        try:
            job_id, task = job_queue.get_nowait()
        except queue.Empty:
            with job_worker_lock:
                if not job_queue.empty():
                    continue
                job_worker_running = False
            active_job_id = None
            root.after(0, lambda: set_busy(False))
            return

        with job_worker_lock:
            enqueued_job_ids.discard(job_id)
        job_record = get_job(job_id)
        if not job_record or job_record.get("status") == "cancelled":
            job_queue.task_done()
            continue

        active_job_id = job_id
        clear_cancel_request()
        set_active_job(job_id)
        start_job(job_id)
        log(f"开始任务：{job_id}")
        try:
            task(job_id)
        except TaskCancelledError as exc:
            finish_job(job_id, "cancelled", str(exc))
            log(f"任务已取消：{job_id}")
        except Exception as exc:
            finish_job(job_id, "failed", str(exc))
            report = write_error_report(exc)
            log(f"任务失败：{job_id}: {exc}")
            log(f"Error report: {report}")
            show_error(tr("failed"), f"{exc}\n\nTask ID: {job_id}\nError report:\n{report}")
        else:
            finish_job(job_id, "completed")
            log(f"任务完成：{job_id}")
        finally:
            clear_active_job()
            active_job_id = None
            job_queue.task_done()


def get_reference_map():
    return {key: view_vars[key].get().strip() for key in VIEW_KEYS}


def build_image_paths_for_agent(result_dir, final_input, copied_refs):
    image_paths = {"front": str(final_input)}
    image_paths.update({view: str(path) for view, path in copied_refs.items()})
    return image_paths


def run_backend_with_auto_repair(
    selected_backend,
    image_paths_for_agent,
    result_dir,
    safe_input,
    triposr_output_dir,
    intent="",
    allow_fallback=True,
):
    current_backend = selected_backend
    triposr_resolutions = [384, 256, 128]
    last_error = None
    fallback_reason = ""

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        try:
            log(f"Backend attempt {attempt}/{MAX_REPAIR_ATTEMPTS}: {current_backend}")
            if current_backend == BACKEND_CRAFTSMAN:
                log("CraftsMan is starting with the device configured in config.json.")
                return (
                    run_craftsman_backend(safe_input, result_dir),
                    BACKEND_CRAFTSMAN,
                    fallback_reason,
                )

            if current_backend == BACKEND_EXTERNAL_MULTIVIEW:
                log("External Multi-View may take several minutes on CPU. The window will stay responsive while it runs.")
                return (
                    run_external_multiview_backend(image_paths_for_agent, result_dir),
                    current_backend,
                    fallback_reason,
                )

            if current_backend == BACKEND_TRIPOSR_FUSION:
                resolution = triposr_resolutions[min(attempt - 1, len(triposr_resolutions) - 1)]
                log(f"TripoSR Fusion mc-resolution: {resolution}")
                return (
                    run_triposr_fusion_backend(
                        image_paths_for_agent,
                        result_dir,
                        mc_resolution=resolution,
                    ),
                    BACKEND_TRIPOSR_FUSION,
                    fallback_reason,
                )

            resolution = triposr_resolutions[min(attempt - 1, len(triposr_resolutions) - 1)]
            log(f"TripoSR mc-resolution: {resolution}")
            return (
                run_triposr_backend(
                    safe_input, triposr_output_dir, mc_resolution=resolution
                ),
                BACKEND_TRIPOSR,
                fallback_reason,
            )
        except TaskCancelledError:
            raise
        except Exception as exc:
            last_error = exc
            report = analyze_error_message(str(exc))
            record_stage(
                f"backend_repair_decision_{attempt}",
                output=json.dumps(report, ensure_ascii=False, indent=2),
                error=str(exc),
            )
            log("Backend failed. Auto-repair analysis:")
            for category in report.get("categories", []):
                log(f"- category: {category}")
            for action in report.get("actions", []):
                log(f"- action: {action}")

            if not allow_fallback:
                raise RuntimeError(
                    f"{current_backend} failed and automatic fallback is disabled.\n{exc}"
                ) from exc
            if attempt >= MAX_REPAIR_ATTEMPTS:
                break

            if current_backend == BACKEND_CRAFTSMAN:
                fallback_reason = f"CraftsMan failed: {exc}"
                current_backend = BACKEND_TRIPOSR
                log("Auto-repair: CraftsMan failed, falling back to TripoSR.")
            elif current_backend == BACKEND_EXTERNAL_MULTIVIEW:
                fallback_reason = f"External Multi-View failed: {exc}"
                current_backend = BACKEND_TRIPOSR
                log("Auto-repair: falling back to TripoSR for the next attempt.")
            else:
                if not fallback_reason:
                    fallback_reason = (
                        f"{current_backend} failed at the original resolution and "
                        f"was retried with safer settings: {exc}"
                    )
                log("Auto-repair: retrying TripoSR with safer lower-resolution settings.")

    raise RuntimeError(f"Backend auto-repair failed after {MAX_REPAIR_ATTEMPTS} attempts.\nLast error:\n{last_error}")


def run_blender_and_check_with_auto_repair(
    final_obj,
    final_blend,
    blender_intent,
    result_dir,
    action_plan,
):
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
            action_plan=action_plan,
        )

        latest_check = check_generation_outputs(result_dir)
        if latest_check["ok"]:
            return latest_code, latest_check

        log("Model check failed. Auto-repair analysis:")
        for problem in latest_check.get("problems", []):
            log(f"- {problem}")

        repair_report = analyze_error_message("\n".join(latest_check.get("problems", [])), latest_check)
        record_stage(
            f"blender_observe_and_repair_{attempt}",
            output=json.dumps(repair_report, ensure_ascii=False, indent=2),
            error="\n".join(latest_check.get("problems", [])),
        )
        for action in repair_report.get("actions", []):
            log(f"- repair action: {action}")

        if attempt >= MAX_REPAIR_ATTEMPTS:
            break

        current_intent = build_repair_intent(blender_intent, repair_report, latest_check)
        log("Auto-repair: regenerating Blender script and rerunning.")

    return latest_code, latest_check


def generate_3d(
    image_path,
    intent,
    ref_map=None,
    job_id=None,
    allow_fallback=True,
    requested_backend_override=None,
):
    global current_result_dir, current_blend, current_obj
    ref_map = ref_map or {}

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"{tr('no_image')}\n{image_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_suffix = f"_{job_id[-6:]}" if job_id else ""
    result_dir = DESKTOP / f"Generated_3D_Model_{timestamp}{job_suffix}"
    result_dir.mkdir(parents=True, exist_ok=True)
    if job_id:
        set_active_job(job_id, result_dir)
        update_job(job_id, result_dir=str(result_dir))
        log(f"Task ID: {job_id}")
    current_result_dir = result_dir
    set_progress(5, f"Output folder: {result_dir}")

    with task_stage("prepare_inputs"):
        work_dir = WORK_ROOT / f"job_{timestamp}{job_suffix}"
        work_dir.mkdir(parents=True, exist_ok=True)
        safe_input = work_dir / "input_front.png"
        shutil.copy2(image_path, safe_input)
        triposr_output_dir = work_dir / "triposr_output"
        final_input = result_dir / "input_front.png"
        shutil.copy2(image_path, final_input)
        copied_refs = copy_reference_images(ref_map, result_dir)
        image_paths_for_agent = build_image_paths_for_agent(
            result_dir, final_input, copied_refs
        )

    set_progress(15, tr("step1"))
    log(f"{tr('request')}: {intent or tr('default_request')}")
    requested_backend = requested_backend_override or backend_var.get()
    log(tr("api_hint"))
    log(f"Requested backend: {requested_backend}")

    with task_stage("vision_analysis_and_planning"):
        analysis = analyze_request(intent, image_paths_for_agent)
        plan = create_modeling_plan(
            intent, image_paths_for_agent, analysis, requested_backend
        )
        analysis["agent_plan"] = plan
        selected_backend = plan["backend"]
        action_plan = build_action_plan(intent, analysis)
        action_plan_path = save_action_plan(result_dir, action_plan)
        analysis["blender_action_plan"] = action_plan
        analysis_path = save_agent_analysis(result_dir, analysis)
    log(f"agent_analysis.json: {analysis_path}")
    log(f"blender_action_plan.json: {action_plan_path}")
    analysis_mode = analysis.get("mode", "local_rules")
    mode_text = (
        "视觉模型模式"
        if analysis_mode.startswith("openai") or analysis_mode == "vision_api"
        else "规则模式：不具备图片内容理解能力"
    )
    mode_text = get_analysis_capability()["label"]
    if analysis_mode == "local_rules_after_vision_error":
        mode_text = "规则模式：视觉 API 调用失败，已退回规则分析"
    root.after(0, lambda text=mode_text: vision_mode_var.set(text))
    log(f"Analysis mode: {analysis_mode}")
    log(f"Agent selected backend: {selected_backend}")
    for reason in plan.get("reasons", []):
        log(f"- {reason}")
    for warning in plan.get("warnings", []):
        log(f"Warning: {warning}")
    set_progress(30)

    set_progress(35, tr("step2"))
    with task_stage("backend_generation"):
        obj_path, actual_backend, fallback_reason = run_backend_with_auto_repair(
            selected_backend,
            image_paths_for_agent,
            result_dir,
            safe_input,
            triposr_output_dir,
            intent,
            allow_fallback=allow_fallback,
        )
    selected_backend = actual_backend
    backend_details = (
        get_last_backend_details() if actual_backend == BACKEND_CRAFTSMAN else {}
    )
    execution = {
        "requested_backend": requested_backend,
        "planned_backend": plan["backend"],
        "actual_backend": actual_backend,
        "fallback_reason": fallback_reason,
        "fallback_allowed": allow_fallback,
        "backend_details": backend_details,
    }
    (result_dir / "backend_execution.json").write_text(
        json.dumps(execution, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    plan["actual_backend"] = actual_backend
    plan["fallback_reason"] = fallback_reason
    analysis["backend_execution"] = execution
    analysis_path = save_agent_analysis(result_dir, analysis)
    status_text = f"请求：{requested_backend} | 实际：{actual_backend}"
    if fallback_reason:
        short_reason = fallback_reason.splitlines()[0][:180]
        status_text += f" | 降级原因：{short_reason}"
    status_text = f"请求后端：{requested_backend} | 实际后端：{actual_backend}"
    if fallback_reason:
        status_text += f" | 降级原因：{fallback_reason.splitlines()[0][:180]}"
    root.after(0, lambda text=status_text: backend_status_var.set(text))
    log(f"Actual backend: {actual_backend}")
    if fallback_reason:
        log(f"Fallback reason: {fallback_reason}")
    if backend_details:
        log(f"Backend engine: {backend_details.get('engine')}")
    if job_id:
        update_job(
            job_id,
            actual_backend=actual_backend,
            fallback_reason=fallback_reason,
        )
    set_progress(70)

    final_blend = result_dir / "result.blend"
    blender_intent = build_modeling_intent(intent or tr("default_request"), analysis, copied_refs)
    if selected_backend == BACKEND_TRIPOSR_FUSION:
        final_obj = result_dir / "mesh.obj"
        set_progress(75, "Step 3: TripoSR Fusion mesh alignment and voxel remesh")
        with task_stage("blender_fusion"):
            user_code = run_blender_triposr_fusion(
                obj_path,
                final_blend,
                image_paths_for_agent,
                intent=intent or tr("default_request"),
                log_callback=log,
            )
        fused_obj = result_dir / "fused_mesh.obj"
        if fused_obj.exists():
            shutil.copy2(fused_obj, final_obj)
        with task_stage("structured_blender_actions"):
            structured_code = run_blender_with_repair(
                final_obj,
                final_blend,
                blender_intent,
                open_existing=True,
                log_callback=log,
                max_script_attempts=1,
                action_plan=action_plan,
            )
            user_code += "\n\n" + structured_code
        with task_stage("visual_quality_and_validation"):
            check = check_generation_outputs(result_dir)
    else:
        final_obj = result_dir / f"mesh{obj_path.suffix.lower()}"
        shutil.copy2(obj_path, final_obj)
        set_progress(75, tr("step3"))
        with task_stage("blender_execute_observe_repair"):
            user_code, check = run_blender_and_check_with_auto_repair(
                final_obj,
                final_blend,
                blender_intent,
                result_dir,
                action_plan,
            )
    set_progress(95)
    if not check["ok"]:
        log("Model check warnings after auto-repair:")
        for problem in check.get("problems", []):
            log(f"- {problem}")

    with task_stage("refinement_report"):
        refinement_report, refinement_tools = write_refinement_report(
            result_dir,
            {
                "blend": final_blend,
                "obj": final_obj,
                "glb": result_dir / "model.glb",
                "fbx": result_dir / "model.fbx",
                "stl": result_dir / "model.stl",
            },
        )
    log(f"Free refinement tools report: {refinement_report}")
    for tool_name, info in refinement_tools.items():
        status = "installed" if info.get("installed") else "not installed"
        log(f"- {tool_name}: {status}")

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
            "actual_backend": actual_backend,
            "fallback_reason": fallback_reason,
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


def modify_current_model(intent, source_blend=None, source_obj=None):
    global current_blend, current_obj

    if source_blend:
        current_blend = Path(source_blend)
    if source_obj:
        current_obj = Path(source_obj)

    if not current_blend or not Path(current_blend).exists():
        raise FileNotFoundError(tr("no_blend"))

    timestamp = datetime.now().strftime("%H%M%S")
    result_dir = Path(current_blend).parent
    if active_job_id:
        set_active_job(active_job_id, result_dir)
        update_job(active_job_id, result_dir=str(result_dir))
    next_blend = result_dir / f"result_modified_{timestamp}.blend"
    copied_refs = copy_reference_images(get_reference_map(), result_dir)

    image_paths_for_agent = {"front": str(result_dir / "input_front.png")}
    image_paths_for_agent.update({view: str(path) for view, path in copied_refs.items()})
    with task_stage("modify_analysis_and_planning"):
        analysis = analyze_request(intent, image_paths_for_agent)
        analysis_path = save_agent_analysis(result_dir, analysis)
        blender_intent = build_modeling_intent(intent, analysis, copied_refs)
        action_plan = build_action_plan(intent, analysis)
        save_action_plan(result_dir, action_plan)

    log(tr("multi"))
    log(f"{tr('request')}: {intent}")
    log(f"agent_analysis.json: {analysis_path}")
    set_progress(40)

    with task_stage("modify_structured_blender_actions"):
        user_code = run_blender_with_repair(
            current_obj,
            next_blend,
            blender_intent,
            open_existing=True,
            log_callback=log,
            attempt_label=tr("attempt"),
            repair_label=tr("repair"),
            action_plan=action_plan,
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


def get_quick_image_dirs():
    candidates = [
        DESKTOP,
        Path.home() / "Pictures",
        Path.home() / "Videos" / "Captures",
        Path.home() / "Downloads",
    ]
    return [path for path in candidates if path.exists()]


def list_images(folder):
    try:
        return [
            path
            for path in sorted(Path(folder).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    except Exception:
        return []


def choose_image_for_var(target_var):
    global last_image_dir
    initial_dir = Path(target_var.get()).parent if target_var.get() else last_image_dir
    if not initial_dir.exists():
        initial_dir = DESKTOP

    file_path = filedialog.askopenfilename(
        title=tr("choose_title"),
        initialdir=str(initial_dir),
        filetypes=[
            (tr("image_files"), "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
            (tr("all_files"), "*.*"),
        ],
    )
    if file_path:
        target_var.set(file_path)
        last_image_dir = Path(file_path).parent


def open_thumbnail_picker(target_var):
    global last_image_dir

    start_dir = Path(target_var.get()).parent if target_var.get() else last_image_dir
    if not start_dir.exists():
        start_dir = DESKTOP

    picker = tk.Toplevel(root)
    picker.title(tr("choose_title"))
    picker.geometry("980x680")
    picker.transient(root)
    picker.grab_set()

    current_dir_var = tk.StringVar(value=str(start_dir))
    selected_path_var = tk.StringVar(value="")
    thumbnail_refs = []

    top = tk.Frame(picker)
    top.pack(fill="x", padx=12, pady=10)

    tk.Label(top, text="文件夹").pack(side="left")
    dir_entry = tk.Entry(top, textvariable=current_dir_var)
    dir_entry.pack(side="left", fill="x", expand=True, padx=8)

    def choose_folder():
        folder = filedialog.askdirectory(title="选择图片文件夹", initialdir=current_dir_var.get())
        if folder:
            current_dir_var.set(folder)
            refresh_grid()

    tk.Button(top, text="选择文件夹", command=choose_folder).pack(side="left", padx=(0, 6))
    tk.Button(top, text="刷新", command=lambda: refresh_grid()).pack(side="left")

    quick = tk.Frame(picker)
    quick.pack(fill="x", padx=12, pady=(0, 8))
    for folder in get_quick_image_dirs():
        label = folder.name if folder != DESKTOP else "桌面"
        tk.Button(
            quick,
            text=label,
            command=lambda p=folder: (current_dir_var.set(str(p)), refresh_grid()),
        ).pack(side="left", padx=(0, 6))

    canvas = tk.Canvas(picker, highlightthickness=0)
    scrollbar = ttk.Scrollbar(picker, orient="vertical", command=canvas.yview)
    grid = tk.Frame(canvas)
    grid_window = canvas.create_window((0, 0), window=grid, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 8))
    scrollbar.pack(side="right", fill="y", padx=(0, 12), pady=(0, 8))

    def on_grid_configure(event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def on_canvas_configure(event):
        canvas.itemconfigure(grid_window, width=event.width)

    grid.bind("<Configure>", on_grid_configure)
    canvas.bind("<Configure>", on_canvas_configure)

    bottom = tk.Frame(picker)
    bottom.pack(fill="x", padx=12, pady=(0, 12))
    selected_entry = tk.Entry(bottom, textvariable=selected_path_var)
    selected_entry.pack(side="left", fill="x", expand=True)

    def confirm_selection():
        global last_image_dir
        selected = selected_path_var.get().strip()
        if selected and Path(selected).exists():
            target_var.set(selected)
            last_image_dir = Path(selected).parent
            picker.destroy()

    def open_native_dialog():
        global last_image_dir
        file_path = filedialog.askopenfilename(
            title=tr("choose_title"),
            initialdir=current_dir_var.get(),
            filetypes=[
                (tr("image_files"), "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
                (tr("all_files"), "*.*"),
            ],
        )
        if file_path:
            target_var.set(file_path)
            last_image_dir = Path(file_path).parent
            picker.destroy()

    tk.Button(bottom, text="打开", width=12, command=confirm_selection).pack(side="left", padx=8)
    tk.Button(bottom, text="系统选择", width=12, command=open_native_dialog).pack(side="left")

    def select_image(path):
        selected_path_var.set(str(path))

    def choose_image(path):
        selected_path_var.set(str(path))
        confirm_selection()

    def refresh_grid():
        for child in grid.winfo_children():
            child.destroy()
        thumbnail_refs.clear()

        folder = Path(current_dir_var.get())
        images = list_images(folder)
        if not images:
            tk.Label(grid, text="这个文件夹里没有图片").grid(row=0, column=0, padx=20, pady=20, sticky="w")
            return

        columns = 4
        for index, image_path in enumerate(images[:240]):
            row = index // columns
            col = index % columns
            item = tk.Frame(grid, width=210, height=190, relief="groove", bd=1)
            item.grid(row=row, column=col, padx=10, pady=10, sticky="n")
            item.grid_propagate(False)

            try:
                image = Image.open(image_path)
                image.thumbnail((180, 120))
                photo = ImageTk.PhotoImage(image)
                thumbnail_refs.append(photo)
                image_label = tk.Label(item, image=photo, cursor="hand2")
            except Exception:
                image_label = tk.Label(item, text="无法预览", width=22, height=7)

            image_label.pack(pady=(8, 4))
            name = image_path.name
            if len(name) > 24:
                name = name[:21] + "..."
            text_label = tk.Label(item, text=name, wraplength=180)
            text_label.pack()

            for widget in (item, image_label, text_label):
                widget.bind("<Button-1>", lambda event, p=image_path: select_image(p))
                widget.bind("<Double-Button-1>", lambda event, p=image_path: choose_image(p))

        if len(images) > 240:
            tk.Label(grid, text="只显示最近 240 张图片，请换文件夹或用系统选择搜索。").grid(
                row=(240 // columns) + 1,
                column=0,
                columnspan=columns,
                padx=10,
                pady=10,
                sticky="w",
            )

    refresh_grid()


def clear_var(target_var):
    target_var.set("")


def _job_payload(job):
    try:
        return json.loads(job.get("payload_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def resume_job(job_id):
    job = get_job(job_id)
    if not job:
        messagebox.showerror("任务管理", f"找不到任务：{job_id}")
        return
    if job["status"] == "running":
        messagebox.showwarning("任务管理", "该任务仍在运行，不能重复启动。")
        return
    if job_id in enqueued_job_ids:
        messagebox.showwarning("任务管理", "该任务已经在等待队列中。")
        return

    payload = _job_payload(job)
    requeue_job(job_id)
    if job["kind"] == "generate":
        def task(current_job_id):
            generate_3d(
                payload.get("image_path", ""),
                payload.get("intent", ""),
                payload.get("ref_map") or {},
                job_id=current_job_id,
                allow_fallback=bool(payload.get("allow_fallback", True)),
                requested_backend_override=(
                    payload.get("requested_backend")
                    or job.get("requested_backend")
                    or BACKEND_TRIPOSR
                ),
            )
    elif job["kind"] == "modify":
        def task(current_job_id):
            modify_current_model(
                payload.get("intent", ""),
                source_blend=payload.get("blend"),
                source_obj=payload.get("obj"),
            )
    else:
        messagebox.showerror("任务管理", f"不支持恢复的任务类型：{job['kind']}")
        return
    enqueue_persistent_job(job_id, task)


def show_task_manager():
    window = tk.Toplevel(root)
    window.title("任务管理")
    window.geometry("1080x620")

    columns = ("id", "kind", "status", "stage", "elapsed", "created")
    tree = ttk.Treeview(window, columns=columns, show="headings", height=14)
    headings = {
        "id": "任务 ID",
        "kind": "类型",
        "status": "状态",
        "stage": "当前阶段",
        "elapsed": "耗时（秒）",
        "created": "创建时间",
    }
    widths = {"id": 190, "kind": 80, "status": 90, "stage": 220, "elapsed": 90, "created": 170}
    for key in columns:
        tree.heading(key, text=headings[key])
        tree.column(key, width=widths[key], anchor="w")
    tree.pack(fill="x", padx=12, pady=(12, 6))

    details = scrolledtext.ScrolledText(window, height=14)
    details.pack(fill="both", expand=True, padx=12, pady=6)

    def selected_job_id():
        selection = tree.selection()
        return tree.item(selection[0], "values")[0] if selection else ""

    def show_details(event=None):
        job_id = selected_job_id()
        details.delete("1.0", tk.END)
        if not job_id:
            return
        job = get_job(job_id) or {}
        lines = [
            f"任务 ID：{job_id}",
            f"请求后端：{job.get('requested_backend') or '-'}",
            f"实际后端：{job.get('actual_backend') or '-'}",
            f"降级原因：{job.get('fallback_reason') or '-'}",
            f"结果目录：{job.get('result_dir') or '-'}",
            f"错误：{job.get('error') or '-'}",
            "",
            "阶段记录：",
        ]
        for stage in list_stages(job_id):
            lines.append(
                f"- {stage['name']} | {stage['status']} | "
                f"{stage.get('elapsed_seconds') or 0:.2f}s"
            )
            if stage.get("command_json"):
                lines.append(f"  命令：{stage['command_json']}")
            if stage.get("error"):
                lines.append(f"  错误：{stage['error']}")
            if stage.get("stdout"):
                lines.append(f"  输出：{stage['stdout'][-1500:]}")
            if stage.get("stderr"):
                lines.append(f"  错误输出：{stage['stderr'][-1500:]}")
        details.insert("1.0", "\n".join(lines))

    def refresh():
        for item in tree.get_children():
            tree.delete(item)
        for job in list_jobs(200):
            tree.insert(
                "",
                "end",
                values=(
                    job["id"],
                    job["kind"],
                    job["status"],
                    job.get("current_stage") or "",
                    f"{job.get('elapsed_seconds') or 0:.2f}",
                    job.get("created_at") or "",
                ),
            )
        window.after(2000, refresh)

    def retry_selected():
        job_id = selected_job_id()
        if not job_id:
            messagebox.showwarning("任务管理", "请先选择一个任务。")
            return
        resume_job(job_id)
        refresh()

    def cancel_selected():
        job_id = selected_job_id()
        if not job_id:
            messagebox.showwarning("任务管理", "请先选择一个任务。")
            return
        job = get_job(job_id) or {}
        if job_id == active_job_id:
            cancel_task()
        elif job.get("status") == "queued":
            finish_job(job_id, "cancelled", "Cancelled before execution.")
        else:
            messagebox.showwarning("任务管理", "只能取消正在运行或排队中的任务。")
        refresh()

    tree.bind("<<TreeviewSelect>>", show_details)
    actions = tk.Frame(window)
    actions.pack(fill="x", padx=12, pady=(0, 12))
    tk.Button(actions, text="刷新", command=refresh).pack(side="left")
    tk.Button(actions, text="恢复 / 重试所选任务", command=retry_selected).pack(side="left", padx=8)
    tk.Button(actions, text="取消所选任务", command=cancel_selected).pack(side="left")
    refresh()


def start_generate():
    image_path = main_image_var.get().strip()
    intent = request_box.get("1.0", tk.END).strip()
    ref_map = get_reference_map()

    payload = {
        "image_path": image_path,
        "intent": intent,
        "ref_map": ref_map,
        "allow_fallback": not disable_fallback_var.get(),
        "requested_backend": backend_var.get(),
    }
    job_id = create_job(
        "generate",
        request_text=intent,
        payload=payload,
        requested_backend=backend_var.get(),
    )

    def task(current_job_id):
        set_progress(0)
        root.after(0, lambda: output_box.delete("1.0", tk.END))
        generate_3d(
            image_path,
            intent,
            ref_map,
            job_id=current_job_id,
            allow_fallback=payload["allow_fallback"],
            requested_backend_override=payload["requested_backend"],
        )

    enqueue_persistent_job(job_id, task)


def start_modify():
    intent = request_box.get("1.0", tk.END).strip()
    if not intent:
        messagebox.showerror(tr("error"), tr("need_request"))
        return

    payload = {
        "intent": intent,
        "blend": str(current_blend or ""),
        "obj": str(current_obj or ""),
    }
    job_id = create_job("modify", request_text=intent, payload=payload)
    enqueue_persistent_job(
        job_id,
        lambda current_job_id: modify_current_model(
            intent,
            source_blend=payload["blend"],
            source_obj=payload["obj"],
        ),
    )


def perform_backend_health_check(show_dialog=False):
    set_progress(0, "正在进行后端启动体检...")
    health = check_backend_health()
    report = format_health_report(health)
    log(report)
    available = [name for name, info in health.items() if info.get("available")]
    summary = "可用：" + (", ".join(available) if available else "无")
    root.after(0, lambda: backend_status_var.set(summary))
    set_progress(0)
    if show_dialog:
        show_info("后端体检", report)


def start_backend_health_check(show_dialog=True):
    run_in_worker(lambda: perform_backend_health_check(show_dialog=show_dialog))


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
    health_button.config(text="后端体检" if LANG == "zh" else "Backend Check")
    cancel_button.config(text="取消当前任务" if LANG == "zh" else "Cancel Current Task")
    task_manager_button.config(text="任务管理" if LANG == "zh" else "Task Manager")
    disable_fallback_check.config(
        text="禁止自动降级" if LANG == "zh" else "Disable automatic fallback"
    )
    vision_prefix_label.config(
        text="图片理解：" if LANG == "zh" else "Image understanding:"
    )
    for key in VIEW_KEYS:
        view_labels[key].config(text=tr(key))
        view_choose_buttons[key].config(text=tr("choose"))
        view_clear_buttons[key].config(text=tr("clear"))
    current_text = request_box.get("1.0", tk.END).strip()
    defaults = {TEXT["zh"]["default_request"], TEXT["en"]["default_request"], ""}
    if current_text in defaults:
        request_box.delete("1.0", tk.END)
        request_box.insert("1.0", tr("default_request"))


recover_interrupted_jobs()
root = tk.Tk()
root.title(tr("title"))
root.geometry("1120x820")

main_image_var = tk.StringVar()
view_vars = {key: tk.StringVar() for key in VIEW_KEYS}
language_var = tk.StringVar(value=TEXT["zh"]["chinese"])
progress_var = tk.IntVar(value=0)
backend_var = tk.StringVar(
    value=DEFAULT_BACKEND
    if DEFAULT_BACKEND
    in {
        BACKEND_CRAFTSMAN,
        BACKEND_AUTO,
        BACKEND_TRIPOSR_FUSION,
        BACKEND_TRIPOSR,
        BACKEND_EXTERNAL_MULTIVIEW,
    }
    else BACKEND_TRIPOSR
)
backend_status_var = tk.StringVar(value="后端尚未体检")
disable_fallback_var = tk.BooleanVar(
    value=not bool(get_runtime("allow_backend_fallback", True))
)
backend_status_var.set("后端尚未体检")
vision_mode_var = tk.StringVar(value=get_analysis_capability()["label"])
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
    values=[BACKEND_CRAFTSMAN, BACKEND_AUTO, BACKEND_TRIPOSR_FUSION, BACKEND_TRIPOSR, BACKEND_EXTERNAL_MULTIVIEW],
    state="readonly",
    width=24,
)
backend_box.pack(side="left", padx=8)
disable_fallback_check = tk.Checkbutton(
    backend_frame,
    text="禁止自动降级",
    variable=disable_fallback_var,
)
disable_fallback_check.pack(side="left", padx=6)
health_button = tk.Button(
    backend_frame,
    text="后端体检",
    command=lambda: start_backend_health_check(show_dialog=True),
)
health_button.pack(side="left", padx=8)
tk.Label(backend_frame, textvariable=backend_status_var, anchor="w").pack(
    side="left", fill="x", expand=True, padx=8
)

capability_frame = tk.Frame(root)
capability_frame.pack(fill="x", padx=16, pady=(0, 8))
vision_prefix_label = tk.Label(capability_frame, text="图片理解：")
vision_prefix_label.pack(side="left")
tk.Label(capability_frame, textvariable=vision_mode_var, anchor="w").pack(
    side="left", fill="x", expand=True
)

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
cancel_button = tk.Button(
    btn_row,
    text="取消任务",
    width=14,
    command=cancel_task,
    state="disabled",
)
cancel_button.pack(side="left", padx=8)
open_folder_button = tk.Button(btn_row, text=tr("open_folder"), width=18, command=open_result_folder)
open_folder_button.pack(side="left", padx=8)
task_manager_button = tk.Button(
    btn_row, text="任务管理", width=12, command=show_task_manager
)
task_manager_button.pack(side="left", padx=8)

log_label = tk.Label(root, text=tr("agent_log"))
log_label.pack(anchor="w", padx=16)
progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
progress_bar.pack(fill="x", padx=16, pady=(0, 8))
output_box = scrolledtext.ScrolledText(root, height=15)
output_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))

apply_language()
root.after(500, lambda: start_backend_health_check(show_dialog=False))
root.mainloop()
