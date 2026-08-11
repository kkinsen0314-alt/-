import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from agent_loop import ToolCallingAgent
from llm_client import LLMResponse, ToolCall
from models import AnalysisRequest
from rag import LocalRAG
from tools import TOOL_REGISTRY, channel_analysis, funnel_analysis, inviter_analysis


class FakeLLM:
    def __init__(self):
        self.calls = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return LLMResponse(
                content=None,
                tool_calls=[ToolCall("call-1", "funnel_analysis", {"file_path": self.file_path})],
                finish_reason="tool_calls",
            )
        report = {
            "title": "测试报告",
            "risk_level": "attention",
            "summary": "工具循环完成",
            "key_findings": ["工具结果已注入"],
            "recommendations": [],
            "evidence": [],
        }
        return LLMResponse(json.dumps(report, ensure_ascii=False), finish_reason="stop")


class ToolAndAgentTests(unittest.TestCase):
    def _make_input(self, directory: str) -> Path:
        path = Path(directory) / "input.csv"
        pd.DataFrame({
            "是否到课": ["是", "否", "是"],
            "是否完课": ["是", "否", "否"],
            "邀请人": ["甲", "甲", "乙"],
            "线索渠道": ["视频号", "视频号", "社群"],
        }).to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def test_three_real_tools_and_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_input(directory)
            self.assertIn("funnel", funnel_analysis(str(path)))
            self.assertEqual(inviter_analysis(str(path), inviter_name="甲")["items"][0]["邀请人"], "甲")
            self.assertEqual(channel_analysis(str(path), channel_name="视频号")["items"][0]["渠道"], "视频号")
            self.assertEqual(set(TOOL_REGISTRY.names()), {"funnel_analysis", "inviter_analysis", "channel_analysis"})

    def test_multi_turn_agent_returns_pydantic_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_input(directory)
            fake_llm = FakeLLM()
            fake_llm.file_path = str(path)
            agent = ToolCallingAgent(llm=fake_llm, rag=LocalRAG(Path(directory) / "reports"))
            response = agent.run(
                AnalysisRequest(file_path=str(path), max_rounds=3, history_top_k=0),
                run_id="api-run-1",
            )
            self.assertEqual(response.status, "completed")
            self.assertEqual(response.run_id, "api-run-1")
            self.assertEqual(response.report.title, "测试报告")
            self.assertEqual(len(response.tool_calls), 1)
            self.assertEqual(len(fake_llm.calls), 2)


if __name__ == "__main__":
    unittest.main()
