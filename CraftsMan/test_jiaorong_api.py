import os

from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APIStatusError


# 读取项目目录中的 .env 文件
load_dotenv()

api_key = os.getenv("JIAORONG_API_KEY")

if not api_key:
    raise RuntimeError(
        "没有读取到 JIAORONG_API_KEY，请检查项目根目录中的 .env 文件。"
    )


# 创建交融 MaaS 客户端
client = OpenAI(
    api_key=api_key,
    base_url="https://c4ai.ccccltd.cn/api/compatible/v1",

    # 交融平台可能拦截普通 Python HTTP 请求，
    # 官方文档建议添加 User-Agent
    default_headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
)


def ask_model(question: str) -> str:
    """向交融大模型发送问题并返回回答。"""

    if not question.strip():
        raise ValueError("问题不能为空。")

    response = client.chat.completions.create(
        # 第一次测试建议先使用基础模型
        model="jiaorong-instruct",

        messages=[
            {
                "role": "system",
                "content": (
                    "你是一名材料科学领域的智能问答助手。"
                    "请使用准确、清晰、结构化的中文回答问题。"
                ),
            },
            {
                "role": "user",
                "content": question,
            },
        ],

        # False：等待完整答案后一次性返回
        stream=False,

        # 越低回答越稳定，适合知识问答
        temperature=0.2,

        # 限制最大输出长度
        max_tokens=1500,
    )

    return response.choices[0].message.content or ""


def main() -> None:
    question = "请简要介绍功能防护涂层的主要类型。"

    try:
        answer = ask_model(question)

        print("问题：")
        print(question)

        print("\n回答：")
        print(answer)

    except APIStatusError as exc:
        print(f"接口请求失败，HTTP 状态码：{exc.status_code}")
        print(f"错误信息：{exc.response}")

    except APIConnectionError as exc:
        print("无法连接交融 MaaS 接口，请检查网络、代理或接口地址。")
        print(exc)

    except Exception as exc:
        print(f"程序运行失败：{exc}")


if __name__ == "__main__":
    main()