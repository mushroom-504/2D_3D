# CraftsMan 远程生成 API

本项目可在本机没有 NVIDIA CUDA 时，通过远程 CraftsMan 服务生成 OBJ。桌面程序默认使用稳定的 TripoSR；选择“CraftsMan 远程服务”时，只调用远程 API，不再检查或启动本地 CraftsMan 环境。

## 1. 配置密钥

不要把真实密钥写入源码或提交到 Git。请在项目根目录的 `.env` 文件中加入：

```text
CRAFTSMAN_API_KEY=your_key_here
```

`.env` 已由 `.gitignore` 忽略。程序会自动读取这个变量。

## 2. 配置文件

远程服务配置位于 `fix/config.json`：

```json
{
  "runtime": {
    "craftsman_mode": "remote_only"
  },
  "craftsman_api": {
    "enabled": true,
    "generate_url": "https://www.sanrenxietong.com/craftsman-api/generate",
    "health_url": "https://www.sanrenxietong.com/craftsman-api/health",
    "api_key_env": "CRAFTSMAN_API_KEY"
  }
}
```

支持的模式：

- `remote_preferred`：先远程，失败后尝试本地。
- `local_preferred`：先本地，失败后尝试远程。
- `remote_only`：只允许远程。
- `local_only`：只允许本地。

界面的“禁止自动降级”控制的是 CraftsMan 整体失败后是否切换到 TripoSR；无论是否降级，界面和任务记录都会分别显示“请求后端”“实际后端”和“降级原因”。

## 3. API 约定

### 健康检查

发送 `GET` 请求到 `health_url`。服务应返回包含以下信息的 JSON：

```json
{
  "status": "ok",
  "model_loaded": true,
  "device": "cuda",
  "busy": false
}
```

### 生成模型

发送 `POST` 请求到 `generate_url`，请求头：

```text
Content-Type: application/json
X-API-Key: <CRAFTSMAN_API_KEY>
```

请求体包含 Base64 图片及生成参数：

```json
{
  "image_base64": "<base64 image>",
  "steps": 50,
  "seed": 0,
  "guidance_scale": 5.0,
  "octree_depth": 7,
  "remove_background": true,
  "foreground_ratio": 1.0
}
```

成功响应示例：

```json
{
  "success": true,
  "task_id": "remote-task-id",
  "elapsed_seconds": 120.5,
  "obj_base64": "<base64 obj>"
}
```

当前项目使用 `remote_only`。客户端限制图片最大 10 MB，生成超时默认 300 秒。远程任务 ID、耗时和服务信息会写入结果目录旁的元数据文件，并进入本地 SQLite 任务日志。

## 4. 验证

启动桌面程序后点击“后端体检”。CraftsMan 项会分别报告：

- 远程 API 是否可用；
- 远程 CraftsMan 模型是否已经加载；
- 当前使用模式；
- 远程服务设备与忙碌状态。

若没有视觉模型密钥，界面会明确显示“规则模式：不具备图片内容理解能力”；这不影响 TripoSR/CraftsMan 建模，但程序不会声称已经理解参考图内容。
