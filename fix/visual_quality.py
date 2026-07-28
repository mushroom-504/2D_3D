import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from backend_manager import TaskCancelledError, run_command
from config_loader import get_path, get_section, get_timeout
from three_view_agent import compare_reference_and_render_pairs


BLENDER_EXE = get_path("blender_exe")
QUALITY_CONFIG = get_section("quality")
RENDER_TIMEOUT = get_timeout("visual_render")
RENDER_RESOLUTION = int(QUALITY_CONFIG.get("render_resolution", 512))
WARNING_THRESHOLD = float(
    QUALITY_CONFIG.get("visual_similarity_warning_threshold", 60.0)
)
MISSING_RATIO_THRESHOLD = float(
    QUALITY_CONFIG.get("missing_silhouette_warning_ratio", 0.08)
)
COLOR_DIFFERENCE_THRESHOLD = float(
    QUALITY_CONFIG.get("color_difference_warning_percent", 25.0)
)
SEMANTIC_COMPARISON_ENABLED = bool(
    QUALITY_CONFIG.get("enable_semantic_visual_comparison", True)
)
VIEW_ORDER = ("front", "back", "left", "right", "top")


def _write_render_script(path, blend_path, output_dir):
    path.write_text(
        f"""
import bpy
import math
import os
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=r"{blend_path}")
output_dir = r"{output_dir}"
os.makedirs(output_dir, exist_ok=True)

meshes = [
    obj for obj in bpy.context.scene.objects
    if obj.type == "MESH" and "reference_plane" not in obj.name.lower()
]
if not meshes:
    raise RuntimeError("No mesh objects available for visual quality renders.")

corners = [
    obj.matrix_world @ Vector(corner)
    for obj in meshes
    for corner in obj.bound_box
]
minimum = Vector((
    min(point.x for point in corners),
    min(point.y for point in corners),
    min(point.z for point in corners),
))
maximum = Vector((
    max(point.x for point in corners),
    max(point.y for point in corners),
    max(point.z for point in corners),
))
center = (minimum + maximum) / 2.0
size = maximum - minimum
largest = max(size.x, size.y, size.z, 0.1)
distance = largest * 3.0

for obj in list(bpy.context.scene.objects):
    if obj.type == "CAMERA":
        bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = largest * 1.35
bpy.context.scene.camera = camera

scene = bpy.context.scene
scene.render.resolution_x = {RENDER_RESOLUTION}
scene.render.resolution_y = {RENDER_RESOLUTION}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = True
try:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
except Exception as exc:
    print("Workbench setup warning:", exc)

positions = {{
    "front": center + Vector((0, -distance, 0)),
    "back": center + Vector((0, distance, 0)),
    "left": center + Vector((-distance, 0, 0)),
    "right": center + Vector((distance, 0, 0)),
    "top": center + Vector((0, 0, distance)),
}}

for view, position in positions.items():
    camera.location = position
    camera.rotation_euler = (center - position).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(output_dir, view + ".png")
    bpy.ops.render.render(write_still=True)
""",
        encoding="utf-8",
    )


def render_canonical_views(blend_path, result_dir, iteration=None):
    result_dir = Path(result_dir).resolve()
    blend_path = Path(blend_path).resolve()
    render_dir = result_dir / "quality_renders"
    if iteration is not None:
        render_dir = render_dir / f"attempt_{int(iteration)}"
    render_dir.mkdir(parents=True, exist_ok=True)
    script = result_dir / "render_quality_views.py"
    _write_render_script(script, blend_path, render_dir)
    run_command(
        [BLENDER_EXE, "--background", "--python", script],
        timeout=RENDER_TIMEOUT,
        capture_output=True,
    )
    return {
        view: render_dir / f"{view}.png"
        for view in VIEW_ORDER
        if (render_dir / f"{view}.png").is_file()
    }


def _foreground_mask(image):
    rgba = np.asarray(image.convert("RGBA"), dtype=np.int32)
    alpha = rgba[:, :, 3]
    rgb = rgba[:, :, :3]
    if np.any(alpha < 250):
        mask = alpha > 16
    else:
        corners = np.stack(
            [rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]], axis=0
        )
        background = np.median(corners, axis=0)
        distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
        mask = distance > 28
        if mask.mean() > 0.9 or mask.mean() < 0.01:
            brightness = rgb.mean(axis=2)
            mask = brightness < 245
    return mask


