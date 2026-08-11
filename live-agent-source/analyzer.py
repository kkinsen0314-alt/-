"""直播运营数据分析模块。"""

import json
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd


BOOLEAN_COLUMNS = [
    "是否到课", "是否连麦", "是否访问课程商品", "是否领取优惠券",
    "是否发起支付", "是否购买课程", "是否抽奖", "是否中奖",
    "是否观看回放", "是否完课", "是否访问直播卡片",
]
DURATION_COLUMNS = ["直播观看时长", "回放观看时长"]
REQUIRED_COLUMNS = ["是否到课", "是否完课"]


def _read_input(filepath: str) -> pd.DataFrame:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在: {path}")
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
        df = pd.read_excel(path)
    else:
        raise ValueError("仅支持 .csv、.xls、.xlsx 和 .xlsm 文件")
    if df.empty:
        raise ValueError("输入文件没有数据行")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"输入文件缺少必需列: {', '.join(missing)}")
    return df


def _normalize_bool(value):
    if pd.isna(value):
        return pd.NA
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"是", "yes", "y", "true", "1"}:
        return True
    if text in {"否", "no", "n", "false", "0"}:
        return False
    return pd.NA


def _time_to_seconds(value) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, pd.Timedelta):
        return max(0, int(value.total_seconds()))
    if isinstance(value, timedelta):
        return max(0, int(value.total_seconds()))
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second
    if isinstance(value, (int, float)):
        numeric = float(value)
        return max(0, int(numeric * 86400 if 0 <= numeric < 1 else numeric))

    text = str(value).strip()
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return max(0, int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2])))
        if len(parts) == 2:
            return max(0, int(parts[0]) * 60 + int(float(parts[1])))
        parsed = pd.to_timedelta(text, errors="coerce")
        if not pd.isna(parsed):
            return max(0, int(parsed.total_seconds()))
    except (TypeError, ValueError, OverflowError):
        pass
    return 0


def _count_true(series: pd.Series) -> int:
    return int(series.fillna(False).astype(bool).sum())


def load_data(filepath: str) -> pd.DataFrame:
    """加载并清洗直播邀课数据，同时保留数据质量提示。"""
    df = _read_input(filepath)
    quality = {
        "未知布尔值": {},
        "缺失值": {},
        "警告": [],
    }

    for col in BOOLEAN_COLUMNS:
        if col not in df.columns:
            continue
        raw = df[col]
        normalized = raw.map(_normalize_bool)
        unknown = raw.notna() & normalized.isna()
        if unknown.any():
            quality["未知布尔值"][col] = sorted({str(value) for value in raw[unknown].tolist()})[:10]
            quality["警告"].append(f"{col} 存在无法识别的取值")
        df[col] = normalized

    for col in DURATION_COLUMNS:
        if col in df.columns:
            df[f"{col}_秒"] = df[col].apply(_time_to_seconds)

    if "预约时间" in df.columns:
        df["预约日期"] = pd.to_datetime(df["预约时间"], errors="coerce")

    for col, count in df.isna().sum().items():
        if count:
            quality["缺失值"][col] = int(count)
    if quality["缺失值"]:
        quality["警告"].append("输入数据存在缺失值，报告中的部分指标可能受影响")
    df.attrs["数据质量"] = quality
    return df


def compute_funnel(df: pd.DataFrame) -> dict:
    """计算核心转化漏斗，当前比例以总预约人数为分母。"""
    total = len(df)
    if total == 0:
        return {"总人数": 0}

    metrics = {
        "总人数": total,
        "新用户数": int((df.get("是否新用户") == "新用户").sum()) if "是否新用户" in df.columns else 0,
    }
    funnel_steps = [
        ("到课", "到课率"),
        ("完课", "完课率"),
        ("访问课程商品", "访问率"),
        ("领取优惠券", "领券率"),
        ("发起支付", "支付发起率"),
        ("购买课程", "购买率"),
        ("观看回放", "回放率"),
    ]
    for step, rate_name in funnel_steps:
        col = f"是否{step}"
        if col in df.columns:
            count = _count_true(df[col])
            metrics[f"{step}人数"] = count
            metrics[rate_name] = f"{round(count / total * 100, 1)}%"

    if "直播观看时长_秒" in df.columns and "是否到课" in df.columns:
        attended = df[df["是否到课"] == True]
        if len(attended) > 0:
            metrics["平均观看时长_秒"] = round(attended["直播观看时长_秒"].mean(), 0)
            metrics["中位观看时长_秒"] = round(attended["直播观看时长_秒"].median(), 0)
    return metrics


