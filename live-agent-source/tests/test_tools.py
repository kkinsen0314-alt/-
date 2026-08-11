import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tools import TOOL_REGISTRY, execute_tool


class ToolTests(unittest.TestCase):
    def test_three_tool_schemas_are_registered(self):
        self.assertEqual(
            TOOL_REGISTRY.names(),
            ["funnel_analysis", "inviter_analysis", "channel_analysis"],
        )

    def test_tools_return_real_analysis_data(self):
        frame = pd.DataFrame({
            "是否到课": ["是", "否", "是"],
            "是否完课": ["否", "否", "是"],
            "直播观看时长": ["00:20:00", "00:05:00", "00:30:00"],
            "邀请人": ["A", "A", "B"],
            "线索渠道": ["视频号", "视频号", "社群"],
            "直播场次": [1, 1, 1],
            "直播标题": ["测试场", "测试场", "测试场"],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            funnel = execute_tool("funnel_analysis", {"file_path": str(path)})
            inviter = execute_tool("inviter_analysis", {
                "file_path": str(path), "inviter_name": None, "top_n": 2,
            })
            channel = execute_tool("channel_analysis", {
                "file_path": str(path), "channel_name": None, "top_n": 2,
            })

        self.assertEqual(funnel["funnel"]["到课率"], "66.7%")
        self.assertEqual(inviter["dimension"], "inviter")
        self.assertEqual(channel["dimension"], "channel")


if __name__ == "__main__":
    unittest.main()
