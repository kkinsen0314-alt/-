# Coze Coding 部署说明

## 启动命令

```bash
python -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
```

## 必需环境变量

- `LLM_API_KEY`：LLM 服务密钥，不写入代码或 ZIP 文件。
- `LLM_BASE_URL`：OpenAI 兼容接口地址，例如 `https://api.deepseek.com`。
- `LLM_MODEL`：模型名称，例如 `deepseek-chat`。

## 可选环境变量

- `LIVE_AGENT_API_KEY`：保护分析接口的 API Key。
- `LIVE_AGENT_MAX_UPLOAD_MB`：上传文件大小限制，默认 20MB。
- `LIVE_AGENT_DATA_ROOT`：服务端本地路径允许访问的根目录。云端建议使用文件上传，不依赖本地 `file_path`。

## 主要接口

- `GET /health`：健康检查。
- `GET /tools`：查看 3 个分析工具的 Schema。
- `POST /v1/analyze`：返回数据探索、漏斗分析和可选维度钻取结果。
- `POST /v1/agent/analyze`：上传 CSV/Excel 并生成多轮 Agent 分析报告。

分析接口使用 `multipart/form-data`，输入文件使用 `file` 字段；`file_path` 只适合同机调用。

## 部署前检查

1. 确认 `message status` 已经是 `done`。
2. 确认 `LLM_API_KEY` 已配置为 Coze 环境变量。
3. 不要把 `.env`、日志、缓存、原始业务数据和未脱敏历史报告上传到项目。
4. 执行 `python -m unittest discover -s tests -v`。
