"""Render concise Markdown for Dify's direct reply node."""

from __future__ import annotations

from models import AnalysisResponse, Evidence


RISK_LABELS = {
    "normal": "正常",
    "attention": "关注",
    "critical": "严重",
    "insufficient_sample": "样本不足",
    "incomplete_data": "数据不完整",
}
FOCUS_METRICS = ("完课率", "领券率", "购买率", "商品访问率", "到课率")
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _compact(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。；、 ") + "..."


def _focus_evidence(evidence: list[Evidence]) -> list[Evidence]:
    selected = []
    for metric in FOCUS_METRICS:
        match = next((item for item in evidence if metric in item.metric), None)
        if match:
            selected.append(match)
    return selected[:3]


def format_dify_report(response: AnalysisResponse) -> str:
    """Keep the Dify response readable without discarding the full API report."""
    if response.status != "completed" or not response.report:
        reason = _compact(response.error or "暂未生成可用报告，请检查数据和模型配置。", 80)
        return "# 直播运营分析\n\n分析未完成：" + reason

    report = response.report
    lines = [
        "# 直播运营分析",
        f"**风险等级：{RISK_LABELS.get(report.risk_level, report.risk_level)}**",
        f"**核心结论：** {_compact(report.summary, 90)}",
    ]

    metrics = _focus_evidence(report.evidence)
    if metrics:
        lines.extend(["", "## 核心指标"])
        for item in metrics:
            explanation = _compact(item.explanation, 28)
            suffix = f"（{explanation}）" if explanation else ""
            lines.append(f"- {item.metric}：{item.value}{suffix}")

    recommendations = sorted(
        report.recommendations,
        key=lambda item: PRIORITY_ORDER.get(item.priority, len(PRIORITY_ORDER)),
    )[:3]
    if recommendations:
        lines.extend(["", "## 优先动作"])
        for index, item in enumerate(recommendations, start=1):
            lines.append(f"{index}. {_compact(item.action, 55)}")

    return "\n".join(lines)
