import os
import time

import gradio as gr

from reconstruction_agent import ReconstructionAgent
from reconstruction_agent import ScriptingAgent

# 初始化智能体
recon_agent = ReconstructionAgent()
# 请把你的 OpenAI API key 填在这里
script_agent = ScriptingAgent(api_key="sk-你的API密钥")

# 指令文件和结果文件夹路径（需与 Blender 执行脚本中的路径一致）
COMMAND_FILE = "C:/agent_temp/command.txt"
RESULT_DIR = "C:/agent_temp/results/"
PREVIEW_PATH = os.path.join(RESULT_DIR, "preview.png")
BLEND_PATH = os.path.join(RESULT_DIR, "result.blend")

def process(uploaded_image, intent):
    """处理上传的图片和文字要求，返回预览图和工程文件"""
    # 1. 保存上传的图片
    img_path = "uploaded_img.png"
    uploaded_image.save(img_path)

    # 2. 用重建智能体生成粗糙3D模型
    model_path = recon_agent.image_to_3d(img_path)

    # 3. 用脚本智能体生成 Blender 代码
    blender_code = script_agent.generate_script(model_path, intent)

    # 4. 将代码写入指令文件，发送给 Blender
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        f.write(blender_code)

    # 5. 等待 Blender 完成（轮询结果文件）
    for _ in range(30):  # 最多等 60 秒
        if os.path.exists(PREVIEW_PATH):
            # 返回预览图和工程文件
            return PREVIEW_PATH, BLEND_PATH
        time.sleep(2)

    return None, "超时，请确认 Blender 是否启动并运行了执行脚本。"

# 搭建 Gradio 界面
iface = gr.Interface(
    fn=process,
    inputs=[
        gr.Image(type="pil", label="上传图片"),
        gr.Textbox(label="建模要求", placeholder="例如：加上圆柱底座，材质改成金色")
    ],
    outputs=[
        gr.Image(label="渲染预览"),
        gr.File(label="下载 Blender 工程文件")
    ],
    title="图片→3D 建模智能体"
)

# 启动网页服务
iface.launch()