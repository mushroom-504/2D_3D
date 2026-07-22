import shutil
import subprocess
from pathlib import Path


import sys

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parents[1]


from config_loader import get_path

TRIPOSR_PYTHON = str(
    get_path("triposr_python")
)

TRIPOSR_DIR = get_path(
    "triposr_dir"
)


CRAFTSMAN_PYTHON = get_path(
    "craftsman_python"
)


CRAFTSMAN_DIR = get_path(
    "craftsman_dir"
)


WORK_ROOT = get_path(
    "work_root"
)

BACKEND_AUTO = "Auto"
BACKEND_CRAFTSMAN = "CraftsMan"
BACKEND_TRIPOSR = "TripoSR"
BACKEND_TRIPOSR_ENHANCED = "TripoSR Enhanced"
BACKEND_TRIPOSR_FUSION = "TripoSR Fusion"
BACKEND_EXTERNAL_MULTIVIEW = "External Multi-View"

PROJECT_ROOT = BASE_DIR
TRIPOSR_DIR_CANDIDATES = [
    PROJECT_ROOT / "TripoSR-main",
]
TRIPOSR_DIR = TRIPOSR_DIR_CANDIDATES[0]
CRAFTSMAN_PYTHON = Path(r"D:\conda\envs\CraftsMan\python.exe")
CRAFTSMAN_DIR = PROJECT_ROOT / "CraftsMan"
CRAFTSMAN_MODEL_CANDIDATES = [
    Path(r"D:\CraftsMan_models\craftsman-DoraVAE"),
    PROJECT_ROOT / "ckpts" / "craftsman-DoraVAE",
    PROJECT_ROOT / "ckpts" / "craftsman-doravae",
]
CRAFTSMAN_MODEL_DIR = next(
    (
        path for path in CRAFTSMAN_MODEL_CANDIDATES
        if (path / "config.yaml").exists() and (path / "model.ckpt").exists()
    ),
    CRAFTSMAN_MODEL_CANDIDATES[0],
)
WORK_ROOT = Path(r"C:\TSR_Work")


def run_command(command, cwd=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n\n"
            + " ".join(str(x) for x in command)
            + "\n\nSTDOUT:\n"
            + result.stdout
            + "\n\nSTDERR:\n"
            + result.stderr
        )
    return result


def copy_reference_images(ref_map, result_dir):
    refs_dir = result_dir / "reference_images"
    refs_dir.mkdir(parents=True, exist_ok=True)
    copied_refs = {}
    for view_key, ref in ref_map.items():
        if not ref:
            continue
        ref_path = Path(ref)
        if ref_path.exists():
            ext = ref_path.suffix.lower()
            dst = refs_dir / f"{view_key}{ext}"
            shutil.copy2(ref_path, dst)
            copied_refs[view_key] = dst
    return copied_refs


def run_triposr_backend(safe_input, triposr_output_dir, mc_resolution=384):
    if not TRIPOSR_DIR.exists():
        raise RuntimeError(
            "TripoSR folder not found. Checked:\n"
            + "\n".join(str(path) for path in TRIPOSR_DIR_CANDIDATES)
        )
    run_command(
        [
            TRIPOSR_PYTHON,
            "run.py",
            str(safe_input),
            "--output-dir",
            str(triposr_output_dir),
            "--mc-resolution",
            str(mc_resolution),
        ],
        cwd=str(TRIPOSR_DIR),
    )
    obj_path = Path(triposr_output_dir) / "0" / "mesh.obj"
    if not obj_path.exists():
        raise RuntimeError(f"OBJ file not found:\n{obj_path}")
    return obj_path


