import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

from config_loader import get_path, get_runtime, get_section, get_timeout
from task_manager import finish_stage, start_stage


TRIPOSR_PYTHON = get_path("triposr_python")
TRIPOSR_DIR = get_path("triposr_dir")
MAST3R_PYTHON = get_path("mast3r_python")
MULTIVIEW_SCRIPT = get_path("multiview_script")
WORK_ROOT = get_path("work_root")

BACKEND_AUTO = "Auto"
BACKEND_CRAFTSMAN = "CraftsMan 远程服务"
BACKEND_TRIPOSR = "TripoSR"
BACKEND_TRIPOSR_ENHANCED = "TripoSR Enhanced"
BACKEND_EXTERNAL_MULTIVIEW = "External Multi-View"

DEFAULT_PROCESS_TIMEOUT = get_timeout("default_process")
TRIPOSR_TIMEOUT = get_timeout("triposr")
MULTIVIEW_TIMEOUT = get_timeout("multiview")
TERMINATE_GRACE_SECONDS = int(get_runtime("terminate_grace_seconds", 5))
CRAFTSMAN_API_TIMEOUT = get_timeout("craftsman_api")
CRAFTSMAN_API_CONFIG = get_section("craftsman_api")
EXTERNAL_MULTIVIEW_CONFIG = get_section("external_multiview")
_last_backend_details = {}


class TaskCancelledError(RuntimeError):
    pass


_process_lock = threading.RLock()
_cancel_event = threading.Event()
_current_process = None


def clear_cancel_request():
    _cancel_event.clear()


def is_cancel_requested():
    return _cancel_event.is_set()


def raise_if_cancelled():
    if is_cancel_requested():
        raise TaskCancelledError("Task cancelled by user.")


def _set_current_process(process):
    global _current_process
    with _process_lock:
        _current_process = process


def _clear_current_process(process):
    global _current_process
    with _process_lock:
        if _current_process is process:
            _current_process = None


def _terminate_process_tree(process):
    if process is None or process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=TERMINATE_GRACE_SECONDS)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


def stop_current_process():
    _cancel_event.set()
    with _process_lock:
        process = _current_process
    _terminate_process_tree(process)


