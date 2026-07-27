import json
from pathlib import Path


ALLOWED_ACTIONS = {
    "cleanup_artifacts",
    "center_ground",
    "smooth",
    "bevel",
    "ensure_material",
    "scale_axes",
    "add_primitive",
}
ALLOWED_PRIMITIVES = {"cube", "sphere", "cylinder"}


def _number(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _vector(value, default):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        value = default
    return [_number(item, default[index]) for index, item in enumerate(value)]


def normalize_action(action):
    if not isinstance(action, dict):
        return None
    action_type = str(action.get("type", "")).strip()
    if action_type not in ALLOWED_ACTIONS:
        return None
    normalized = {"type": action_type}
    if action_type == "bevel":
        normalized["width"] = max(0.0, min(_number(action.get("width"), 0.01), 0.2))
        normalized["segments"] = max(1, min(int(_number(action.get("segments"), 2)), 6))
    elif action_type == "scale_axes":
        normalized["scale"] = _vector(action.get("scale"), [1, 1, 1])
    elif action_type == "add_primitive":
        primitive = str(action.get("primitive", "")).lower()
        if primitive not in ALLOWED_PRIMITIVES:
            return None
        normalized.update(
            {
                "primitive": primitive,
                "name": str(action.get("name", f"Correction_{primitive}"))[:80],
                "location": _vector(action.get("location"), [0, 0, 1]),
                "scale": _vector(action.get("scale"), [0.2, 0.2, 0.2]),
                "color": [
                    max(0.0, min(value, 1.0))
                    for value in _vector(action.get("color"), [0.7, 0.7, 0.7])
                ],
            }
        )
    return normalized


def build_action_plan(intent, analysis):
    actions = [
        {"type": "cleanup_artifacts"},
        {"type": "center_ground"},
        {"type": "smooth"},
        {"type": "ensure_material"},
    ]
    lower = (intent or "").lower()
    if any(word in lower for word in ("bevel", "圆角", "倒角", "smooth", "平滑")):
        actions.append({"type": "bevel", "width": 0.01, "segments": 2})

    if any(word in lower for word in ("圆角", "倒角", "平滑")):
        actions.append({"type": "bevel", "width": 0.01, "segments": 2})

    proposed = (analysis or {}).get("structured_actions", [])
    rejected = []
    for action in proposed:
        normalized = normalize_action(action)
        if normalized:
            actions.append(normalized)
        else:
            rejected.append(action)

    unique = []
    seen = set()
    for action in actions:
        key = json.dumps(action, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            unique.append(action)

    return {
        "schema_version": 1,
        "actions": unique,
        "rejected_actions": rejected,
        "observation_required_after_execution": True,
    }


def save_action_plan(result_dir, plan):
    path = Path(result_dir) / "blender_action_plan.json"
    path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def action_plan_to_blender_code(plan):
    payload = json.dumps((plan or {}).get("actions", []), ensure_ascii=False)
    return f"""
import json

STRUCTURED_ACTIONS = json.loads({payload!r})

def structured_meshes():
    return [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and "reference_plane" not in obj.name.lower()
    ]

def execute_structured_actions():
    for action in STRUCTURED_ACTIONS:
        action_type = action.get("type")
        if action_type == "cleanup_artifacts":
            cleanup_auto_artifacts()
        elif action_type == "center_ground":
            normalize_model_pose()
        elif action_type == "smooth":
            for obj in structured_meshes():
                for polygon in obj.data.polygons:
                    polygon.use_smooth = True
        elif action_type == "ensure_material":
            material = bpy.data.materials.get("Agent_Default_Material")
            if material is None:
                material = bpy.data.materials.new("Agent_Default_Material")
                material.diffuse_color = (0.65, 0.68, 0.72, 1.0)
            for obj in structured_meshes():
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(material)
        elif action_type == "bevel":
            for obj in structured_meshes():
                modifier = obj.modifiers.get("Agent_Bevel")
                if modifier is None:
                    modifier = obj.modifiers.new("Agent_Bevel", "BEVEL")
                modifier.width = float(action.get("width", 0.01))
                modifier.segments = int(action.get("segments", 2))
        elif action_type == "scale_axes":
            scale = action.get("scale", [1, 1, 1])
            for obj in structured_meshes():
                obj.scale.x *= float(scale[0])
                obj.scale.y *= float(scale[1])
                obj.scale.z *= float(scale[2])
        elif action_type == "add_primitive":
            primitive = action.get("primitive")
            location = action.get("location", [0, 0, 1])
            if primitive == "cube":
                bpy.ops.mesh.primitive_cube_add(location=location)
            elif primitive == "sphere":
                bpy.ops.mesh.primitive_uv_sphere_add(location=location)
            elif primitive == "cylinder":
                bpy.ops.mesh.primitive_cylinder_add(location=location)
            else:
                continue
            obj = bpy.context.object
            obj.name = action.get("name", "Correction")
            obj.scale = action.get("scale", [0.2, 0.2, 0.2])
            color = action.get("color", [0.7, 0.7, 0.7])
            material = bpy.data.materials.new(obj.name + "_Material")
            material.diffuse_color = (*color, 1.0)
            obj.data.materials.append(material)

execute_structured_actions()
"""
