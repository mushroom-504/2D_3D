import os
import shutil
import subprocess
from pathlib import Path


DESKTOP = Path.home() / "Desktop"

TOOL_HINTS = {
    "MeshLab": {
        "purpose": "清理、修复、平滑、简化 TripoSR 生成的网格。",
        "env": "MESHLABSERVER_EXE",
        "paths": [
            r"C:\Program Files\VCG\MeshLab\meshlabserver.exe",
            r"C:\Program Files\MeshLab\meshlabserver.exe",
            str(DESKTOP / "MeshLab" / "meshlabserver.exe"),
        ],
    },
    "Instant Meshes": {
        "purpose": "把杂乱三角面重新拓扑成更干净的四边面，适合后续在 Blender 里精修。",
        "env": "INSTANT_MESHES_EXE",
        "paths": [
            r"C:\Program Files\Instant Meshes\Instant Meshes.exe",
            r"C:\Program Files\InstantMeshes\Instant Meshes.exe",
            str(DESKTOP / "Instant Meshes" / "Instant Meshes.exe"),
            str(DESKTOP / "InstantMeshes" / "Instant Meshes.exe"),
            str(DESKTOP / "instant-meshes" / "Instant Meshes.exe"),
        ],
    },
    "MeshLib": {
        "purpose": "用 Python 做网格修复、平滑、布尔、简化、距离计算。",
        "env": "",
        "paths": [],
    },
}


def _find_executable(names, candidate_paths, env_name=""):
    if env_name:
        env_path = os.environ.get(env_name)
        if env_path and Path(env_path).exists():
            return env_path

    for candidate in candidate_paths:
        path = Path(candidate)
        if path.exists():
            return str(path)

    for name in names:
        found = shutil.which(name)
        if found:
            return found

    return ""


def detect_refinement_tools():
    """Detect free/local mesh-refinement tools without making generation depend on them."""
    tools = {}

    tools["MeshLab"] = {
        "installed": False,
        "path": _find_executable(
            ["meshlabserver.exe", "meshlabserver"],
            TOOL_HINTS["MeshLab"]["paths"],
            TOOL_HINTS["MeshLab"]["env"],
        ),
        "purpose": TOOL_HINTS["MeshLab"]["purpose"],
    }
    tools["MeshLab"]["installed"] = bool(tools["MeshLab"]["path"])

    tools["Instant Meshes"] = {
        "installed": False,
        "path": _find_executable(
            ["Instant Meshes.exe", "InstantMeshes.exe", "instant-meshes.exe"],
            TOOL_HINTS["Instant Meshes"]["paths"],
            TOOL_HINTS["Instant Meshes"]["env"],
        ),
        "purpose": TOOL_HINTS["Instant Meshes"]["purpose"],
    }
    tools["Instant Meshes"]["installed"] = bool(tools["Instant Meshes"]["path"])

    try:
        import meshlib  # noqa: F401

        meshlib_installed = True
    except Exception:
        meshlib_installed = False

    tools["MeshLib"] = {
        "installed": meshlib_installed,
        "path": "python package: meshlib" if meshlib_installed else "",
        "purpose": TOOL_HINTS["MeshLib"]["purpose"],
    }
    return tools


def write_refinement_report(result_dir, model_files=None):
    result_dir = Path(result_dir)
    model_files = model_files or {}
    tools = detect_refinement_tools()
    report_path = result_dir / "free_refinement_tools.txt"

    lines = [
        "免费本地模型精修工具检测报告",
        "",
        "用途：",
        "这个文件告诉你当前电脑上哪些免费精修工具可以接到智能体后面使用。",
        "它不会替代 TripoSR 生成模型，而是用于生成后继续清理、平滑、重拓扑、修复网格。",
        "",
        "当前模型文件：",
    ]

    for label, path in model_files.items():
        if path:
            lines.append(f"- {label}: {path}")

    lines.extend(["", "工具检测："])
    for name, info in tools.items():
        status = "已找到" if info["installed"] else "未找到"
        lines.append(f"- {name}: {status}")
        lines.append(f"  作用: {info['purpose']}")
        if info["path"]:
            lines.append(f"  路径: {info['path']}")

    lines.extend(
        [
            "",
            "建议使用顺序：",
            "1. 先用 TripoSR Fusion 生成多视角融合基础模型。",
            "2. 如果模型破洞、碎片多，优先用 MeshLab 清理和平滑。",
            "3. 如果模型面数乱、后续不好编辑，再用 Instant Meshes 重新拓扑。",
            "4. 如果以后想写更强的自动修复脚本，再接 MeshLib 的 Python 功能。",
            "",
            "Instant Meshes 便携版说明：",
            "如果你已经安装但这里显示未找到，可以把它的 exe 路径写入环境变量 INSTANT_MESHES_EXE。",
            "例如：INSTANT_MESHES_EXE=C:\\你的路径\\Instant Meshes.exe",
            "",
            "注意：",
            "这些工具只能精修已有模型，不能凭空生成类似付费 3D 大模型那种完整角色语义结构。",
            "想让角色更像原图，仍然需要更强的生成后端，或者在 Blender 中做结构化补形。",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path, tools


def try_run_meshlab_cleanup(input_obj, output_obj, log_callback=None):
    """Optional MeshLab cleanup. It only runs when meshlabserver is installed."""
    tools = detect_refinement_tools()
    meshlab = tools["MeshLab"]
    if not meshlab["installed"]:
        return None

    input_obj = Path(input_obj)
    output_obj = Path(output_obj)
    output_obj.parent.mkdir(parents=True, exist_ok=True)
    script_path = output_obj.with_suffix(".mlx")
    script_path.write_text(
        """<!DOCTYPE FilterScript>
<FilterScript>
 <filter name="Remove Duplicate Vertices"/>
 <filter name="Remove Duplicate Faces"/>
 <filter name="Remove Unreferenced Vertices"/>
 <filter name="Laplacian Smooth">
  <Param name="stepSmoothNum" value="2" description="Smoothing steps" type="RichInt"/>
  <Param name="Boundary" value="true" description="Smooth boundary" type="RichBool"/>
  <Param name="cotangentWeight" value="true" description="Cotangent weighting" type="RichBool"/>
 </filter>
</FilterScript>
""",
        encoding="utf-8",
    )

    command = [
        meshlab["path"],
        "-i",
        str(input_obj),
        "-o",
        str(output_obj),
        "-s",
        str(script_path),
    ]
    if log_callback:
        log_callback("MeshLab cleanup: running local mesh cleanup.")
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.returncode != 0:
        if log_callback:
            log_callback("MeshLab cleanup failed, keeping original model.")
            log_callback((result.stderr or result.stdout)[:1200])
        return None
    return output_obj