def run_command(
    cmd,
    cwd=None,
    env=None,
    timeout=None,
    capture_output=False,
):
    raise_if_cancelled()
    timeout = timeout or DEFAULT_PROCESS_TIMEOUT
    command_parts = [str(part) for part in cmd]
    stage_token = start_stage(
        f"command:{Path(command_parts[0]).name}",
        command=command_parts,
    )
    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        start_new_session = True

    try:
        process = subprocess.Popen(
            command_parts,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
    except Exception as exc:
        finish_stage(stage_token, "failed", error=str(exc))
        raise
    _set_current_process(process)
    stdout = None
    stderr = None
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        error = (
            f"Command timed out after {timeout} seconds: {' '.join(map(str, cmd))}"
        )
        finish_stage(stage_token, "failed", stdout, stderr, error)
        raise TimeoutError(error) from exc
    finally:
        _clear_current_process(process)

    if is_cancel_requested():
        finish_stage(stage_token, "cancelled", stdout, stderr, "Task cancelled by user.")
        raise TaskCancelledError("Task cancelled by user.")
    if process.returncode != 0:
        detail = f"\nstdout:\n{(stdout or '')[-2000:]}\nstderr:\n{(stderr or '')[-2000:]}"
        error = (
            f"Command failed with code {process.returncode}: "
            f"{' '.join(map(str, cmd))}{detail}"
        )
        finish_stage(stage_token, "failed", stdout, stderr, error)
        raise RuntimeError(error)
    finish_stage(stage_token, "completed", stdout, stderr)
    if not capture_output:
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def copy_reference_images(ref_map, result_dir):
    refs_dir = Path(result_dir) / "reference_images"
    refs_dir.mkdir(parents=True, exist_ok=True)
    copied_refs = {}
    for view_key, ref in ref_map.items():
        raise_if_cancelled()
        if not ref:
            continue
        ref_path = Path(ref)
        if ref_path.exists():
            ext = ref_path.suffix.lower()
            dst = refs_dir / f"{view_key}{ext}"
            shutil.copy2(ref_path, dst)
            copied_refs[view_key] = dst
    return copied_refs


def run_triposr_backend(safe_input, triposr_output_dir, mc_resolution=384):
    if not TRIPOSR_PYTHON.is_file():
        raise RuntimeError(f"TripoSR Python environment not found: {TRIPOSR_PYTHON}")
    if not (TRIPOSR_DIR / "run.py").is_file():
        raise RuntimeError(f"TripoSR source not found: {TRIPOSR_DIR}")
    run_command(
        [
            TRIPOSR_PYTHON,
            "run.py",
            safe_input,
            "--output-dir",
            triposr_output_dir,
            "--mc-resolution",
            str(mc_resolution),
        ],
        cwd=TRIPOSR_DIR,
        timeout=TRIPOSR_TIMEOUT,
    )
    obj_path = Path(triposr_output_dir) / "0" / "mesh.obj"
    if not obj_path.is_file() or obj_path.stat().st_size == 0:
        raise RuntimeError(f"OBJ file not found or empty: {obj_path}")
    return obj_path


def run_craftsman_backend(image_paths_for_agent, intent, result_dir):
    global _last_backend_details
    if isinstance(image_paths_for_agent, (str, os.PathLike)):
        image_paths_for_agent = {"front": str(image_paths_for_agent)}
    image_paths_for_agent = {
        view: Path(path)
        for view, path in (image_paths_for_agent or {}).items()
        if view in {"front", "back", "left", "right", "top", "bottom"} and path
    }
    front = image_paths_for_agent.get("front")
    if not front or not front.is_file():
        raise RuntimeError("CraftsMan 至少需要一张有效的主图片（front）。")

    output_dir = Path(result_dir) / "craftsman_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_obj = output_dir / "mesh.obj"
    runner = Path(__file__).with_name("craftsman_api_runner.py")
    if not CRAFTSMAN_API_CONFIG.get("enabled", False):
        raise RuntimeError("CraftsMan remote API is disabled in config.json.")
    command = [
        TRIPOSR_PYTHON,
        runner,
        "--front",
        front,
        "--output",
        output_obj,
        "--timeout",
        str(CRAFTSMAN_API_TIMEOUT),
        "--prompt",
        str(intent or ""),
    ]
    for view in ("back", "left", "right", "top", "bottom"):
        path = image_paths_for_agent.get(view)
        if path and path.is_file():
            command.extend([f"--{view}", path])
    run_command(
        command,
        cwd=Path(__file__).parent,
        timeout=CRAFTSMAN_API_TIMEOUT + 30,
    )
    if not output_obj.is_file() or output_obj.stat().st_size == 0:
        raise RuntimeError("CraftsMan remote service did not create an OBJ file.")
    metadata_path = output_obj.with_suffix(".api.json")
    metadata = {}
    if metadata_path.is_file():
        import json

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    _last_backend_details = {"engine": "remote_api", **metadata}
    return output_obj


def get_last_backend_details():
    return dict(_last_backend_details)


def run_external_multiview_backend(image_paths_for_agent, result_dir):
    if not bool(EXTERNAL_MULTIVIEW_CONFIG.get("enabled", False)):
        raise RuntimeError(
            "External Multi-View is disabled in config.json. "
            "This optional experimental backend does not affect TripoSR or CraftsMan."
        )
    if not MAST3R_PYTHON.is_file():
        raise RuntimeError(f"MASt3R Python environment not found: {MAST3R_PYTHON}")
    if not MULTIVIEW_SCRIPT.is_file():
        raise RuntimeError(f"Multi-view runner not found: {MULTIVIEW_SCRIPT}")

    output_dir = Path(result_dir) / "multiview_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [MAST3R_PYTHON, MULTIVIEW_SCRIPT, "--output-dir", output_dir]
    for view, path in image_paths_for_agent.items():
        if path and Path(path).exists():
            command.extend([f"--{view}", path])
    run_command(command, timeout=MULTIVIEW_TIMEOUT)

    candidates = []
    for name in ("scene", "model", "mesh"):
        for suffix in (".obj", ".glb", ".gltf", ".ply"):
            candidates.append(output_dir / f"{name}{suffix}")
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    for suffix in [".glb", ".obj", ".gltf", ".ply"]:
        matches = sorted(
            output_dir.rglob(f"*{suffix}"),
            key=lambda path: path.stat().st_size,
            reverse=True,
        )
        if matches:
            return matches[0]
    raise RuntimeError(
        "External Multi-View finished, but no OBJ/GLB/GLTF/PLY file was found "
        f"under {output_dir}."
    )
