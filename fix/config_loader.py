import json
import sys
from pathlib import Path


def get_base_dir():

    # exe运行
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    # 源码运行
    return Path(__file__).resolve().parent



BASE_DIR = get_base_dir()


CONFIG_PATH = BASE_DIR / "config.json"


with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)



def get_path(key):

    value = CONFIG["paths"][key]

    path = Path(value)

    if not path.is_absolute():
        path = BASE_DIR / path

    return path.resolve()