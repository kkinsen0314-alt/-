import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from models import AnalysisReport, AnalysisResponse, Evidence, Recommendation
from rag import LocalRAG


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


class RagAndApiTests(unittest.TestCase):
    def test_local_rag_retrieves_historical_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "reports"
            report_dir.mkdir()
            (report_dir / "anomaly.md").write_text(
                "# 完课率异常\n完课率严重偏低，需要优化直播中段节奏。",
                encoding="utf-8",
            )
            hits = LocalRAG(report_dir).search("完课率异常", top_k=1)
            self.assertEqual(len(hits), 1)
            self.assertIn("完课率", hits[0]["snippet"])

    def test_project_knowledge_is_retrievable(self):
        knowledge_dir = Path(__file__).parents[1] / "knowledge"
        rag = LocalRAG(knowledge_dir)
        metric_hits = rag.search("完课率 领券率", top_k=3)
        threshold_hits = rag.search("预警线 严重线 阈值版本", top_k=1)
        self.assertTrue(any("metric_definitions" in hit["path"] for hit in metric_hits))
        self.assertEqual(Path(threshold_hits[0]["path"]).name, "threshold_guidance.md")

    @unittest.skipUnless(FASTAPI_AVAILABLE, "安装 requirements.txt 后运行 FastAPI 验证")
    def test_health_and_tool_schema_endpoints(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        self.assertEqual(client.get("/health").json(), {"status": "ok"})
        names = {item["function"]["name"] for item in client.get("/tools").json()["tools"]}
        self.assertEqual(names, {"funnel_analysis", "inviter_analysis", "channel_analysis"})

    def test_funnel_endpoint_accepts_upload_and_local_path(self):
        from fastapi.testclient import TestClient
        from api import app

        frame = pd.DataFrame({
            "是否到课": ["是", "否", "是"],
            "是否完课": ["否", "否", "是"],
            "邀请人": ["甲", "甲", "乙"],
            "线索渠道": ["视频号", "视频号", "社群"],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            client = TestClient(app)

            local_response = client.post("/v1/tools/funnel", data={"file_path": str(path)})
            self.assertEqual(local_response.status_code, 200)
            self.assertEqual(local_response.json()["tool"], "funnel_analysis")
            self.assertIn("funnel", local_response.json()["result"])

            with path.open("rb") as handle:
                upload_response = client.post(
                    "/v1/tools/funnel",
                    files={"file": (path.name, handle, "text/csv")},
                )
            self.assertEqual(upload_response.status_code, 200)
            self.assertEqual(upload_response.json()["result"]["data_size"]["总行数"], 3)


    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI is required for API verification")
    def test_dify_endpoint_returns_compact_text(self):
        from fastapi.testclient import TestClient
        from api import app

        result = AnalysisResponse(
            run_id="test-run",
            status="completed",
            report=AnalysisReport(
                title="Test report",
                risk_level="attention",
                summary="The conversion journey has material drop-off.",
                evidence=[
                    Evidence(source="funnel_analysis", metric="Completion rate", value="32.1%", explanation="Low retention"),
                    Evidence(source="funnel_analysis", metric="Coupon rate", value="0.0%", explanation="No incentive"),
                    Evidence(source="funnel_analysis", metric="Purchase rate", value="1.5%", explanation="Low conversion"),
                ],
                recommendations=[
                    Recommendation(priority="high", problem="", action="Send a coupon after completion"),
                ],
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_text("attendance\nyes\n", encoding="utf-8")
            with patch("api.ToolCallingAgent") as agent_class:
                agent_class.return_value.run.return_value = result
                with path.open("rb") as handle:
                    response = TestClient(app).post(
                        "/v1/dify/analyze",
                        files={"file": (path.name, handle, "text/csv")},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertIn("# ", response.text)
        self.assertNotIn('"run_id"', response.text)


if __name__ == "__main__":
    unittest.main()
