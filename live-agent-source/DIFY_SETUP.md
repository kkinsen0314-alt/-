# Dify 接入说明

## 推荐接入方式

第一阶段让 Dify 作为聊天入口和文件上传层，调用本项目的 `POST /v1/agent/analyze`。数据清洗、RAG、阈值判断、三个分析工具和报告生成继续由本项目负责，改动最少。

## 接入前提

Dify Cloud 不能访问本机 `127.0.0.1`。需要先把 FastAPI 服务暴露为 Dify 可访问的 HTTPS 地址，例如部署到云服务器，或使用受控的内网穿透。不要把带有 API Key 的地址写进 OpenAPI 文件。

## Dify 配置步骤

1. 启动 FastAPI：`python -m uvicorn api:app --host 0.0.0.0 --port 8000`。
2. 将 `dify_openapi.yaml` 中的 `servers.url` 替换为公网 HTTPS 地址。
3. 在 Dify 的工具/插件中导入 `dify_openapi.yaml`。
4. 配置请求头 `X-API-Key`，值与服务端的 `LIVE_AGENT_API_KEY` 一致。
5. 创建 Dify Agent 或 Workflow，把上传文件传给 `file` 参数，把用户问题传给 `question` 参数。
6. 用一份脱敏 CSV/Excel 测试，确认返回 `status=completed`、`report`、`tool_calls` 和 `history_hits`。

## Dify 知识库的两种选择

- 快速接入：继续使用项目内 `knowledge/` 和 `output/` 的本地 RAG，Dify 只负责入口。
- 深度迁移：将 `knowledge/` 下的 5 个 Markdown 文件上传到 Dify 知识库，再把 `/v1/tools/funnel`、`/v1/tools/inviter`、`/v1/tools/channel` 分别配置成 HTTP 工具，由 Dify 工作流负责多轮调用。这个方案需要重新设计工作流，不能只上传 Python 文件。

## 不要上传或暴露

- `.env`、LLM API Key 和服务 API Key
- 手机号、姓名等未脱敏的业务数据
- `logs/`、`tmp/`、`__pycache__/`
- 仅适用于本机的 `file_path`
