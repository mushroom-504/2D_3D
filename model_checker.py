import json
import subprocess
from pathlib import Path


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"


def _expected_files(result_dir):
    result_dir = Path(result_dir)
    return {
        "blend": result_dir / "result.blend",
        "glb": result_dir / "model.glb",
        "fbx": result_dir / "model.fbx",
        "stl": result_dir / "model.stl",
        "preview": result_dir / "preview.png",
    }


def _read_analysis(result_dir):
    analysis_path = Path(result_dir) / "agent_analysis.json"
    if not analysis_path.exists():
        return {}
    try:
        return json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": str(exc)}


def _check_reference_usage(result_dir, analysis):
    refs_dir = Path(result_dir) / "reference_images"
    reference_images = sorted(refs_dir.glob("*")) if refs_dir.exists() else []
    plan = analysis.get("agent_plan", {})
    available_views = set(plan.get("available_views") or analysis.get("available_views") or [])

    copied_reference_views = {path.stem for path in reference_images}
    expected_reference_views = {view for view in available_views if view != "front"}
    missing_from_plan = sorted(copied_reference_views - available_views)

    return {
        "reference_image_count": len(reference_images),
        "copied_reference_views": sorted(copied_reference_views),
        "planned_views": sorted(available_views),
        "expected_reference_views": sorted(expected_reference_views),
        "looks_used": not reference_images or bool(copied_reference_views & expected_reference_views),
        "warnings": (
            [f"Reference images exist but are not listed in the agent plan: {missing_from_plan}"]
            if missing_from_plan
            else []
        ),
    }


def _write_blender_check_script(script_path, blend_path, output_json):
    script_path.write_text(
        f"""
import json
import math
import bpy
from mathutils import Vector

result = {{
    "can_open_blender_file": False,
    "mesh_count": 0,
    "material_count": 0,
    "is_empty": True,
    "is_tilted": False,
    "has_black_base": False,
    "materials_missing": False,
    "bounds": None,
    "warnings": [],
}}

try:
    bpy.ops.wm.open_mainfile(filepath=r"{blend_path}")
    result["can_open_blender_file"] = True

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    result["mesh_count"] = len(mesh_objects)
    result["is_empty"] = len(mesh_objects) == 0

    materials = set()
    corners = []
    for obj in mesh_objects:
        name = obj.name.lower()
        is_base_like = name.startswith("base") or "pedestal" in name or "display_base" in name
        obj_materials = [mat for mat in getattr(obj.data, "materials", []) if mat]
        for mat in obj_materials:
            materials.add(mat.name)
            mat_name = mat.name.lower()
            if "base_dark" in mat_name and is_base_like:
                result["has_black_base"] = True

        if is_base_like or "cylinder" in name:
            z_size = abs(obj.dimensions.z)
            xy_size = max(abs(obj.dimensions.x), abs(obj.dimensions.y))
            if xy_size > 0 and z_size / xy_size < 0.25:
                result["has_black_base"] = True

        if obj_materials == []:
            result["materials_missing"] = True

        for corner in obj.bound_box:
            if name.endswith("reference_plane") or "reference_plane" in name:
                continue
            corners.append(obj.matrix_world @ Vector(corner))

    result["material_count"] = len(materials)

    if corners:
        min_x = min(v.x for v in corners)
        max_x = max(v.x for v in corners)
        min_y = min(v.y for v in corners)
        max_y = max(v.y for v in corners)
        min_z = min(v.z for v in corners)
        max_z = max(v.z for v in corners)
        result["bounds"] = {{
            "x": [min_x, max_x],
            "y": [min_y, max_y],
            "z": [min_z, max_z],
        }}
        width = max_x - min_x
        depth = max_y - min_y
        height = max_z - min_z
        if height < max(width, depth) * 0.55:
            result["is_tilted"] = True
        if min_z < -0.05:
            result["warnings"].append("Model bottom is below ground level.")
        if abs((min_x + max_x) / 2.0) > 0.1 or abs((min_y + max_y) / 2.0) > 0.1:
            result["warnings"].append("Model is not centered near world origin.")

except Exception as exc:
    result["open_error"] = str(exc)

with open(r"{output_json}", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
""",
        encoding="utf-8",
    )


def _run_blender_model_check(result_dir, blend_path):
    blender_exe = Path(BLENDER_EXE)
    if not blender_exe.exists():
        return {
            "can_open_blender_file": False,
            "warnings": [f"Blender executable not found: {BLENDER_EXE}"],
        }

    result_dir = Path(result_dir)
    script_path = result_dir / "model_check_blender.py"
    output_json = result_dir / "model_check_blender.json"
    _write_blender_check_script(script_path, blend_path, output_json)

    completed = subprocess.run(
        [str(blender_exe), "--background", "--python", str(script_path)],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
    )
    if completed.returncode != 0:
        return {
            "can_open_blender_file": False,
            "warnings": ["Blender model check failed."],
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }

    if not output_json.exists():
        return {
            "can_open_blender_file": False,
            "warnings": ["Blender check did not write model_check_blender.json."],
        }

    return json.loads(output_json.read_text(encoding="utf-8"))


def check_generation_outputs(result_dir):
    result_dir = Path(result_dir)
    expected = _expected_files(result_dir)
    missing = [name for name, path in expected.items() if not path.exists()]
    tiny = [name for name, path in expected.items() if path.exists() and path.stat().st_size < 1024]

    analysis = _read_analysis(result_dir)
    reference_usage = _check_reference_usage(result_dir, analysis)
    blender_check = {}
    if expected["blend"].exists():
        blender_check = _run_blender_model_check(result_dir, expected["blend"])
    else:
        blender_check = {
            "can_open_blender_file": False,
            "warnings": ["result.blend does not exist, so Blender open check was skipped."],
        }

    problems = []
    if missing:
        problems.append(f"Missing output files: {missing}")
    if tiny:
        problems.append(f"Output files are too small: {tiny}")
    if not blender_check.get("can_open_blender_file"):
        problems.append("Blender cannot open result.blend.")
    if blender_check.get("is_empty"):
        problems.append("Model appears to be empty.")
    if blender_check.get("is_tilted"):
        problems.append("Model appears to be tilted.")
    if blender_check.get("has_black_base"):
        problems.append("Model may contain an unwanted black base/cylinder.")
    if blender_check.get("materials_missing"):
        problems.append("Some mesh objects have no material.")
    if not reference_usage.get("looks_used"):
        problems.append("Reference images may not have been included in the plan.")

    problems.extend(reference_usage.get("warnings", []))
    problems.extend(blender_check.get("warnings", []))

    return {
        "ok": not problems,
        "missing": missing,
        "tiny": tiny,
        "problems": problems,
        "files": {name: str(path) for name, path in expected.items()},
        "checks": {
            "not_empty": not blender_check.get("is_empty", True),
            "not_tilted": not blender_check.get("is_tilted", False),
            "no_black_base": not blender_check.get("has_black_base", False),
            "blender_can_open": blender_check.get("can_open_blender_file", False),
            "materials_present": not blender_check.get("materials_missing", False),
            "reference_views_used_in_plan": reference_usage.get("looks_used", False),
        },
        "reference_usage": reference_usage,
        "blender_check": blender_check,
    }
