import json
from pathlib import Path

from backend_manager import TaskCancelledError, run_command
from config_loader import get_path, get_timeout
from visual_quality import evaluate_visual_similarity


BLENDER_EXE = get_path("blender_exe")
MODEL_CHECK_TIMEOUT = get_timeout("model_check")


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
    "duplicate_overlap_suspected": False,
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
    object_bounds = []
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

        own_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        if own_corners:
            own_min = Vector((
                min(v.x for v in own_corners),
                min(v.y for v in own_corners),
                min(v.z for v in own_corners),
            ))
            own_max = Vector((
                max(v.x for v in own_corners),
                max(v.y for v in own_corners),
                max(v.z for v in own_corners),
            ))
            own_size = own_max - own_min
            own_volume = max(own_size.x * own_size.y * own_size.z, 0.0)
            object_bounds.append((obj.name, own_min, own_max, own_volume))

        for corner in obj.bound_box:
            if name.endswith("reference_plane") or "reference_plane" in name:
                continue
            corners.append(obj.matrix_world @ Vector(corner))

    result["material_count"] = len(materials)

    per_view_names = (
        "front_mesh", "back_mesh", "left_mesh", "right_mesh",
        "top_mesh", "bottom_mesh", "triposr_front", "triposr_back",
    )
    if sum(
        any(token in obj.name.lower() for token in per_view_names)
        for obj in mesh_objects
    ) >= 2:
        result["duplicate_overlap_suspected"] = True
        result["warnings"].append(
            "Multiple per-view source meshes were found; this resembles removed "
            "multi-mesh fusion output."
        )

    for index, (name_a, min_a, max_a, volume_a) in enumerate(object_bounds):
        if volume_a <= 0:
            continue
        for name_b, min_b, max_b, volume_b in object_bounds[index + 1:]:
            if volume_b <= 0:
                continue
            overlap = Vector((
                max(0.0, min(max_a.x, max_b.x) - max(min_a.x, min_b.x)),
                max(0.0, min(max_a.y, max_b.y) - max(min_a.y, min_b.y)),
                max(0.0, min(max_a.z, max_b.z) - max(min_a.z, min_b.z)),
            ))
            overlap_volume = overlap.x * overlap.y * overlap.z
            if overlap_volume / min(volume_a, volume_b) >= 0.70:
                result["duplicate_overlap_suspected"] = True
                result["warnings"].append(
                    f"Large mesh bounds overlap: {{name_a}} and {{name_b}}."
                )

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

    try:
        run_command(
            [blender_exe, "--background", "--python", script_path],
            capture_output=True,
            timeout=MODEL_CHECK_TIMEOUT,
        )
    except TaskCancelledError:
        raise
    except Exception as exc:
        return {
            "can_open_blender_file": False,
            "warnings": [f"Blender model check failed: {exc}"],
        }

    if not output_json.exists():
        return {
            "can_open_blender_file": False,
            "warnings": ["Blender check did not write model_check_blender.json."],
        }

    return json.loads(output_json.read_text(encoding="utf-8"))


def check_generation_outputs(result_dir, visual_iteration=None):
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
    visual_quality = {}
    if expected["blend"].exists() and blender_check.get("can_open_blender_file"):
        visual_quality = evaluate_visual_similarity(
            result_dir,
            expected["blend"],
            iteration=visual_iteration,
        )

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
    if visual_quality.get("below_threshold"):
        problems.append(
            "Rendered model has low visual similarity to the reference images: "
            f"{visual_quality.get('overall_score')} < "
            f"{visual_quality.get('warning_threshold')}."
        )
    worst_missing = float(visual_quality.get("worst_missing_silhouette_ratio", 0.0))
    missing_threshold = float(
        visual_quality.get("missing_silhouette_warning_ratio", 1.0)
    )
    if worst_missing > missing_threshold:
        problems.append(
            "Rendered model is missing reference silhouette regions: "
            f"{worst_missing:.1%} > {missing_threshold:.1%}."
        )
    worst_color = float(visual_quality.get("worst_color_difference_percent", 0.0))
    color_threshold = float(
        visual_quality.get("color_difference_warning_percent", 100.0)
    )
    if worst_color > color_threshold:
        problems.append(
            "Rendered model colors differ from the reference images: "
            f"{worst_color:.1f}% > {color_threshold:.1f}%."
        )
    semantic = visual_quality.get("semantic_comparison") or {}
    if semantic.get("available") and str(semantic.get("severity", "none")).lower() in {
        "moderate",
        "major",
    }:
        problems.append(
            "Vision comparison found meaningful geometry/style differences: "
            f"{semantic.get('overall_assessment', semantic.get('severity'))}"
        )
    for part in semantic.get("global_missing_parts") or []:
        problems.append(f"Missing visible part: {part}")

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
            "visual_similarity": visual_quality.get("overall_score"),
            "visual_similarity_available": visual_quality.get("available", False),
            "visual_repair_needed": visual_quality.get("needs_repair", False),
            "color_similarity_by_view": {
                view: info.get("color_similarity")
                for view, info in (visual_quality.get("views") or {}).items()
            },
            "missing_silhouette_by_view": {
                view: info.get("missing_silhouette_ratio")
                for view, info in (visual_quality.get("views") or {}).items()
            },
        },
        "reference_usage": reference_usage,
        "blender_check": blender_check,
        "visual_quality": visual_quality,
    }
