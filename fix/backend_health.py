from pathlib import Path
import shutil
import torch


def check_backend_health():

    result = {}


    # TripoSR
    triposr_path = Path("TripoSR-main")

    result["TripoSR"] = {
        "available": triposr_path.exists(),
        "reason":
            "OK"
            if triposr_path.exists()
            else "TripoSR folder missing"
    }


    # Blender

    blender = shutil.which("blender")

    result["Blender"] = {
        "available": blender is not None,
        "reason":
            blender
            if blender
            else "Blender command not found"
    }


    # Torch

    result["Torch"] = {
        "available": True,
        "cuda":
            torch.cuda.is_available(),
        "device":
            torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else "CPU"
    }


    return result