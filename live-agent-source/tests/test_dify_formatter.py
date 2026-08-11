import unittest

from dify_formatter import format_dify_report
from models import AnalysisReport, AnalysisResponse, Evidence, Recommendation


class DifyFormatterTests(unittest.TestCase):
    def test_completed_report_is_compact_markdown(self):
        response = AnalysisResponse(
            run_id="internal-run-id",
            status="completed",
            report=AnalysisReport(
                title="测试报告",
                risk_level="attention",
                summary="到课表现正常，但完课、领券和购买环节存在明显流失。",
                evidence=[
                    Evidence(source="funnel_analysis", metric="到课率", value="85.1%", explanation="到课表现良好"),
                    Evidence(source="funnel_analysis", metric="完课率", value="32.1%", explanation="内容留存不足"),
                    Evidence(source="funnel_analysis", metric="领券率", value="0.0%", explanation="优惠激励缺失"),
                    Evidence(source="funnel_analysis", metric="购买率", value="1.5%", explanation="购买转化偏低"),
                ],
                recommendations=[
                    Recommendation(priority="medium", problem="", action="补全数据采集"),
                    Recommendation(priority="high", problem="", action="完课节点自动发放限时优惠券"),
                    Recommendation(priority="high", problem="", action="完课页增加商品入口并口播引导"),
                    Recommendation(priority="high", problem="", action="增加互动和答疑提升完课率"),
                ],
            ),
        )

        result = format_dify_report(response)

        self.assertIn("# 直播运营分析", result)
        self.assertIn("风险等级：关注", result)
        self.assertIn("完课率：32.1%", result)
        self.assertIn("领券率：0.0%", result)
        self.assertIn("购买率：1.5%", result)
        self.assertIn("完课节点自动发放限时优惠券", result)
        self.assertNotIn("internal-run-id", result)
        self.assertNotIn("补全数据采集", result)

    def test_failed_report_has_readable_error(self):
        result = format_dify_report(AnalysisResponse(run_id="run", status="failed", error="模型服务不可用"))

        self.assertEqual(result, "# 直播运营分析\n\n分析未完成：模型服务不可用")


if __name__ == "__main__":
    unittest.main()
