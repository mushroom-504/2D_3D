from three_view_agent import analyze_three_view_request, build_blender_intent, save_analysis


BACKEND_AUTO = "Auto"
BACKEND_CRAFTSMAN = "CraftsMan"
BACKEND_TRIPOSR = "TripoSR"
BACKEND_TRIPOSR_ENHANCED = "TripoSR Enhanced"
BACKEND_TRIPOSR_FUSION = "TripoSR Fusion"
BACKEND_EXTERNAL_MULTIVIEW = "External Multi-View"

VIEW_ORDER = ["front", "back", "left", "right", "top", "bottom"]

DIMENSION_KEYWORDS = [
    "尺寸",
    "标注",
    "长度",
    "宽度",
    "高度",
    "厚度",
    "直径",
    "半径",
    "毫米",
    "厘米",
    "mm",
    "cm",
]

STYLE_IMAGE_KEYWORDS = [
    "动漫",
    "二次元",
    "卡通",
    "草图",
    "手绘",
    "插画",
    "头像",
    "挂件",
    "角色",
    "人物",
    "立绘",
    "玩偶",
    "娃娃",
    "发饰",
    "q版",
    "q 版",
    "可爱",
    "cartoon",
    "anime",
    "sketch",
    "illustration",
    "character",
    "doll",
    "figure",
    "chibi",
]

REAL_MULTIVIEW_KEYWORDS = [
    "真实照片",
    "实物",
    "摄影",
    "多视图重建",
    "照片重建",
    "扫描",
    "real photo",
    "photogrammetry",
    "scan",
    "multi-view reconstruction",
]

TRIPOSR_ENHANCED_KEYWORDS = [
    "TripoSR Enhanced",
    "triposr enhanced",
    "TripoSR精度",
    "TripoSR 精度",
    "不要扁平",
    "加厚",
    "厚度修正",
    "圆润",
]

TRIPOSR_FUSION_KEYWORDS = [
    "TripoSR Fusion",
    "triposr fusion",
    "融合",
    "多模型融合",
    "多视角融合",
    "分别生成",
    "分别参考",
    "正面背面融合",
    "正面侧面融合",
    "front.obj",
    "back.obj",
    "side.obj",
]


def analyze_request(intent, image_paths_for_agent):
    return analyze_three_view_request(intent, image_paths_for_agent)


def _existing_views(image_paths_for_agent):
    result = []
    for view in VIEW_ORDER:
        path = (image_paths_for_agent or {}).get(view)
        if path:
            result.append(view)
    return result


def _contains_any(text, keywords):
    lower = (text or "").lower()
    return any(keyword.lower() in lower for keyword in keywords)


def create_modeling_plan(intent, image_paths_for_agent, analysis=None, requested_backend=BACKEND_AUTO):
    available_views = _existing_views(image_paths_for_agent)
    reference_views = [view for view in available_views if view != "front"]
    has_dimensions = bool((analysis or {}).get("dimensions")) or _contains_any(intent, DIMENSION_KEYWORDS)
    looks_stylized = _contains_any(intent, STYLE_IMAGE_KEYWORDS)
    explicitly_real_multiview = _contains_any(intent, REAL_MULTIVIEW_KEYWORDS)

    reasons = []
    warnings = []

    if requested_backend and requested_backend != BACKEND_AUTO:
        backend = requested_backend
        reasons.append(f"User selected backend: {requested_backend}.")
    elif _contains_any(intent, TRIPOSR_FUSION_KEYWORDS):
        backend = BACKEND_TRIPOSR_FUSION
        reasons.append("The request asks to run TripoSR on multiple views and fuse the meshes in Blender.")
    elif len(reference_views) >= 1 and looks_stylized:
        backend = BACKEND_TRIPOSR_FUSION
        reasons.append(
            "Stylized/anime/character references are available, so the agent recommends TripoSR Fusion to use front plus reference meshes."
        )
    elif looks_stylized:
        backend = BACKEND_TRIPOSR_FUSION if len(reference_views) >= 1 else BACKEND_TRIPOSR
        reasons.append(
            "Stylized/anime/character requests use TripoSR Fusion when references exist, otherwise TripoSR."
        )
    elif len(reference_views) >= 1 and explicitly_real_multiview:
        backend = BACKEND_EXTERNAL_MULTIVIEW
        reasons.append("Multiple real-photo views were requested, so the agent recommends the multi-view backend.")
    else:
        backend = BACKEND_TRIPOSR
        if len(reference_views) >= 1:
            reasons.append(
                "Reference views were provided, but the request does not clearly say real-photo multi-view reconstruction, so Auto uses TripoSR to avoid MASt3R fragment artifacts."
            )
        else:
            reasons.append("Only one primary view is available, so the agent recommends TripoSR for the base mesh.")

    if "front" not in available_views:
        warnings.append("No front image is available. Generation may fail because the front image is required.")

    if len(reference_views) == 0:
        warnings.append("No reference views were uploaded. Back/side/top details will need to be inferred.")

    if has_dimensions:
        reasons.append("Dimension words or extracted dimensions were found, so Blender should preserve typed/measured proportions.")

    steps = [
        "Copy all uploaded images into the result folder and keep their view names.",
        "Analyze the natural language request and all available views.",
        f"Run {backend} to create the base model.",
        "Import or build the model in Blender.",
        "Remove black bases, display cylinders, and helper artifacts.",
        "Straighten, center, and ground the model.",
        "Use reference views and the request to correct visible details.",
        "Export result.blend, model.glb, model.fbx, model.stl, and preview.png.",
        "Run model checks after export.",
    ]

    quality_checks = [
        "model file exists",
        "model is not empty",
        "model is upright and centered",
        "no black base or unwanted flat cylinder",
        "Blender can open the file",
        "materials are present when expected",
        "reference views were included in the Blender modification prompt",
    ]

    return {
        "backend": backend,
        "requested_backend": requested_backend or BACKEND_AUTO,
        "available_views": available_views,
        "reference_views": reference_views,
        "has_dimensions": has_dimensions,
        "looks_stylized_or_sketch": looks_stylized,
        "explicitly_real_multiview": explicitly_real_multiview,
        "reasons": reasons,
        "warnings": warnings,
        "steps": steps,
        "quality_checks": quality_checks,
    }


def build_modeling_intent(intent, analysis, copied_refs):
    return build_blender_intent(intent, analysis, copied_refs)


def save_agent_analysis(result_dir, analysis):
    return save_analysis(result_dir, analysis)
