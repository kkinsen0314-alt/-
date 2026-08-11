# 腾讯云 SCF Web 函数部署

本项目使用腾讯云 SCF 的 Python 3.9 Web 函数运行时。请使用 `dist/live-agent-scf.zip`，不要使用 Coze 的部署包。

## 本地构建

```powershell
D:\py\python.exe scripts\build_scf_package.py
```

构建脚本会下载 Linux x86_64 / Python 3.9 依赖，并将以下内容写入 ZIP 根目录：

- FastAPI 与 Agent 代码
- `scf_bootstrap` 启动文件
- `config/` 阈值配置
- `knowledge/` 和 `output/` 的本地 RAG 资料

不会打入 API Key、本地上传文件、日志、测试和原始直播数据。

## 控制台配置

1. 在“函数代码”中选择“本地上传 ZIP 包”，上传 `dist/live-agent-scf.zip`。
2. 保存后，在 Web 函数配置中将项目监听端口设置为 `9000`。
3. 在“环境变量”中设置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LIVE_AGENT_API_KEY`、`LIVE_AGENT_MAX_UPLOAD_MB`。
4. 在“函数 URL”中创建公网 URL。使用 `NONE` 鉴权时必须设置强随机 `LIVE_AGENT_API_KEY`，并由调用方通过 `X-API-Key` 请求头传入。
5. 部署后访问 `/health`，返回 `{ "status": "ok" }` 后再接入 Dify。
