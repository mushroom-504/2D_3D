import json
import os
import sys
from pathlib import Path


class ConfigurationError(RuntimeError):
    pass


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
CONFIG_PATH = Path(
    os.environ.get("IMAGE3D_CONFIG", str(BASE_DIR / "config.json"))
).expanduser().resolve()


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
                f"Path '{key}' is missing in {CONFIG_PATH} (or environment variable {env_name})."
            )
        return None
    return str(value)


def get_path(key):
    value = _raw_path(key, required=True)
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def get_optional_path(key):
    value = _raw_path(key, required=False)
    if value is None:
        return None
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()
