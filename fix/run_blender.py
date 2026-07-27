import argparse
from pathlib import Path

from backend_manager import run_command
from config_loader import get_path, get_timeout


def main():
    parser = argparse.ArgumentParser(description="Run a Blender Python script with configured Blender.")
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("script_args", nargs="*")
    args = parser.parse_args()

    blender = get_path("blender_exe")
    if not blender.is_file():
        raise SystemExit(f"Blender executable not found: {blender}")
    if not args.script.is_file():
        raise SystemExit(f"Blender script not found: {args.script}")

    command = [blender, "--background", "--python", args.script]
    if args.script_args:
        command.extend(["--", *args.script_args])
    run_command(command, timeout=get_timeout("blender"))


if __name__ == "__main__":
    main()
