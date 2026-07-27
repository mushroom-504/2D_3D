import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path

from config_loader import get_path, get_runtime, get_timeout


TRIPOSR_PYTHON = get_path("triposr_python")
TRIPOSR_DIR = get_path("triposr_dir")
CRAFTSMAN_PYTHON = get_path("craftsman_python")
CRAFTSMAN_DIR = get_path("craftsman_dir")
CRAFTSMAN_MODEL_DIR = get_path("craftsman_model")
MAST3R_PYTHON = get_path("mast3r_python")
MULTIVIEW_SCRIPT = get_path("multiview_script")
WORK_ROOT = get_path("work_root")

BACKEND_AUTO = "Auto"
BACKEND_CRAFTSMAN = "CraftsMan"
BACKEND_TRIPOSR = "TripoSR"
BACKEND_TRIPOSR_ENHANCED = "TripoSR Enhanced"
BACKEND_TRIPOSR_FUSION = "TripoSR Fusion"
BACKEND_EXTERNAL_MULTIVIEW = "External Multi-View"

DEFAULT_PROCESS_TIMEOUT = get_timeout("default_process")
TRIPOSR_TIMEOUT = get_timeout("triposr")
CRAFTSMAN_TIMEOUT = get_timeout("craftsman")
MULTIVIEW_TIMEOUT = get_timeout("multiview")
TERMINATE_GRACE_SECONDS = int(get_runtime("terminate_grace_seconds", 5))
CRAFTSMAN_DEVICE = str(get_runtime("craftsman_device", "cuda"))
CRAFTSMAN_DTYPE = str(get_runtime("craftsman_dtype", "float32"))


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
    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        start_new_session = True

    process = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=capture_output,
        encoding="utf-8" if capture_output else None,
        errors="replace" if capture_output else None,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )
    _set_current_process(process)
    stdout = None
    stderr = None
    try:
        if capture_output:
            stdout, stderr = process.communicate(timeout=timeout)
        else:
            process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        if capture_output:
            stdout, stderr = process.communicate()
        raise TimeoutError(
            f"Command timed out after {timeout} seconds: {' '.join(map(str, cmd))}"
        ) from exc
    finally:
        _clear_current_process(process)

    if is_cancel_requested():
        raise TaskCancelledError("Task cancelled by user.")
    if process.returncode != 0:
        detail = ""
        if capture_output:
            detail = f"\nstdout:\n{(stdout or '')[-2000:]}\nstderr:\n{(stderr or '')[-2000:]}"
        raise RuntimeError(
            f"Command failed with code {process.returncode}: {' '.join(map(str, cmd))}{detail}"
        )
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


def run_craftsman_backend(safe_input, result_dir):
    if not CRAFTSMAN_PYTHON.is_file():
        raise RuntimeError(f"CraftsMan Python environment not found: {CRAFTSMAN_PYTHON}")
    if not (CRAFTSMAN_DIR / "craftsman" / "__init__.py").is_file():
        raise RuntimeError(f"CraftsMan source package not found: {CRAFTSMAN_DIR}")
    if not (CRAFTSMAN_MODEL_DIR / "config.yaml").is_file():
        raise RuntimeError(f"CraftsMan config missing: {CRAFTSMAN_MODEL_DIR / 'config.yaml'}")
    if not (CRAFTSMAN_MODEL_DIR / "model.ckpt").is_file():
        raise RuntimeError(f"CraftsMan checkpoint missing: {CRAFTSMAN_MODEL_DIR / 'model.ckpt'}")

    runner = Path(__file__).with_name("craftsman_runner.py")
    output_dir = Path(result_dir) / "craftsman_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_obj = output_dir / "mesh.obj"
    run_command(
        [
            CRAFTSMAN_PYTHON,
            runner,
            "--input",
            safe_input,
            "--output",
            output_obj,
            "--craftsman-root",
            CRAFTSMAN_DIR,
            "--model-dir",
            CRAFTSMAN_MODEL_DIR,
            "--device",
            CRAFTSMAN_DEVICE,
            "--dtype",
            CRAFTSMAN_DTYPE,
        ],
        cwd=CRAFTSMAN_DIR,
        timeout=CRAFTSMAN_TIMEOUT,
    )
    if not output_obj.is_file() or output_obj.stat().st_size == 0:
        raise RuntimeError(f"CraftsMan did not create an OBJ: {output_obj}")
    return output_obj


def run_triposr_fusion_backend(image_paths_for_agent, result_dir, mc_resolution=384):
    result_dir = Path(result_dir)
    fusion_dir = result_dir / "triposr_fusion_meshes"
    fusion_dir.mkdir(parents=True, exist_ok=True)

    mesh_paths = {}
    for view in ["front", "back", "left", "right", "top", "bottom"]:
        raise_if_cancelled()
        image_path = (image_paths_for_agent or {}).get(view)
        if not image_path:
            continue
        image_path = Path(image_path)
        if not image_path.exists():
            continue

        view_output_dir = fusion_dir / f"{view}_triposr_output"
        obj_path = run_triposr_backend(
            image_path, view_output_dir, mc_resolution=mc_resolution
        )
        copied_obj = fusion_dir / f"{view}_mesh.obj"
        shutil.copy2(obj_path, copied_obj)
        mesh_paths[view] = copied_obj

    if "front" not in mesh_paths:
        raise RuntimeError("TripoSR Fusion needs a front image.")
    if len(mesh_paths) < 2:
        raise RuntimeError("TripoSR Fusion needs front plus at least one reference image.")
    return mesh_paths


def run_external_multiview_backend(image_paths_for_agent, result_dir):
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
