"""直播运营指标的确定性阈值判定。"""

import json
from pathlib import Path
from typing import Any, Optional, Union


ROOT = Path(__file__).parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "thresholds.json"
LEVEL_LABELS = {
    "normal": "正常",
    "attention": "关注",
    "critical": "严重",
    "insufficient_sample": "样本不足",
    "incomplete_data": "数据不完整",
    "missing": "缺失",
}


def load_threshold_config(config_path: Optional[Union[str, Path]] = None) -> dict:
    """加载并校验阈值配置。"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"阈值配置不存在: {path}")
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    if not isinstance(config.get("metrics"), dict) or not config["metrics"]:
        raise ValueError("阈值配置必须包含非空 metrics")
    for metric_id, rule in config["metrics"].items():
        for key in ("label", "source", "unit", "warning_below", "critical_below"):
            if key not in rule:
                raise ValueError(f"阈值配置 {metric_id} 缺少字段: {key}")
        if float(rule["critical_below"]) >= float(rule["warning_below"]):
            raise ValueError(f"阈值配置 {metric_id} 的严重线必须低于预警线")
    return config


def _to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value.endswith("%"):
            value = value[:-1]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_value(container: dict, rule: dict) -> Optional[float]:
    value = _to_number(container.get(rule["source"]))
    if value is None:
        return None
    if rule["unit"] == "minutes":
        value /= 60
    return round(value, 2)


def _classify(value: Optional[float], rule: dict) -> str:
    if value is None:
        return "missing"
    if value < float(rule["critical_below"]):
        return "critical"
    if value < float(rule["warning_below"]):
        return "attention"
    return "normal"


def _metric_result(metric_id: str, rule: dict, value: Optional[float], sample_size: int) -> dict:
    level = _classify(value, rule)
    return {
        "id": metric_id,
        "指标": rule["label"],
        "当前值": value,
        "单位": rule["unit"],
        "预警线": float(rule["warning_below"]),
        "严重线": float(rule["critical_below"]),
        "等级": level,
        "等级说明": LEVEL_LABELS[level],
        "样本数": sample_size,
    }


def evaluate_thresholds(analysis: dict, config: Optional[dict] = None) -> dict:
    """根据分析结果执行三级阈值判定，不依赖 LLM。"""
    config = config or load_threshold_config()
    funnel = analysis.get("核心漏斗", {})
    data_size = analysis.get("数据规模", {})
    sample_size = int(funnel.get("总人数", data_size.get("总行数", 0)) or 0)
    minimum_sample_size = int(config.get("minimum_sample_size", 20))
    minimum_inviter_sample_size = int(config.get("minimum_inviter_sample_size", 10))

    overall_results = []
    missing_metrics = []
    for metric_id, rule in config["metrics"].items():
        if metric_id == "inviter_attendance_rate":
            continue
        value = _metric_value(funnel, rule)
        result = _metric_result(metric_id, rule, value, sample_size)
        overall_results.append(result)
        if result["等级"] == "missing":
            missing_metrics.append(rule["label"])

    inviter_results = []
    skipped_inviters = []
    inviter_rule = config["metrics"].get("inviter_attendance_rate")
    if inviter_rule:
        for item in analysis.get("分邀请人", []):
            inviter_name = str(item.get("邀请人", "未命名"))
            inviter_sample = int(item.get("预约人数", 0) or 0)
            if inviter_sample < minimum_inviter_sample_size:
                skipped_inviters.append({"邀请人": inviter_name, "样本数": inviter_sample})
                continue
            result = _metric_result(
                "inviter_attendance_rate",
                inviter_rule,
                _metric_value(item, inviter_rule),
                inviter_sample,
            )
            result["邀请人"] = inviter_name
            inviter_results.append(result)

    all_results = overall_results + inviter_results
    levels = {result["等级"] for result in all_results}
    if "critical" in levels:
        raw_level = "critical"
    elif "attention" in levels:
        raw_level = "attention"
    elif "missing" in levels:
        raw_level = "incomplete_data"
    else:
        raw_level = "normal"

    if raw_level == "normal" and sample_size < minimum_sample_size:
        overall_level = "insufficient_sample"
    else:
        overall_level = raw_level

    return {
        "版本": config.get("version", "unknown"),
        "整体等级": overall_level,
        "整体等级说明": LEVEL_LABELS[overall_level],
        "原始等级": raw_level,
        "样本数": sample_size,
        "最小样本数": minimum_sample_size,
        "指标判定": overall_results,
        "邀请人判定": inviter_results,
        "跳过的小样本邀请人": skipped_inviters,
        "缺失指标": missing_metrics,
    }


def to_markdown_summary(result: dict) -> str:
    """将程序判定转换为可审计的 Markdown 摘要。"""
    lines = [
        f"- 整体等级：{result.get('整体等级说明', '未知')}",
        f"- 样本数：{result.get('样本数', 0)}（最小样本数：{result.get('最小样本数', 0)}）",
        f"- 阈值版本：{result.get('版本', 'unknown')}",
    ]
    for item in result.get("指标判定", []) + result.get("邀请人判定", []):
        value = item.get("当前值")
        if value is None:
            display_value = "缺失"
        elif item.get("单位") == "percent":
            display_value = f"{value}%"
        else:
            display_value = f"{value} 分钟"
        owner = f"（{item['邀请人']}）" if item.get("邀请人") else ""
        lines.append(
            f"- {item['指标']}{owner}：{display_value}，"
            f"{item['等级说明']}（预警线 {item['预警线']}，严重线 {item['严重线']}）"
        )
    if result.get("跳过的小样本邀请人"):
        names = ", ".join(item["邀请人"] for item in result["跳过的小样本邀请人"])
        lines.append(f"- 小样本邀请人未参与判定：{names}")
    return "\n".join(lines)
