import json
from pathlib import Path

from backend_manager import (
    BACKEND_CRAFTSMAN,
    BACKEND_EXTERNAL_MULTIVIEW,
    BACKEND_TRIPOSR,
    MAST3R_PYTHON,
    MULTIVIEW_SCRIPT,
    TRIPOSR_DIR,
    TRIPOSR_PYTHON,
    run_command,
)
from config_loader import get_path, get_section, get_timeout


BLENDER_EXE = get_path("blender_exe")
MAST3R_DIR = get_path("mast3r_dir")
HEALTH_TIMEOUT = get_timeout("health_probe")
EXTERNAL_MULTIVIEW_CONFIG = get_section("external_multiview")
LLM_BLENDER_AGENT_CONFIG = get_section("llm_blender_agent")


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
            part.strip()
            for part in (completed.stdout, completed.stderr)
            if part and part.strip()
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
        "print('cuda=' + str(torch.cuda.is_available())); "
        "print('device=' + (torch.cuda.get_device_name(0) "
        "if torch.cuda.is_available() else 'CPU'))",
        cwd=TRIPOSR_DIR,
    )
    cuda_available = ok and "cuda=True" in reason
    if ok and not cuda_available:
        reason += (
            "\nCPU mode: TripoSR is available, but generation will be slower. "
            "Enable CUDA only on a machine with a supported NVIDIA GPU, driver, "
            "and CUDA-enabled PyTorch."
        )
    return _status(
        ok,
        reason,
        python=str(TRIPOSR_PYTHON),
        source=str(TRIPOSR_DIR),
        cuda_available=cuda_available,
        execution_mode="cuda" if cuda_available else "cpu",
    )


def _check_craftsman():
    remote_health = {}
    remote_ok = False
    remote_reason = ""
    try:
        from craftsman_api_runner import check_health

        remote_health = check_health(timeout=HEALTH_TIMEOUT)
        remote_ok = remote_health.get("status") == "ok"
        multiview_declared = bool(
            remote_health.get("supports_multiview")
            or remote_health.get("multiview_supported")
        )
        remote_reason = (
            f"status={remote_health.get('status')}, "
            f"model_loaded={remote_health.get('model_loaded')}, "
            f"device={remote_health.get('device')}, "
            f"busy={remote_health.get('busy')}, "
            f"output_format={remote_health.get('output_format')}, "
            f"multiview_declared={multiview_declared}"
        )
    except Exception as exc:
        remote_reason = str(exc)

    reason = (
        f"remote_service: OK ({remote_reason})"
        if remote_ok
        else f"remote_service: {remote_reason}"
    )
    return _status(
        remote_ok,
        reason,
        experimental=False,
        service_type="remote",
        configured_mode="remote_only",
        remote_api_available=remote_ok,
        multiview_capability_declared=bool(
            remote_health.get("supports_multiview")
            or remote_health.get("multiview_supported")
        ),
        supported_views=remote_health.get("supported_views", []),
        output_format=remote_health.get("output_format"),
    )


def _check_multiview():
    if not bool(EXTERNAL_MULTIVIEW_CONFIG.get("enabled", False)):
        return _status(
            False,
            "Disabled (optional experimental backend). "
            "TripoSR and CraftsMan are unaffected.",
            enabled=False,
            optional=True,
            experimental=True,
            severity="info",
        )
    if not MULTIVIEW_SCRIPT.is_file():
        return _status(
            False,
            f"Runner missing: {MULTIVIEW_SCRIPT}",
            enabled=True,
            optional=True,
            experimental=True,
        )
    if not MAST3R_DIR.is_dir():
        return _status(
            False,
            f"MASt3R source missing: {MAST3R_DIR}",
            enabled=True,
            optional=True,
            experimental=True,
        )
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
        enabled=True,
        optional=True,
        experimental=True,
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
        elif name in {"output_root", "work_root"}:
            if not path.exists() and not path.parent.is_dir():
                problems.append(f"{name} parent missing: {path.parent}")
        elif name == "triposr_dir":
            if not path.is_dir():
                problems.append(f"{name} directory missing: {path}")
        elif not path.is_file():
            problems.append(f"{name} file missing: {path}")
    return _status(
        not problems,
        "OK" if not problems else "; ".join(problems),
        paths={name: str(path) for name, path in configured.items()},
    )


def _check_llm_blender_agent():
    enabled = bool(LLM_BLENDER_AGENT_CONFIG.get("enabled", True))
    if not enabled:
        return _status(
            False,
            "Disabled in config.json.",
            enabled=False,
            optional=True,
            severity="info",
        )
    try:
        from llm_blender_agent_client import check_blender_mcp

        result = check_blender_mcp()
        available = bool(result.get("available"))
        return _status(
            available,
            result.get("reason", result.get("status", "unknown")),
            enabled=True,
            optional=True,
            severity=None if available else "info",
            host=str(LLM_BLENDER_AGENT_CONFIG.get("host", "127.0.0.1")),
            port=int(LLM_BLENDER_AGENT_CONFIG.get("port", 9876)),
        )
    except Exception as exc:
        return _status(
            False,
            str(exc),
            enabled=True,
            optional=True,
            severity="info",
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
        BACKEND_CRAFTSMAN: craftsman,
        BACKEND_EXTERNAL_MULTIVIEW: multiview,
        "LLM Blender Agent": _check_llm_blender_agent(),
        "Blender": blender,
        "Configuration": _check_configuration(),
    }


def format_health_report(health):
    lines = []
    for name, info in health.items():
        if info.get("available"):
            marker = "[OK]"
        elif info.get("severity") == "info" or (
            info.get("optional") and not info.get("enabled", True)
        ):
            marker = "[INFO]"
        else:
            marker = "[X]"
        reason = info.get("reason", "")
        if len(reason) > 500:
            reason = reason[:500] + "..."
        lines.append(f"{marker} {name}: {reason}")
        if info.get("service_type") == "remote" and info.get("available"):
            declared = info.get("multiview_capability_declared")
            views = info.get("supported_views") or []
            capability_text = (
                "\u670d\u52a1\u7aef\u5df2\u58f0\u660e"
                if declared
                else "\u670d\u52a1\u7aef\u672a\u58f0\u660e\uff08\u63a5\u53e3\u4ecd\u5728\u7ebf\uff09"
            )
            view_text = ", ".join(views) if views else "\u672a\u63d0\u4f9b"
            lines.append(
                f"    \u591a\u89c6\u56fe\u80fd\u529b\uff1a{capability_text}\uff1b"
                f"\u652f\u6301\u89c6\u56fe\uff1a{view_text}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_health_report(check_backend_health()))
