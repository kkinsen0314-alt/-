"""多轮工具调用 Agent，负责 RAG 注入和 Pydantic 结构化输出。"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from llm_client import LLMClient
from models import AnalysisReport, AnalysisRequest, AnalysisResponse, HistoryHit, ToolCallRecord
from observability import configure_logging, log_event
from rag import LocalRAG
from tools import TOOL_REGISTRY, ToolRegistry, tool_result_text


ROOT = Path(__file__).parent
RUNTIME_ROOT = Path(os.getenv("LIVE_AGENT_RUNTIME_DIR", tempfile.gettempdir())) / "live_agent"


SYSTEM_PROMPT = """
你是直播运营数据分析 Agent。你必须先使用工具获得确定性数据，再基于工具结果分析。

可用工具：
- funnel_analysis：核心漏斗和程序化阈值判断
- inviter_analysis：邀请人排行或指定邀请人钻取
- channel_analysis：渠道排行或指定渠道钻取

你可以在多轮中组合工具：先做漏斗，再针对异常邀请人或渠道继续钻取。
系统可能提供历史报告检索结果，请把它们作为参考证据，不要把历史数据冒充当前数据。

当分析完成后，只输出一个合法 JSON 对象，不要输出 Markdown 代码围栏、解释文字或额外字段。JSON 结构必须是：
{
  "title": "报告标题",
  "risk_level": "normal|attention|critical|insufficient_sample|incomplete_data",
  "summary": "结论摘要",
  "key_findings": ["数据发现"],
  "recommendations": [
    {"priority": "high|medium|low", "problem": "问题", "action": "动作", "expected_effect": "预期效果"}
  ],
  "evidence": [
    {"source": "工具名或历史报告", "metric": "指标", "value": "数值", "explanation": "说明"}
  ]
}
""".strip()


def _strip_json_fence(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _parse_report(text: str) -> AnalysisReport:
    value = _strip_json_fence(text)
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            raise ValueError("LLM 未返回合法 JSON 报告")
        payload = json.loads(match.group(0))
    return AnalysisReport.model_validate(payload)


class ToolCallingAgent:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        registry: Optional[ToolRegistry] = None,
        rag: Optional[LocalRAG] = None,
        logger=None,
    ):
        self.logger = logger or configure_logging(RUNTIME_ROOT / "logs" / "agent.jsonl")
        self.llm = llm or LLMClient(logger=self.logger)
        self.registry = registry or TOOL_REGISTRY
        self.rag = rag or LocalRAG(ROOT / "output", ROOT / "knowledge")

    def run(self, request: AnalysisRequest, run_id: Optional[str] = None) -> AnalysisResponse:
        run_id = run_id or str(uuid.uuid4())
        started_at = time.perf_counter()
        tool_records: list[ToolCallRecord] = []
        history_hits = self.rag.search(request.question, top_k=request.history_top_k)
        log_event(self.logger, "agent_start", run_id, {
            "file_path": request.file_path,
            "max_rounds": request.max_rounds,
            "history_hits": len(history_hits),
        })

        context = self.rag.context(history_hits)
        system_prompt = SYSTEM_PROMPT
        if context:
            system_prompt += "\n\n相关历史知识（仅作参考）：\n" + context

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._user_prompt(request)},
        ]

        try:
            for round_number in range(1, request.max_rounds + 1):
                log_event(self.logger, "agent_round_start", run_id, {"round": round_number})
                response = self.llm.chat_with_tools(
                    messages,
                    self.registry.schemas(),
                    temperature=0.2,
                    max_tokens=2500,
                    run_id=run_id,
                )
                if response.has_tool_calls:
                    self._append_assistant_tool_calls(messages, response)
                    for tool_call in response.tool_calls:
                        tool_started = time.perf_counter()
                        try:
                            arguments = dict(tool_call.arguments or {})
                            if tool_call.name == "funnel_analysis" and request.threshold_config_path:
                                arguments.setdefault("threshold_config_path", request.threshold_config_path)
                            result = self.registry.execute(tool_call.name, arguments)
                            result_text = tool_result_text(result)
                            record = ToolCallRecord(
                                name=tool_call.name,
                                arguments=arguments,
                                duration_ms=int((time.perf_counter() - tool_started) * 1000),
                                success=True,
                            )
                        except Exception as exc:
                            result_text = json.dumps({"error": str(exc)}, ensure_ascii=False)
                            record = ToolCallRecord(
                                name=tool_call.name,
                                arguments=tool_call.arguments or {},
                                duration_ms=int((time.perf_counter() - tool_started) * 1000),
                                success=False,
                                error=str(exc),
                            )
                        tool_records.append(record)
                        log_event(self.logger, "tool_call", run_id, record.model_dump())
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_text,
                        })
                    continue

                try:
                    report = _parse_report(response.content or "")
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    log_event(self.logger, "structured_output_retry", run_id, {
                        "round": round_number,
                        "error": str(exc),
                    })
                    if round_number == request.max_rounds:
                        raise
                    messages.append({"role": "assistant", "content": response.content or ""})
                    messages.append({
                        "role": "user",
                        "content": "上一次输出不是合法的目标 JSON。请基于已有工具结果重新输出，且只输出符合要求的 JSON。",
                    })
                    continue

                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                log_event(self.logger, "agent_completed", run_id, {
                    "rounds": round_number,
                    "tool_calls": len(tool_records),
                    "duration_ms": elapsed_ms,
                })
                return AnalysisResponse(
                    run_id=run_id,
                    status="completed",
                    report=report,
                    tool_calls=tool_records,
                    history_hits=[HistoryHit.model_validate(hit) for hit in history_hits],
                )

            raise RuntimeError("达到最大 Agent 轮数但未生成结构化报告")
        except Exception as exc:
            log_event(self.logger, "agent_failed", run_id, {"error": str(exc)})
            return AnalysisResponse(
                run_id=run_id,
                status="failed",
                tool_calls=tool_records,
                history_hits=[HistoryHit.model_validate(hit) for hit in history_hits],
                error=str(exc),
            )

    @staticmethod
    def _user_prompt(request: AnalysisRequest) -> str:
        return (
            f"数据文件：{request.file_path}\n"
            f"分析问题：{request.question}\n"
            "请先使用漏斗分析工具，再根据数据决定是否需要邀请人或渠道钻取。"
        )

    @staticmethod
    def _append_assistant_tool_calls(messages: list[dict], response) -> None:
        messages.append({
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in response.tool_calls
            ],
        })