def _normalized_pair(path):
    image = Image.open(path).convert("RGBA")
    mask = _foreground_mask(image)
    points = np.argwhere(mask)
    if len(points) == 0:
        return None, None
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    cropped_image = image.crop((x0, y0, x1, y1)).resize((256, 256))
    mask_image = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype("uint8"))
    cropped_mask = np.asarray(
        mask_image.resize((256, 256), Image.Resampling.NEAREST)
    ) > 127
    return cropped_image, cropped_mask


def _mask_regions(mask):
    height, width = mask.shape
    regions = {
        "top": mask[: height // 3, :],
        "bottom": mask[(height * 2) // 3 :, :],
        "left": mask[:, : width // 3],
        "right": mask[:, (width * 2) // 3 :],
        "center": mask[height // 3 : (height * 2) // 3, width // 3 : (width * 2) // 3],
    }
    total = max(int(mask.sum()), 1)
    return {
        name: round(float(region.sum()) / total * 100.0, 2)
        for name, region in regions.items()
        if region.any()
    }


def _write_difference_image(reference_mask, rendered_mask, output_path):
    height, width = reference_mask.shape
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    overlap = np.logical_and(reference_mask, rendered_mask)
    missing = np.logical_and(reference_mask, ~rendered_mask)
    extra = np.logical_and(rendered_mask, ~reference_mask)
    overlay[overlap] = (190, 190, 190, 180)
    overlay[missing] = (255, 60, 60, 255)
    overlay[extra] = (40, 120, 255, 255)
    Image.fromarray(overlay, "RGBA").save(output_path)


def compare_images(reference_path, render_path, difference_output=None):
    reference, reference_mask = _normalized_pair(reference_path)
    rendered, rendered_mask = _normalized_pair(render_path)
    if reference is None or rendered is None:
        return {
            "score": 0.0,
            "silhouette_iou": 0.0,
            "edge_similarity": 0.0,
            "color_similarity": 0.0,
            "missing_silhouette_ratio": 1.0,
            "extra_silhouette_ratio": 1.0,
            "warning": "Could not isolate a foreground silhouette.",
        }

    intersection = np.logical_and(reference_mask, rendered_mask).sum()
    union = np.logical_or(reference_mask, rendered_mask).sum()
    silhouette_iou = float(intersection / union) if union else 0.0
    missing_mask = np.logical_and(reference_mask, ~rendered_mask)
    extra_mask = np.logical_and(rendered_mask, ~reference_mask)
    missing_ratio = float(missing_mask.sum() / max(reference_mask.sum(), 1))
    extra_ratio = float(extra_mask.sum() / max(rendered_mask.sum(), 1))

    ref_edge = np.asarray(
        reference.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32
    )
    render_edge = np.asarray(
        rendered.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32
    )
    edge_similarity = float(
        max(0.0, 1.0 - np.mean(np.abs(ref_edge - render_edge)) / 255.0)
    )
    reference_rgb = np.asarray(reference.convert("RGB"), dtype=np.float32)
    rendered_rgb = np.asarray(rendered.convert("RGB"), dtype=np.float32)
    reference_mean = reference_rgb[reference_mask].mean(axis=0)
    rendered_mean = rendered_rgb[rendered_mask].mean(axis=0)
    color_delta = float(np.mean(np.abs(reference_mean - rendered_mean)) / 255.0)
    color_similarity = max(0.0, 1.0 - color_delta)
    score = 100.0 * (
        0.55 * silhouette_iou + 0.20 * edge_similarity + 0.25 * color_similarity
    )
    if difference_output:
        _write_difference_image(reference_mask, rendered_mask, difference_output)
    return {
        "score": round(score, 2),
        "silhouette_iou": round(silhouette_iou, 4),
        "silhouette_difference_percent": round((1.0 - silhouette_iou) * 100.0, 2),
        "edge_similarity": round(edge_similarity, 4),
        "color_similarity": round(color_similarity * 100.0, 2),
        "color_difference_percent": round(color_delta * 100.0, 2),
        "reference_mean_rgb": [round(float(value), 1) for value in reference_mean],
        "render_mean_rgb": [round(float(value), 1) for value in rendered_mean],
        "missing_silhouette_ratio": round(missing_ratio, 4),
        "extra_silhouette_ratio": round(extra_ratio, 4),
        "missing_regions_percent": _mask_regions(missing_mask),
        "extra_regions_percent": _mask_regions(extra_mask),
        "difference_legend": "red=missing from render, blue=extra in render, gray=overlap",
    }


def _reference_images(result_dir):
    result_dir = Path(result_dir)
    result = {}
    front = result_dir / "input_front.png"
    if front.is_file():
        result["front"] = front
    refs = result_dir / "reference_images"
    if refs.is_dir():
        for view in VIEW_ORDER:
            matches = sorted(refs.glob(f"{view}.*"))
            if matches:
                result[view] = matches[0]
    return result


def evaluate_visual_similarity(result_dir, blend_path, iteration=None):
    result_dir = Path(result_dir).resolve()
    blend_path = Path(blend_path).resolve()
    report_path = result_dir / (
        f"visual_quality_attempt_{int(iteration)}.json"
        if iteration is not None
        else "visual_quality.json"
    )
    references = _reference_images(result_dir)
    if not references:
        report = {
            "available": False,
            "warning": "No reference images were available for visual comparison.",
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    try:
        renders = render_canonical_views(blend_path, result_dir, iteration=iteration)
        views = {}
        view_pairs = {}
        for view, reference in references.items():
            render = renders.get(view)
            if render:
                difference_path = render.parent / f"{view}_difference.png"
                views[view] = {
                    **compare_images(reference, render, difference_path),
                    "reference": str(reference),
                    "render": str(render),
                    "difference_image": str(difference_path),
                }
                if view in {"front", "back", "left", "right"}:
                    view_pairs[view] = (reference, render)
        scores = [item["score"] for item in views.values()]
        overall = round(sum(scores) / len(scores), 2) if scores else 0.0
        worst_missing_ratio = max(
            (item.get("missing_silhouette_ratio", 0.0) for item in views.values()),
            default=0.0,
        )
        worst_color_difference = max(
            (item.get("color_difference_percent", 0.0) for item in views.values()),
            default=0.0,
        )
        semantic = {
            "available": False,
            "mode": "disabled",
            "warning": "Semantic visual comparison is disabled.",
        }
        if SEMANTIC_COMPARISON_ENABLED and view_pairs:
            try:
                semantic = compare_reference_and_render_pairs(view_pairs)
            except Exception as exc:
                semantic = {
                    "available": False,
                    "mode": "vision_error",
                    "warning": f"Semantic visual comparison failed: {exc}",
                }
        severity = str(semantic.get("severity", "none")).lower()
        semantic_needs_repair = semantic.get("available", False) and severity in {
            "moderate",
            "major",
        }
        below_threshold = bool(views) and overall < WARNING_THRESHOLD
        needs_repair = (
            below_threshold
            or worst_missing_ratio > MISSING_RATIO_THRESHOLD
            or worst_color_difference > COLOR_DIFFERENCE_THRESHOLD
            or semantic_needs_repair
        )
        report = {
            "available": bool(views),
            "iteration": iteration,
            "overall_score": overall,
            "warning_threshold": WARNING_THRESHOLD,
            "below_threshold": below_threshold,
            "missing_silhouette_warning_ratio": MISSING_RATIO_THRESHOLD,
            "worst_missing_silhouette_ratio": round(worst_missing_ratio, 4),
            "color_difference_warning_percent": COLOR_DIFFERENCE_THRESHOLD,
            "worst_color_difference_percent": round(worst_color_difference, 2),
            "semantic_comparison": semantic,
            "needs_repair": needs_repair,
            "views": views,
        }
    except TaskCancelledError:
        raise
    except Exception as exc:
        report = {
            "available": False,
            "warning": f"Visual quality evaluation failed: {exc}",
        }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    latest_path = result_dir / "visual_quality.json"
    if latest_path != report_path:
        latest_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report