def group_by_inviter(df: pd.DataFrame) -> list[dict]:
    """按邀请人分组统计。"""
    if "邀请人" not in df.columns:
        return []
    result = []
    for name, group in df.groupby("邀请人"):
        item = {"邀请人": name, "预约人数": len(group)}
        for col, label in [
            ("是否到课", "到课率"), ("是否完课", "完课率"),
            ("是否访问课程商品", "访问率"), ("是否购买课程", "购买率"),
        ]:
            if col in group.columns:
                item[label] = f"{round(_count_true(group[col]) / len(group) * 100, 1)}%"
        result.append(item)
    return sorted(result, key=lambda x: x["预约人数"], reverse=True)


def group_by_channel(df: pd.DataFrame) -> list[dict]:
    """按线索渠道分组统计。"""
    if "线索渠道" not in df.columns:
        return []
    result = []
    for name, group in df.groupby("线索渠道"):
        item = {"渠道": name, "人数": len(group)}
        for col, label in [
            ("是否到课", "到课率"), ("是否完课", "完课率"),
            ("是否购买课程", "购买率"),
        ]:
            if col in group.columns:
                item[label] = f"{round(_count_true(group[col]) / len(group) * 100, 1)}%"
        result.append(item)
    return sorted(result, key=lambda x: x["人数"], reverse=True)


def group_by_session(df: pd.DataFrame) -> list[dict]:
    """按直播场次分组统计。"""
    if "直播场次" not in df.columns:
        return []
    title_map = {}
    if "直播标题" in df.columns:
        title_map = df.groupby("直播场次")["直播标题"].first().to_dict()

    result = []
    for session, group in df.groupby("直播场次"):
        session_value = session.item() if hasattr(session, "item") else session
        item = {
            "场次": session_value,
            "标题": title_map.get(session, ""),
            "人数": len(group),
        }
        for col, label in [
            ("是否到课", "到课率"), ("是否完课", "完课率"),
            ("是否购买课程", "购买率"),
        ]:
            if col in group.columns:
                item[label] = f"{round(_count_true(group[col]) / len(group) * 100, 1)}%"
        result.append(item)
    return sorted(result, key=lambda x: str(x["场次"]))


def analyze(filepath: str) -> dict:
    """读取文件、完成统计并返回结构化结果。"""
    df = load_data(filepath)
    result = {
        "分析时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "数据来源": Path(filepath).name,
        "数据规模": {"总行数": len(df), "总列数": len(df.columns)},
        "数据质量": df.attrs.get("数据质量", {}),
        "核心漏斗": compute_funnel(df),
        "分邀请人": group_by_inviter(df),
        "分渠道": group_by_channel(df),
        "分场次": group_by_session(df),
    }
    return result


def to_markdown_summary(result: dict) -> str:
    """将分析结果转为 Markdown 摘要，供 LLM 消费。"""
    lines = [
        "## 数据分析摘要\n",
        f"- 分析时间：{result['分析时间']}",
        f"- 数据来源：{result['数据来源']}",
        f"- 数据规模：{result['数据规模']['总行数']} 条记录\n",
    ]
    quality = result.get("数据质量", {})
    for warning in quality.get("警告", []):
        lines.append(f"- 数据质量警告：{warning}")

    funnel = result.get("核心漏斗", {})
    lines.extend([
        "### 核心漏斗",
        f"- 总人数：{funnel.get('总人数', 0)}",
        f"- 到课率：{funnel.get('到课率', 'N/A')}",
        f"- 完课率：{funnel.get('完课率', 'N/A')}",
        f"- 访问商品率：{funnel.get('访问率', 'N/A')}",
        f"- 购买率：{funnel.get('购买率', 'N/A')}",
    ])
    if "平均观看时长_秒" in funnel:
        minutes = round(float(funnel["平均观看时长_秒"]) / 60, 1)
        lines.append(f"- 平均观看时长：{minutes} 分钟")
    if "中位观看时长_秒" in funnel:
        minutes = round(float(funnel["中位观看时长_秒"]) / 60, 1)
        lines.append(f"- 中位观看时长：{minutes} 分钟")

    inviters = result.get("分邀请人", [])
    if inviters:
        lines.append("### 邀请人表现 (Top 3)")
        for item in inviters[:3]:
            lines.append(
                f"- {item['邀请人']}：预约 {item['预约人数']} 人，"
                f"到课率 {item.get('到课率', 'N/A')}，购买率 {item.get('购买率', 'N/A')}"
            )

    channels = result.get("分渠道", [])
    if channels:
        lines.append("\n### 渠道分布")
        for item in channels[:5]:
            lines.append(f"- {item['渠道']}：{item['人数']} 人，到课率 {item.get('到课率', 'N/A')}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python analyzer.py <Excel或CSV文件路径> [--json | --markdown]")
        sys.exit(1)
    result = analyze(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "--markdown":
        print(to_markdown_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
