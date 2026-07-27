import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config_loader import get_path


DB_PATH = get_path("task_db")
_local = threading.local()
_db_lock = threading.RLock()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_database():
    with _db_lock, _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                request_text TEXT,
                payload_json TEXT,
                requested_backend TEXT,
                actual_backend TEXT,
                fallback_reason TEXT,
                result_dir TEXT,
                current_stage TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                elapsed_seconds REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                command_json TEXT,
                stdout TEXT,
                stderr TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                elapsed_seconds REAL DEFAULT 0,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_stages_job ON stages(job_id);
            """
        )


def create_job(kind, request_text="", payload=None, requested_backend=""):
    initialize_database()
    job_id = "job_" + uuid.uuid4().hex[:16]
    with _db_lock, _connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                id, kind, status, request_text, payload_json,
                requested_backend, created_at
            ) VALUES (?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                job_id,
                kind,
                request_text,
                json.dumps(payload or {}, ensure_ascii=False),
                requested_backend,
                _now(),
            ),
        )
    return job_id


def update_job(job_id, **fields):
    allowed = {
        "status",
        "requested_backend",
        "actual_backend",
        "fallback_reason",
        "result_dir",
        "current_stage",
        "error",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "payload_json",
    }
    values = {key: value for key, value in fields.items() if key in allowed}
    if not values:
        return
    assignments = ", ".join(f"{key}=?" for key in values)
    with _db_lock, _connect() as connection:
        connection.execute(
            f"UPDATE jobs SET {assignments} WHERE id=?",
            [*values.values(), job_id],
        )


def start_job(job_id):
    update_job(
        job_id,
        status="running",
        started_at=_now(),
        finished_at=None,
        error=None,
    )


def finish_job(job_id, status, error=""):
    job = get_job(job_id)
    elapsed = 0.0
    if job and job.get("started_at"):
        try:
            started = datetime.fromisoformat(job["started_at"])
            elapsed = (datetime.now() - started).total_seconds()
        except ValueError:
            pass
    update_job(
        job_id,
        status=status,
        error=error,
        current_stage="",
        finished_at=_now(),
        elapsed_seconds=elapsed,
    )


def get_job(job_id):
    initialize_database()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit=100):
    initialize_database()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(row) for row in rows]


def list_stages(job_id):
    initialize_database()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM stages WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def recover_interrupted_jobs():
    initialize_database()
    with _db_lock, _connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status='interrupted', finished_at=?, current_stage='',
                error=CASE WHEN error IS NULL OR error='' THEN
                    'Application exited before the task finished.' ELSE error END
            WHERE status='running'
            """,
            (_now(),),
        )


def requeue_job(job_id):
    update_job(
        job_id,
        status="queued",
        started_at=None,
        finished_at=None,
        current_stage="",
        error="",
        elapsed_seconds=0,
    )


def set_active_job(job_id, result_dir=None):
    _local.job_id = job_id
    _local.result_dir = str(result_dir) if result_dir else ""
    if job_id and result_dir:
        update_job(job_id, result_dir=str(result_dir))


def clear_active_job():
    _local.job_id = None
    _local.result_dir = ""


def get_active_job_id():
    return getattr(_local, "job_id", None)


def _append_event(event):
    result_dir = getattr(_local, "result_dir", "")
    if not result_dir:
        return
    path = Path(result_dir) / "stage_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def start_stage(name, command=None):
    job_id = get_active_job_id()
    if not job_id:
        return None
    started_at = _now()
    with _db_lock, _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO stages (
                job_id, name, status, command_json, started_at
            ) VALUES (?, ?, 'running', ?, ?)
            """,
            (
                job_id,
                name,
                json.dumps(command, ensure_ascii=False) if command else None,
                started_at,
            ),
        )
        stage_id = cursor.lastrowid
    update_job(job_id, current_stage=name)
    _append_event(
        {
            "time": started_at,
            "job_id": job_id,
            "stage_id": stage_id,
            "stage": name,
            "status": "running",
            "command": command,
        }
    )
    return stage_id, time.monotonic()


def finish_stage(stage_token, status, stdout="", stderr="", error=""):
    if not stage_token:
        return
    stage_id, started_monotonic = stage_token
    elapsed = time.monotonic() - started_monotonic
    finished_at = _now()
    with _db_lock, _connect() as connection:
        connection.execute(
            """
            UPDATE stages SET status=?, stdout=?, stderr=?, error=?,
                finished_at=?, elapsed_seconds=? WHERE id=?
            """,
            (
                status,
                (stdout or "")[-10000:],
                (stderr or "")[-10000:],
                (error or "")[-10000:],
                finished_at,
                elapsed,
                stage_id,
            ),
        )
    _append_event(
        {
            "time": finished_at,
            "job_id": get_active_job_id(),
            "stage_id": stage_id,
            "status": status,
            "elapsed_seconds": round(elapsed, 3),
            "error": error,
        }
    )


def record_stage(name, status="completed", output="", error="", command=None):
    token = start_stage(name, command=command)
    finish_stage(token, status, stdout=output, error=error)


@contextmanager
def task_stage(name):
    token = start_stage(name)
    try:
        yield
    except Exception as exc:
        finish_stage(token, "failed", error=str(exc))
        raise
    else:
        finish_stage(token, "completed")


initialize_database()
