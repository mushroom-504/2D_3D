import json
from pathlib import Path

from backend_manager import (
    BACKEND_CRAFTSMAN,
    BACKEND_EXTERNAL_MULTIVIEW,
    BACKEND_TRIPOSR,
    BACKEND_TRIPOSR_FUSION,
    CRAFTSMAN_DIR,
    CRAFTSMAN_MODEL_DIR,
    CRAFTSMAN_PYTHON,
    MAST3R_PYTHON,
    MULTIVIEW_SCRIPT,
    TRIPOSR_DIR,
    TRIPOSR_PYTHON,
    run_command,
)
from config_loader import get_path, get_timeout


BLENDER_EXE = get_path("blender_exe")
MAST3R_DIR = get_path("mast3r_dir")
HEALTH_TIMEOUT = get_timeout("health_probe")
MIN_CHECKPOINT_BYTES = 1024 * 1024


def _status(available, reason, **details):
    return {"available": bool(available), "reason": str(reason), **details}


def _probe_python(python_exe, code, cwd=None):
    if not Path(python_exe).is_file():
        return False, f"Python executable not found: {python_exe}"
    try:
        completed = run_command(
            [python_exe, "-B", "-c", code],
            cwd=cwd,
            timeout=HEALTH_TIMEOUT,
            capture_output=True,
        )
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
        )
        return True, output or "OK"
    except Exception as exc:
        return False, str(exc)


def _check_triposr():
    run_file = TRIPOSR_DIR / "run.py"
    if not run_file.is_file():
        return _status(False, f"TripoSR run.py missing: {run_file}")
    ok, reason = _probe_python(
        TRIPOSR_PYTHON,
        "import torch; import tsr; "
        "print('torch=' + torch.__version__); "
        "print('cuda=' + str(torch.cuda.is_available()))",
        cwd=TRIPOSR_DIR,
    )
    return _status(
        ok,
        reason,
        python=str(TRIPOSR_PYTHON),
        source=str(TRIPOSR_DIR),
    )


def _check_craftsman():
    package = CRAFTSMAN_DIR / "craftsman" / "__init__.py"
    config = CRAFTSMAN_MODEL_DIR / "config.yaml"
    checkpoint = CRAFTSMAN_MODEL_DIR / "model.ckpt"
    missing = [
        str(path)
        for path in (package, config, checkpoint)
        if not path.is_file()
    ]
    if missing:
        return _status(False, "Missing CraftsMan files: " + "; ".join(missing))
    if checkpoint.stat().st_size < MIN_CHECKPOINT_BYTES:
        return _status(False, f"CraftsMan checkpoint is incomplete: {checkpoint}")

    root_literal = json.dumps(str(CRAFTSMAN_DIR))
    code = (
        "import sys, torch; "
        f"sys.path.insert(0, {root_literal}); "
        "from craftsman import CraftsManPipeline; "
        "assert torch.cuda.is_available(), 'CUDA is unavailable'; "
        "print('torch=' + torch.__version__); "
        "print('gpu=' + torch.cuda.get_device_name(0)); "
        "print('CraftsManPipeline=OK')"
    )
    ok, reason = _probe_python(CRAFTSMAN_PYTHON, code, cwd=CRAFTSMAN_DIR)
    return _status(
        ok,
        reason,
        source_files_ok=True,
        model_files_ok=True,
        python=str(CRAFTSMAN_PYTHON),
        source=str(CRAFTSMAN_DIR),
        model=str(CRAFTSMAN_MODEL_DIR),
    )


def _check_multiview():
    if not MULTIVIEW_SCRIPT.is_file():
        return _status(False, f"Runner missing: {MULTIVIEW_SCRIPT}")
    if not MAST3R_DIR.is_dir():
        return _status(False, f"MASt3R source missing: {MAST3R_DIR}")
    root_literal = json.dumps(str(MAST3R_DIR))
    code = (
        "import sys, torch; "
        f"sys.path.insert(0, {root_literal}); "
        "from mast3r.model import AsymmetricMASt3R; "
        "print('torch=' + torch.__version__); "
        "print('cuda=' + str(torch.cuda.is_available())); "
        "print('mast3r=OK')"
    )
    ok, reason = _probe_python(MAST3R_PYTHON, code, cwd=MAST3R_DIR)
    return _status(
        ok,
        reason,
        python=str(MAST3R_PYTHON),
        source=str(MAST3R_DIR),
    )


def check_backend_health():
    triposr = _check_triposr()
    craftsman = _check_craftsman()
    multiview = _check_multiview()
    blender = _status(
        BLENDER_EXE.is_file(),
        "OK" if BLENDER_EXE.is_file() else f"Blender not found: {BLENDER_EXE}",
        executable=str(BLENDER_EXE),
    )
    return {
        BACKEND_TRIPOSR: triposr,
        BACKEND_TRIPOSR_FUSION: _status(
            triposr["available"],
            triposr["reason"],
            dependency=BACKEND_TRIPOSR,
        ),
        BACKEND_CRAFTSMAN: craftsman,
        BACKEND_EXTERNAL_MULTIVIEW: multiview,
        "Blender": blender,
    }


def format_health_report(health):
    lines = []
    for name, info in health.items():
        marker = "[OK]" if info.get("available") else "[X]"
        reason = info.get("reason", "")
        if len(reason) > 300:
            reason = reason[-300:]
        lines.append(f"{marker} {name}: {reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_health_report(check_backend_health()))
