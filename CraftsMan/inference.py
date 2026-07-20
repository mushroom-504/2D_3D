from pathlib import Path

import torch
from craftsman import CraftsManPipeline


PROJECT_DIR = Path(__file__).resolve().parent

# 输入图片
INPUT_IMAGE = Path(
    r"C:\Users\荣\Desktop\2713ebe3ba996b149f9171f1dca22a78.jpeg"
)

# 输出目录
OUTPUT_DIR = PROJECT_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_MESH = OUTPUT_DIR / "craftsman_result.obj"


if not INPUT_IMAGE.exists():
    raise FileNotFoundError(f"输入图片不存在：{INPUT_IMAGE}")

# if not torch.cuda.is_available():
#     raise RuntimeError(
#         "CraftsMan 没有检测到可用的 NVIDIA CUDA 显卡。"
#         "请先检查 PyTorch CUDA 和显卡驱动。"
#     )

print("运行设备：CPU")

pipeline = CraftsManPipeline.from_pretrained(
    "craftsman3d/craftsman-DoraVAE",
    device="cpu",
    torch_dtype=torch.float32,
)

print("正在生成三维网格……")

result = pipeline(
    str(INPUT_IMAGE),
    num_inference_steps=50,
    guidance_scale=7.5,
    seed=42,
)

if not result.meshes:
    raise RuntimeError("CraftsMan 没有返回任何网格。")

mesh = result.meshes[0]
mesh.export(str(OUTPUT_MESH))

print("模型生成完成：", OUTPUT_MESH)