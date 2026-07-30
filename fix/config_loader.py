import glob
import json
import os
import shutil
import sys
from pathlib import Path


class ConfigurationError(RuntimeError):
    pass


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
PROJECT_DIR = BASE_DIR.parent


def _config_path():
    configured = os.environ.get("IMAGE3D_CONFIG", "").strip()
    if not configured:
        return (BASE_DIR / "config.json").resolve()
    path = Path(os.path.expandvars(os.path.expanduser(configured)))
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.resolve()


CONFIG_PATH = _config_path()


def _load_dotenv():
    env_path = PROJECT_DIR / ".env"
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()


def _load_config():
    if not CONFIG_PATH.is_file():
        raise ConfigurationError(f"Config file not found: {CONFIG_PATH}")
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read config file {CONFIG_PATH}: {exc}") from exc
    if not isinstance(data.get("paths"), dict):
        raise ConfigurationError("config.json must contain a 'paths' object.")
    if not isinstance(data.get("runtime"), dict):
        raise ConfigurationError("config.json must contain a 'runtime' object.")
    return data


CONFIG = _load_config()


def get_value(section, key, default=None):
    return CONFIG.get(section, {}).get(key, default)


def get_section(section):
    value = CONFIG.get(section, {})
    return value if isinstance(value, dict) else {}


def get_runtime(key, default=None):
    return get_value("runtime", key, default)


def get_timeout(key, default=600):
    value = CONFIG.get("timeouts_seconds", {}).get(key, default)
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Timeout '{key}' must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"Timeout '{key}' must be greater than zero.")
    return value


def _raw_path(key, required):
    env_name = f"IMAGE3D_{key.upper()}"
    value = os.environ.get(env_name, CONFIG["paths"].get(key))
    if value is None or str(value).strip() == "":
        if required:
            raise ConfigurationError(
                f"Path '{key}' is missing in {CONFIG_PATH} "
                f"(or environment variable {env_name})."
            )
        return None
    return str(value).strip()


def _first_file(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    return None


def _first_directory(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_dir():
            return path.resolve()
    return None


def _which(name):
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def _auto_python(key):
    current = Path(sys.executable).resolve()
    if key == "mast3r_python":
        candidates = [
            PROJECT_DIR / ".venv-mast3r" / "Scripts" / "python.exe",
            PROJECT_DIR / ".venv-mast3r" / "bin" / "python",
            PROJECT_DIR / "runtime" / "mast3r" / "python.exe",
            current,
            _which("python"),
            _which("python3"),
        ]
        fallback = PROJECT_DIR / ".venv-mast3r" / "Scripts" / "python.exe"
    else:
        candidates = [
            current,
            PROJECT_DIR / ".venv" / "Scripts" / "python.exe",
            PROJECT_DIR / ".venv" / "bin" / "python",
            PROJECT_DIR / "runtime" / "triposr" / "python.exe",
            _which("python"),
            _which("python3"),
        ]
        fallback = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    return _first_file(candidates) or fallback.resolve()


def _auto_blender():
    candidates = [
        PROJECT_DIR / "tools" / "blender" / "blender.exe",
        PROJECT_DIR / "Blender" / "blender.exe",
        _which("blender"),
    ]
    for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if not root:
            continue
        pattern = str(
            Path(root) / "Blender Foundation" / "Blender *" / "blender.exe"
        )
        candidates.extend(
            Path(path) for path in sorted(glob.glob(pattern), reverse=True)
        )
    fallback = PROJECT_DIR / "tools" / "blender" / "blender.exe"
    return _first_file(candidates) or fallback.resolve()


def _auto_directory(key):
    if key == "triposr_dir":
        candidates = [
            PROJECT_DIR / "TripoSR-main",
            PROJECT_DIR / "TripoSR",
        ]
        fallback = PROJECT_DIR / "TripoSR-main"
    elif key == "mast3r_dir":
        candidates = [
            PROJECT_DIR / "MASt3R",
            PROJECT_DIR / "mast3r",
            PROJECT_DIR / "mast3r-main",
            PROJECT_DIR / "mast3r-main" / "mast3r-main",
        ]
        fallback = PROJECT_DIR / "MASt3R"
    else:
        return None
    return _first_directory(candidates) or fallback.resolve()


def _auto_tool(key):
    if key == "meshlabserver_exe":
        candidates = [
            PROJECT_DIR / "tools" / "meshlab" / "meshlabserver.exe",
            _which("meshlabserver"),
        ]
    elif key == "instant_meshes_exe":
        candidates = [
            PROJECT_DIR / "tools" / "instant-meshes" / "Instant Meshes.exe",
            PROJECT_DIR / "instant-meshes-master" / "Instant Meshes.exe",
            _which("Instant Meshes"),
            _which("InstantMeshes"),
        ]
    else:
        return None
    return _first_file(candidates)


def _auto_path(key, required):
    if key in {"triposr_python", "mast3r_python"}:
        return _auto_python(key)
    if key == "blender_exe":
        return _auto_blender()
    if key in {"triposr_dir", "mast3r_dir"}:
        return _auto_directory(key)
    if key in {"meshlabserver_exe", "instant_meshes_exe"}:
        path = _auto_tool(key)
        if path is not None or not required:
            return path
    if required:
        raise ConfigurationError(f"No automatic path resolver is defined for '{key}'.")
    return None


def _resolve_configured_path(value):
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def get_path(key):
    value = _raw_path(key, required=True)
    if value.lower() in {"auto", "detect"}:
        return _auto_path(key, required=True)
    return _resolve_configured_path(value)


def get_optional_path(key):
    value = _raw_path(key, required=False)
    if value is None:
        return None
    if value.lower() in {"auto", "detect"}:
        return _auto_path(key, required=False)
    return _resolve_configured_path(value)
