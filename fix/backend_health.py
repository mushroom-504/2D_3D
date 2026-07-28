import json
from pathlib import Path

from backend_manager import (
    BACKEND_CRAFTSMAN,
    BACKEND_EXTERNAL_MULTIVIEW,
    BACKEND_TRIPOSR,
    BACKEND_TRIPOSR_FUSION,
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
    remote_ok = False
    remote_reason = ""
    try:
        from craftsman_api_runner import check_health

        remote_health = check_health(timeout=HEALTH_TIMEOUT)
        remote_ok = remote_health.get("status") == "ok"
        remote_reason = (
            f"status={remote_health.get('status')}, "
            f"model_loaded={remote_health.get('model_loaded')}, "
            f"device={remote_health.get('device')}, busy={remote_health.get('busy')}"
        )
    except Exception as exc:
        remote_reason = str(exc)

    reason = f"remote_service: {'OK' if remote_ok else remote_reason}"
    return _status(
        remote_ok,
        reason,
        experimental=False,
        service_type="remote",
        configured_mode="remote_only",
        remote_api_available=remote_ok,
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


def _check_configuration():
    configured = {
        "output_root": get_path("output_root"),
        "work_root": get_path("work_root"),
        "task_db": get_path("task_db"),
        "blender_exe": BLENDER_EXE,
        "triposr_python": TRIPOSR_PYTHON,
        "triposr_dir": TRIPOSR_DIR,
    }
    problems = []
    for name, path in configured.items():
        path = Path(path)
        if name == "task_db":
            parent = path.parent
            if not parent.exists():
                problems.append(f"{name} parent missing: {parent}")
        elif name in {"output_root", "work_root", "triposr_dir"}:
            if not path.is_dir():
                problems.append(f"{name} directory missing: {path}")
        elif not path.is_file():
            problems.append(f"{name} file missing: {path}")
    return _status(
        not problems,
        "OK" if not problems else "; ".join(problems),
        paths={name: str(path) for name, path in configured.items()},
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
        "Configuration": _check_configuration(),
    }


def format_health_report(health):
    lines = []
    for name, info in health.items():
        marker = "[OK]" if info.get("available") else "[X]"
        reason = info.get("reason", "")
        if len(reason) > 300:
            reason = reason[:300] + "..."
        lines.append(f"{marker} {name}: {reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_health_report(check_backend_health()))
