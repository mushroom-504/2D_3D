import openai
from openai import OpenAI

class ReconstructionAgent:
    def __init__(self, api_key=None):
        # 建议从环境变量读取，更安全
        self.client = OpenAI(api_key=api_key)

    def process(self, image_path, intent):
        # 这里就可以调用 OpenAI 的接口了
        # 例如：self.client.chat.completions.create(...)
        pass

class ScriptingAgent:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        # 给大模型的系统提示，规定它只输出 Blender Python 代码
        self.system_msg = """
你是 Blender Python API 专家。
根据用户的要求，编写一个函数 `def modify_scene(model_path):`，该函数完成：
1. 清空场景所有物体
2. 导入 model_path 指向的 .obj 文件
3. 将导入的物体移到世界原点，应用平滑着色
4. 根据用户意图修改模型（例如添加底座、缩放、赋予材质等）
只输出完整的 Python 代码，不要有任何 markdown 标记或解释文字。
"""

    def generate_script(self, model_path: str, intent: str) -> str:
        """返回一段可直接在 Blender 里运行的 Python 脚本"""
        prompt = f"模型文件路径: {model_path}\n用户意图: {intent}\n请生成代码:"
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self.system_msg},
                {"role": "user", "content": prompt}
            ]
        )
        code = response.choices[0].message.content
        # 去除可能的代码块标记
        code = code.replace("```python", "").replace("```", "").strip()
        return code