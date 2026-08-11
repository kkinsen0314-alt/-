"""本地 FastAPI 服务：提供直播数据分析工具接口。"""

import hmac
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

try:
    from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.responses import PlainTextResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - requires optional service dependencies
    raise RuntimeError("请先安装服务依赖: pip install -r requirements.txt") from exc

from observability import configure_logging, log_event
from agent_loop import ToolCallingAgent
from dify_formatter import format_dify_report
from models import AnalysisRequest, AnalysisResponse
from tools import TOOL_REGISTRY, execute_tool, explore_data


ROOT = Path(__file__).parent
RUNTIME_ROOT = Path(os.getenv("LIVE_AGENT_RUNTIME_DIR", tempfile.gettempdir())) / "live_agent"
UPLOAD_ROOT = RUNTIME_ROOT / "api_uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_SUFFIXES = {".csv", ".xls", ".xlsx", ".xlsm"}
MAX_UPLOAD_BYTES = int(os.getenv("LIVE_AGENT_MAX_UPLOAD_MB", "20")) * 1024 * 1024
logger = configure_logging(RUNTIME_ROOT / "logs" / "api.jsonl")

app = FastAPI(
    title="直播运营数据分析 Agent API",
    version="1.0.0",
    description="为 Dify 或其他编排器提供直播数据探索、漏斗分析和分组钻取工具。",
)


class ToolResponse(BaseModel):
    run_id: str
    tool: str
    status: str = "completed"
    result: dict[str, Any]


class CombinedAnalysisResponse(BaseModel):
    run_id: str
    status: str = "completed"
    source: str
    explore: dict[str, Any]
    funnel: dict[str, Any]
    drilldown: dict[str, Any] = Field(default_factory=dict)


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("LIVE_AGENT_API_KEY", "")
    if expected and not x_api_key:
        raise HTTPException(status_code=401, detail="缺少 X-API-Key")
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=403, detail="X-API-Key 无效")


def _validate_local_path(file_path: str) -> Path:
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=400, detail="file_path 不存在或不是文件")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 CSV、XLS、XLSX 和 XLSM 文件")
    data_root = os.getenv("LIVE_AGENT_DATA_ROOT")
    if data_root:
        allowed_root = Path(data_root).expanduser().resolve()
        if allowed_root not in path.parents and path != allowed_root:
            raise HTTPException(status_code=403, detail="文件不在 LIVE_AGENT_DATA_ROOT 范围内")
    return path


async def _materialize_input(file_path: Optional[str], upload: Optional[UploadFile]) -> Tuple[Path, Any]:
    if bool(file_path) == bool(upload):
        raise HTTPException(status_code=400, detail="请提供 file_path 或上传 file，不能同时提供或都不提供")
    if file_path:
        return _validate_local_path(file_path), None

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="上传文件必须是 CSV、XLS、XLSX 或 XLSM")
    temp_dir = tempfile.TemporaryDirectory(dir=UPLOAD_ROOT)
    target = Path(temp_dir.name) / f"input{suffix}"
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        temp_dir.cleanup()
        raise HTTPException(status_code=413, detail="上传文件超过大小限制")
    target.write_bytes(content)
    return target, temp_dir


def _error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, (FileNotFoundError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="分析服务内部错误")


async def _call_tool(tool_name: str, arguments: dict[str, Any], run_id: str) -> dict:
    started = time.perf_counter()
    log_event(logger, "tool_started", run_id, {"tool": tool_name})
    try:
        result = execute_tool(tool_name, arguments)
        duration_ms = round((time.perf_counter() - started) * 1000)
        log_event(logger, "tool_finished", run_id, {"tool": tool_name, "duration_ms": duration_ms})
        return result
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000)
        log_event(logger, "tool_failed", run_id, {
            "tool": tool_name,
            "duration_ms": duration_ms,
            "error_type": type(exc).__name__,
        })
        raise


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
@app.get("/v1/tools")
def tools_endpoint() -> dict[str, list[dict]]:
    return {"tools": TOOL_REGISTRY.schemas()}


@app.post("/v1/tools/explore", response_model=ToolResponse, dependencies=[Depends(verify_api_key)])
async def explore_endpoint(
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
) -> ToolResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        result = explore_data(str(path))
        return ToolResponse(run_id=run_id, tool="explore_data", result=result)
    except Exception as exc:
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()


@app.post("/v1/tools/funnel", response_model=ToolResponse, dependencies=[Depends(verify_api_key)])
async def funnel_endpoint(
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
) -> ToolResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        result = await _call_tool("funnel_analysis", {"file_path": str(path)}, run_id)
        return ToolResponse(run_id=run_id, tool="funnel_analysis", result=result)
    except Exception as exc:
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()


