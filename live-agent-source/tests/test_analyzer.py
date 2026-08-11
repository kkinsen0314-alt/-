import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analyzer import analyze, load_data


class AnalyzerTests(unittest.TestCase):
    def test_csv_normalization_and_duration(self):
        frame = pd.DataFrame({
            "是否到课": ["是", "否"],
            "是否完课": ["是", "否"],
            "直播观看时长": ["00:30:00", "00:00:45"],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            loaded = load_data(path)

        self.assertTrue(bool(loaded["是否到课"].iloc[0]))
        self.assertFalse(bool(loaded["是否到课"].iloc[1]))
        self.assertEqual(int(loaded["直播观看时长_秒"].iloc[0]), 1800)
        self.assertEqual(int(loaded["直播观看时长_秒"].iloc[1]), 45)

    def test_missing_required_column_fails_fast(self):
        frame = pd.DataFrame({"是否到课": ["是"]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            with self.assertRaises(ValueError):
                load_data(path)

    def test_analysis_contains_data_quality(self):
        frame = pd.DataFrame({
            "是否到课": ["是", "否"],
            "是否完课": ["是", "否"],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            result = analyze(path)

        self.assertIn("数据质量", result)
        self.assertEqual(result["核心漏斗"]["到课率"], "50.0%")


if __name__ == "__main__":
    unittest.main()
