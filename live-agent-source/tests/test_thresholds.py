import unittest

from thresholds import evaluate_thresholds, load_threshold_config


class ThresholdTests(unittest.TestCase):
    def setUp(self):
        self.config = load_threshold_config()

    def test_critical_metric_is_deterministic(self):
        analysis = {
            "数据规模": {"总行数": 50},
            "核心漏斗": {
                "总人数": 50,
                "到课率": "79.1%",
                "完课率": "8.3%",
                "平均观看时长_秒": 900,
            },
            "分邀请人": [{"邀请人": "周舟", "预约人数": 12, "到课率": "59%"}],
        }
        result = evaluate_thresholds(analysis, self.config)

        self.assertEqual(result["整体等级"], "critical")
        self.assertEqual(result["原始等级"], "critical")
        levels = {item["指标"]: item["等级"] for item in result["指标判定"]}
        self.assertEqual(levels["到课率"], "attention")
        self.assertEqual(levels["完课率"], "critical")
        self.assertEqual(result["邀请人判定"][0]["等级"], "critical")

    def test_small_sample_is_not_marked_normal(self):
        analysis = {
            "数据规模": {"总行数": 8},
            "核心漏斗": {
                "总人数": 8,
                "到课率": "100%",
                "完课率": "100%",
                "平均观看时长_秒": 3600,
            },
        }
        result = evaluate_thresholds(analysis, self.config)

        self.assertEqual(result["原始等级"], "normal")
        self.assertEqual(result["整体等级"], "insufficient_sample")


if __name__ == "__main__":
    unittest.main()
