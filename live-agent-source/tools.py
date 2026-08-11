"""真实分析工具及其注册表。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from analyzer import analyze
from thresholds import evaluate_thresholds, load_threshold_config


def _get(mapping: dict, *names: str, default: Any = None) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _base_analysis(result: dict) -> dict:
    return {
        "data_source": _get(result, "数据来源", "鏁版嵁鏉ユ簮"),
        "data_size": _get(result, "数据规模", "鏁版嵁瑙勬ā", default={}),
        "data_quality": _get(result, "数据质量", "鏁版嵁璐ㄩ噺", default={}),
    }


def funnel_analysis(file_path: str, threshold_config_path: Optional[str] = None) -> dict:
    """计算核心漏斗并返回确定性的阈值判断。"""
    result = analyze(file_path)
    config = load_threshold_config(threshold_config_path)
    payload = _base_analysis(result)
    payload.update({
        "funnel": _get(result, "核心漏斗", "鏍稿績婕忔枟", default={}),
        "thresholds": evaluate_thresholds(result, config),
    })
    return payload


def inviter_analysis(
    file_path: str,
    inviter_name: Optional[str] = None,
    top_n: int = 10,
) -> dict:
    """按邀请人返回表现排行或指定邀请人的钻取结果。"""
    result = analyze(file_path)
    items = _get(result, "分邀请人", "鍒嗛個璇蜂汉", default=[]) or []
    if inviter_name:
        items = [
            item for item in items
            if str(_get(item, "邀请人", "閭€璇蜂汉", default="")) == inviter_name
        ]
    limit = max(1, min(int(top_n), 50))
    payload = _base_analysis(result)
    payload.update({
        "dimension": "inviter",
        "filter": inviter_name,
        "items": items[:limit],
    })
    return payload


def channel_analysis(
    file_path: str,
    channel_name: Optional[str] = None,
    top_n: int = 10,
) -> dict:
    """按渠道返回表现排行或指定渠道的钻取结果。"""
    result = analyze(file_path)
    items = _get(result, "分渠道", "鍒嗘笭閬", default=[]) or []
    if channel_name:
        items = [
            item for item in items
            if str(_get(item, "渠道", "娓犻亾", default="")) == channel_name
        ]
    limit = max(1, min(int(top_n), 50))
    payload = _base_analysis(result)
    payload.update({
        "dimension": "channel",
        "filter": channel_name,
        "items": items[:limit],
    })
    return payload


def explore_data(file_path: str) -> dict:
    """返回输入数据的规模、质量和可用分析维度。"""
    result = analyze(file_path)
    return {
        **_base_analysis(result),
        "available_dimensions": {
            "inviter": bool(_get(result, "分邀请人", "鍒嗛個璇蜂汉", default=[])),
            "channel": bool(_get(result, "分渠道", "鍒嗘笭閬", default=[])),
            "session": bool(_get(result, "分场次", "鍒嗗満娆", default=[])),
        },
    }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., dict]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """集中管理工具定义、Schema 和执行函数。"""

    def __init__(self, specs: Optional[list[ToolSpec]] = None):
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._specs[spec.name] = spec

    def schemas(self) -> list[dict]:
        return [spec.schema() for spec in self._specs.values()]

    def names(self) -> list[str]:
        return list(self._specs)

    def execute(self, name: str, arguments: dict[str, Any]) -> dict:
        if name not in self._specs:
            raise ValueError(f"unknown tool: {name}")
        return self._specs[name].handler(**arguments)


FILE_PATH = {
    "type": "string",
    "description": "本地 CSV 或 Excel 文件路径",
}
TOP_N = {
    "type": "integer",
    "minimum": 1,
    "maximum": 50,
    "default": 10,
}


def build_tool_registry() -> ToolRegistry:
    return ToolRegistry([
        ToolSpec(
            name="funnel_analysis",
            description="计算到课、完课、商品访问、领券、支付和购买等核心漏斗指标，并返回程序化阈值判断。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": FILE_PATH,
                    "threshold_config_path": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["file_path"],
            },
            handler=funnel_analysis,
        ),
        ToolSpec(
            name="inviter_analysis",
            description="按邀请人统计预约量、到课率、完课率、访问率和购买率，可筛选指定邀请人。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": FILE_PATH,
                    "inviter_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "top_n": TOP_N,
                },
                "required": ["file_path"],
            },
            handler=inviter_analysis,
        ),
        ToolSpec(
            name="channel_analysis",
            description="按渠道统计人数、到课率、完课率和购买率，可筛选指定渠道。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": FILE_PATH,
                    "channel_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "top_n": TOP_N,
                },
                "required": ["file_path"],
            },
            handler=channel_analysis,
        ),
    ])


TOOL_REGISTRY = build_tool_registry()
TOOL_FUNCTIONS = {name: TOOL_REGISTRY._specs[name].handler for name in TOOL_REGISTRY.names()}
TOOL_SCHEMAS = TOOL_REGISTRY.schemas()


def execute_tool(name: str, arguments: dict[str, Any]) -> dict:
    return TOOL_REGISTRY.execute(name, arguments)


def tool_result_text(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