@app.post("/v1/tools/inviter", response_model=ToolResponse, dependencies=[Depends(verify_api_key)])
async def inviter_endpoint(
    inviter_name: Optional[str] = Form(default=None),
    top_n: int = Form(default=10, ge=1, le=50),
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
) -> ToolResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        result = await _call_tool(
            "inviter_analysis",
            {"file_path": str(path), "inviter_name": inviter_name, "top_n": top_n},
            run_id,
        )
        return ToolResponse(run_id=run_id, tool="inviter_analysis", result=result)
    except Exception as exc:
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()


@app.post("/v1/tools/channel", response_model=ToolResponse, dependencies=[Depends(verify_api_key)])
async def channel_endpoint(
    channel_name: Optional[str] = Form(default=None),
    top_n: int = Form(default=10, ge=1, le=50),
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
) -> ToolResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        result = await _call_tool(
            "channel_analysis",
            {"file_path": str(path), "channel_name": channel_name, "top_n": top_n},
            run_id,
        )
        return ToolResponse(run_id=run_id, tool="channel_analysis", result=result)
    except Exception as exc:
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()


@app.post("/v1/analyze", response_model=CombinedAnalysisResponse, dependencies=[Depends(verify_api_key)])
async def analyze_endpoint(
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
    dimension: Optional[str] = Form(default=None),
    top_n: int = Form(default=10, ge=1, le=50),
) -> CombinedAnalysisResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    log_event(logger, "request_started", run_id, {"endpoint": "/v1/analyze"})
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        explore = explore_data(str(path))
        funnel = await _call_tool("funnel_analysis", {"file_path": str(path)}, run_id)
        drilldown = {}
        if dimension:
            if dimension == "inviter":
                drilldown = await _call_tool(
                    "inviter_analysis",
                    {"file_path": str(path), "top_n": top_n},
                    run_id,
                )
            elif dimension == "channel":
                drilldown = await _call_tool(
                    "channel_analysis",
                    {"file_path": str(path), "top_n": top_n},
                    run_id,
                )
            else:
                raise ValueError("dimension 必须是 inviter 或 channel")
        log_event(logger, "request_finished", run_id, {"endpoint": "/v1/analyze"})
        return CombinedAnalysisResponse(
            run_id=run_id,
            source=explore["data_source"],
            explore=explore,
            funnel=funnel,
            drilldown=drilldown,
        )
    except Exception as exc:
        log_event(logger, "request_failed", run_id, {"endpoint": "/v1/analyze", "error_type": type(exc).__name__})
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()


@app.post("/v1/agent/analyze", response_model=AnalysisResponse, dependencies=[Depends(verify_api_key)])
async def agent_analyze_endpoint(
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
    question: str = Form(default="请分析本场直播的核心问题并给出可执行建议。"),
    max_rounds: int = Form(default=4, ge=1, le=8),
    history_top_k: int = Form(default=3, ge=0, le=10),
) -> AnalysisResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    log_event(logger, "agent_request_started", run_id, {"endpoint": "/v1/agent/analyze"})
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        request = AnalysisRequest(
            file_path=str(path),
            question=question,
            max_rounds=max_rounds,
            history_top_k=history_top_k,
        )
        result = ToolCallingAgent().run(request, run_id=run_id)
        log_event(logger, "agent_request_finished", run_id, {"status": result.status})
        return result
    except Exception as exc:
        log_event(logger, "agent_request_failed", run_id, {"error_type": type(exc).__name__})
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()


@app.post("/v1/dify/analyze", response_class=PlainTextResponse, dependencies=[Depends(verify_api_key)])
async def dify_analyze_endpoint(
    file: Optional[UploadFile] = File(default=None),
    file_path: Optional[str] = Form(default=None),
    question: str = Form(default="请分析本场直播的核心问题，并给出可执行的优化建议。"),
    max_rounds: int = Form(default=4, ge=1, le=8),
    history_top_k: int = Form(default=3, ge=0, le=10),
) -> PlainTextResponse:
    run_id = uuid.uuid4().hex
    temp_dir = None
    log_event(logger, "dify_request_started", run_id, {"endpoint": "/v1/dify/analyze"})
    try:
        path, temp_dir = await _materialize_input(file_path, file)
        request = AnalysisRequest(
            file_path=str(path),
            question=question,
            max_rounds=max_rounds,
            history_top_k=history_top_k,
        )
        result = ToolCallingAgent().run(request, run_id=run_id)
        log_event(logger, "dify_request_finished", run_id, {"status": result.status})
        return PlainTextResponse(format_dify_report(result))
    except Exception as exc:
        log_event(logger, "dify_request_failed", run_id, {"error_type": type(exc).__name__})
        raise _error_response(exc) from exc
    finally:
        if temp_dir:
            temp_dir.cleanup()
