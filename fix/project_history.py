import json
import traceback
from datetime import datetime

from config_loader import get_path


HISTORY_FILE = get_path("history_file")
LAST_ERROR_FILE = get_path("last_error_file")


def write_error_report(error):
    LAST_ERROR_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_ERROR_FILE.write_text(
        "3D Agent Error Report\n"
        + "=" * 60
        + "\n\n"
        + str(error)
        + "\n\nTraceback:\n"
        + traceback.format_exc(),
        encoding="utf-8",
    )
    return LAST_ERROR_FILE


def append_history(event):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    event = dict(event)
    event["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
