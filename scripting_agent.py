import torch
from tsr.system import TSR
from PIL import Image
import os

class ReconstructionAgent:
    def __init__(self):
        # 加载预训练的 TripoSR 模型
        self.model = TSR.from_pretrained(
            "stabilityai/TripoSR",
            config_file="config.yaml"   # TripoSR 自带的配置文件，不需要自己写
        )
        # 如果有 NVIDIA 显卡就用 GPU 加速，否则用 CPU
        self.model.to("cuda" if torch.cuda.is_available() else "cpu")

    def image_to_3d(self, image_path: str) -> str:
        """
        输入图片路径，返回生成的 .obj 模型文件路径
        """
        # 1. 打开图片并确保是 RGB 格式
        img = Image.open(image_path).convert("RGB")
        # 2. 用 AI 模型推理（不开梯度，节约显存）
        with torch.no_grad():
            scene = self.model(img, device=self.model.device)
        # 3. 构造输出路径：原图名 + _recon.obj
        out_path = os.path.splitext(image_path)[0] + "_recon.obj"
        # 4. 导出三维网格文件
        scene.export(out_path)
        return out_path