def run_craftsman_backend(safe_input, result_dir):
    if not CRAFTSMAN_PYTHON.exists():
        raise RuntimeError(f"CraftsMan Python environment not found: {CRAFTSMAN_PYTHON}")
    if not (CRAFTSMAN_DIR / "craftsman").exists():
        raise RuntimeError(f"CraftsMan project not found: {CRAFTSMAN_DIR}")

    runner = Path(__file__).with_name("craftsman_runner.py")
    output_dir = Path(result_dir) / "craftsman_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_obj = output_dir / "mesh.obj"
    run_command(
        [
            str(CRAFTSMAN_PYTHON), str(runner),
            "--input", str(safe_input),
            "--output", str(output_obj),
            "--craftsman-root", str(CRAFTSMAN_DIR),
            "--model-dir", str(CRAFTSMAN_MODEL_DIR),
        ],
        cwd=str(CRAFTSMAN_DIR),
    )
    if not output_obj.exists() or output_obj.stat().st_size == 0:
        raise RuntimeError(f"CraftsMan did not create an OBJ: {output_obj}")
    return output_obj


def run_triposr_fusion_backend(image_paths_for_agent, result_dir, mc_resolution=384):
    """Run TripoSR for each available view, then return view -> OBJ path."""
    result_dir = Path(result_dir)
    fusion_dir = result_dir / "triposr_fusion_meshes"
    fusion_dir.mkdir(parents=True, exist_ok=True)

    mesh_paths = {}
    for view in ["front", "back", "left", "right", "top", "bottom"]:
        image_path = (image_paths_for_agent or {}).get(view)
        if not image_path:
            continue
        image_path = Path(image_path)
        if not image_path.exists():
            continue

        view_output_dir = fusion_dir / f"{view}_triposr_output"
        obj_path = run_triposr_backend(image_path, view_output_dir, mc_resolution=mc_resolution)
        copied_obj = fusion_dir / f"{view}_mesh.obj"
        shutil.copy2(obj_path, copied_obj)
        mesh_paths[view] = copied_obj

    if "front" not in mesh_paths:
        raise RuntimeError("TripoSR Fusion needs a front image to create the main mesh.")
    if len(mesh_paths) < 2:
        raise RuntimeError("TripoSR Fusion needs front plus at least one reference image.")

    return mesh_paths


def run_external_multiview_backend(image_paths_for_agent, result_dir):
    import os

    script = os.environ.get("MULTIVIEW_RECON_SCRIPT")
    python_exe = os.environ.get("MULTIVIEW_RECON_PYTHON", TRIPOSR_PYTHON)
    default_mast3r_runner = Path(__file__).with_name("mast3r_multiview_runner.py")
    default_mast3r_python = Path(r"D:\conda\envs\mast3r\python.exe")
    if not script or "your_multiview" in script or "path\\to" in script or not Path(script).exists():
        script = str(default_mast3r_runner)
    if not python_exe or "your_multiview" in python_exe or not Path(python_exe).exists():
        python_exe = str(default_mast3r_python if default_mast3r_python.exists() else TRIPOSR_PYTHON)
    if Path(script) == default_mast3r_runner and default_mast3r_python.exists():
        python_exe = str(default_mast3r_python)

    output_dir = Path(result_dir) / "multiview_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [python_exe, script, "--output-dir", str(output_dir)]
    for view, path in image_paths_for_agent.items():
        if path and Path(path).exists():
            command.extend([f"--{view}", str(path)])

    run_command(command)

    candidates = [
        output_dir / "mesh.obj",
        output_dir / "model.obj",
        output_dir / "scene.obj",
        output_dir / "scene.glb",
        output_dir / "model.glb",
        output_dir / "mesh.glb",
        output_dir / "scene.gltf",
        output_dir / "model.gltf",
        output_dir / "mesh.gltf",
        output_dir / "scene.ply",
        output_dir / "model.ply",
        output_dir / "mesh.ply",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    for suffix in [".glb", ".obj", ".gltf", ".ply"]:
        matches = sorted(output_dir.rglob(f"*{suffix}"), key=lambda p: p.stat().st_size, reverse=True)
        if matches:
            return matches[0]

    raise RuntimeError(
        "External Multi-View backend finished, but no OBJ/GLB file was found.\n"
        f"Expected one of:\n" + "\n".join(str(p) for p in candidates)
    )
