import json
import traceback
from datetime import datetime
from pathlib import Path


DESKTOP = Path.home() / "Desktop"
HISTORY_FILE = DESKTOP / "3d_agent_history.jsonl"
LAST_ERROR_FILE = DESKTOP / "3d_agent_last_error.txt"


def write_error_report(error):
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
    event = dict(event)
    event["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
