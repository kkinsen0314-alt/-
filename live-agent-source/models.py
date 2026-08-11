"""API 与 Agent 的结构化数据模型。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


RiskLevel = Literal["normal", "attention", "critical", "insufficient_sample", "incomplete_data"]
Priority = Literal["high", "medium", "low"]


class Recommendation(BaseModel):
    priority: Priority
    problem: str
    action: str
    expected_effect: str = ""


class Evidence(BaseModel):
    source: str
    metric: str = ""
    value: str = ""
    explanation: str = ""


class AnalysisReport(BaseModel):
    title: str
    risk_level: RiskLevel
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)
    duration_ms: int = 0
    success: bool = True
    error: str = ""


class HistoryHit(BaseModel):
    path: str
    title: str
    score: float
    snippet: str


class AnalysisRequest(BaseModel):
    file_path: str
    question: str = "请分析本场直播的核心问题并给出可执行建议。"
    max_rounds: int = Field(default=4, ge=1, le=8)
    threshold_config_path: Optional[str] = None
    history_top_k: int = Field(default=3, ge=0, le=10)


class AnalysisResponse(BaseModel):
    run_id: str
    status: Literal["completed", "failed"]
    report: Optional[AnalysisReport] = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    history_hits: list[HistoryHit] = Field(default_factory=list)
    error: str = ""
