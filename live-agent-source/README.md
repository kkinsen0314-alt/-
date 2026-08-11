# 直播运营数据智能分析 Agent

本项目提供一个可供 Dify 或其他编排器调用的本地 FastAPI 服务：读取 CSV/Excel，完成数据清洗、漏斗计算、阈值判断、邀请人/渠道钻取，并可通过多轮工具调用和结构化 LLM 输出生成分析报告。

## 升级架构

```text
FastAPI
  -> 文件上传或受限本地路径
  -> 数据探索 / 漏斗分析 / 邀请人分析 / 渠道分析
  -> ToolCallingAgent
       -> 本地历史报告 RAG
       -> LLM 多轮工具调用
       -> Pydantic 结构化报告
  -> JSONL 日志
```

## 安装与启动

在项目目录执行：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

启动后可访问：

- [健康检查](http://127.0.0.1:8000/health)
- [Swagger 文档](http://127.0.0.1:8000/docs)
- [工具 Schema](http://127.0.0.1:8000/tools)

### 可选配置

```powershell
$env:LLM_API_KEY = "your-api-key"
$env:LLM_BASE_URL = "https://api.deepseek.com"
$env:LLM_MODEL = "deepseek-chat"
$env:LIVE_AGENT_API_KEY = "local-service-key"
$env:LIVE_AGENT_DATA_ROOT = "D:\data\live"
$env:LIVE_AGENT_MAX_UPLOAD_MB = "20"
```

`LIVE_AGENT_API_KEY` 设置后，除健康检查和工具 Schema 外的接口都需要请求头 `X-API-Key`。设置 `LIVE_AGENT_DATA_ROOT` 后，`file_path` 只能访问该目录及其子目录。

## HTTP 接口

所有分析接口均使用 `multipart/form-data`。输入文件有两种方式，二选一：

- `file`：上传 CSV/Excel 文件，适合 Dify 调用。
- `file_path`：服务端本地文件路径，适合同机脚本或定时任务。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/tools`、`/v1/tools` | 导出 3 个工具的 function schema |
| POST | `/v1/tools/explore` | 数据规模、质量和可用维度 |
| POST | `/v1/tools/funnel` | 漏斗指标和三级阈值判断 |
| POST | `/v1/tools/inviter` | 邀请人排行或指定邀请人钻取 |
| POST | `/v1/tools/channel` | 渠道排行或指定渠道钻取 |
| POST | `/v1/analyze` | 数据探索 + 漏斗 + 可选维度钻取 |
| POST | `/v1/agent/analyze` | 多轮 Agent 分析和结构化报告 |

### 调用示例

本地路径调用：

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/analyze `
  -H "X-API-Key: local-service-key" `
  -F "file_path=D:\data\live\直播数据.xlsx" `
  -F "dimension=channel" `
  -F "top_n=10"
```

上传文件调用：

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/tools/funnel `
  -H "X-API-Key: local-service-key" `
  -F "file=@D:\data\live\直播数据.xlsx"
```

Agent 调用：

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/agent/analyze `
  -H "X-API-Key: local-service-key" `
  -F "file=@D:\data\live\直播数据.xlsx" `
  -F "question=请分析漏斗问题，并重点关注表现异常的邀请人和渠道" `
  -F "max_rounds=4" `
  -F "history_top_k=3"
```

`/v1/agent/analyze` 需要配置 `LLM_API_KEY`。如果只验证确定性分析，可先使用 `/v1/analyze` 或 `/v1/tools/*`，无需调用 LLM。

## 三个真实工具

`tools.py` 中的 `ToolRegistry` 统一管理工具名称、描述、参数 Schema 和执行函数：

- `funnel_analysis`：计算到课、完课、商品访问、领券、支付和购买等漏斗指标，并执行程序化阈值判断。
- `inviter_analysis`：按邀请人统计表现，支持 `inviter_name` 指定邀请人和 `top_n` 限制返回数量。
- `channel_analysis`：按渠道统计表现，支持 `channel_name` 指定渠道和 `top_n` 限制返回数量。

Agent 会根据上一轮工具结果决定是否继续调用其他工具；程序负责计算和判定，LLM 负责解释、归因和建议。

## RAG、重试与日志

- `rag.py` 检索 `output/` 历史 Markdown 报告和 `knowledge/` 知识文档，并在响应中保留 `history_hits`。
- `llm_client.py` 对超时、网络错误及 408/429/5xx 临时错误进行指数退避重试，默认最多 3 次。
- Agent 和 API 日志写入 `logs/agent.jsonl`、`logs/api.jsonl`，通过 `run_id` 串联调用链。

当前 RAG 使用本地词项检索，不依赖外部向量库，后续可以替换为向量检索而不改变 API 接口。

## 评测与测试

执行单元测试：

```powershell
python -m unittest discover -s tests -v
```

使用真实 CSV/Excel 评测三个工具：

```powershell
python evals/real_data_eval.py `
  "D:\data\live\live-1.xlsx" `
  "D:\data\live\live-2.xlsx"
```

结果写入 `evals/real_data_eval_latest.json`。

## Dify 接入注意事项

Dify 云端无法直接访问你电脑上的 `127.0.0.1` 或 `localhost`。本地 FastAPI 完成后，要接入 Dify 还需要把服务部署到 Dify 可访问的 HTTPS 地址，或使用内网穿透/反向代理；同时建议开启 `LIVE_AGENT_API_KEY`，并仅暴露必要的上传接口。

第一阶段可直接导入 `dify_openapi.yaml`，让 Dify 调用 `/v1/agent/analyze`；详细步骤见 `DIFY_SETUP.md`。

## 兼容旧 CLI

原有 Pipeline CLI 保留：

```powershell
python agent.py data.xlsx --mode all
```

## 项目结构

```text
api.py                    FastAPI 服务入口
dify_openapi.yaml         Dify 可导入的 Agent API 描述
DIFY_SETUP.md             Dify 接入与公网服务说明
agent_loop.py             多轮 Agent、RAG 注入、结构化输出
tools.py                  三个真实工具和 ToolRegistry
rag.py                    本地 RAG 封装
llm_client.py             OpenAI 兼容 API、function calling、重试
models.py                 Pydantic 请求、响应和报告模型
observability.py          JSONL 日志
analyzer.py               数据读取、清洗、漏斗和分组统计
thresholds.py             确定性阈值判断
knowledge/                本地业务知识库
  analysis_guidelines.md  分析总原则与证据优先级
  metric_definitions.md   指标口径、字段和数据质量
  anomaly_diagnosis.md    异常现象与排查方向
  threshold_guidance.md   阈值解释与使用边界
  optimization_playbook.md  运营动作与复盘闭环
evals/                    真实数据评测脚本和结果
tests/                    单元测试和接口测试
output/                   历史报告
```
