import tempfile
import unittest
from pathlib import Path

import pandas as pd

from agent import LiveStreamAgent


class FakeLLM:
    model = "test-model"

    def __init__(self):
        self.last_user_prompt = ""

    def chat(self, system_prompt, user_prompt, temperature, max_tokens):
        self.last_user_prompt = user_prompt
        return "测试报告"


class AgentTests(unittest.TestCase):
    def test_anomaly_report_contains_program_judgement(self):
        frame = pd.DataFrame({
            "是否到课": ["是"] * 19 + ["否"],
            "是否完课": ["否"] * 20,
            "直播观看时长": ["00:20:00"] * 20,
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.csv"
            output_path = root / "output"
            frame.to_csv(input_path, index=False, encoding="utf-8-sig")

            agent = LiveStreamAgent(api_key="test-key")
            fake_llm = FakeLLM()
            agent.llm = fake_llm
            result = agent.run(str(input_path), mode="anomaly", output_dir=str(output_path))
            report = Path(result["anomaly"]["path"]).read_text(encoding="utf-8")

        self.assertIn("程序阈值判定", report)
        self.assertIn("严重", report)
        self.assertIn("阈值判定", fake_llm.last_user_prompt)


if __name__ == "__main__":
    unittest.main()
