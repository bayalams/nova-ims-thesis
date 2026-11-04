"""
Tests for report run evaluation artifacts.
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from reporting.evaluation import write_report_run_evaluation


class ReportingEvaluationTests(unittest.TestCase):
    def test_write_report_run_evaluation_creates_csv_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_folder = Path(tmp) / "may13_context_check"
            run_folder.mkdir()
            simple_manifest = run_folder / "simple_manifest.json"
            simple_manifest.write_text(
                json.dumps({
                    "context_strategy": "simple",
                    "knowledge_base_recipe": "news_recursive_2000_overlap_3large",
                    "metrics": {
                        "citation_count": 2,
                        "cited_future_article_count": 1,
                        "kb_search_call_count": 0,
                    },
                    "model_metrics": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                    },
                    "kb_requirement_satisfied": True,
                }),
                encoding="utf-8",
            )
            (run_folder / "run_manifest.json").write_text(
                json.dumps({
                    "recipe_name": "daily_tourism_intelligence",
                    "run_name": "may13_context_check",
                    "status": "completed_with_errors",
                    "report_datetime": "2026-05-13T23:59:59+00:00",
                    "knowledge_base_recipe": "news_recursive_2000_overlap_3large",
                    "strategies": [
                        {
                            "strategy": "simple",
                            "status": "ok",
                            "report_path": str(run_folder / "simple.md"),
                            "manifest_path": str(simple_manifest),
                            "error": "",
                        },
                        {
                            "strategy": "react-basic",
                            "status": "error",
                            "report_path": "",
                            "manifest_path": "",
                            "error": "KB unavailable",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            result = write_report_run_evaluation(run_folder)

            self.assertEqual(result["csv_path"], run_folder / "evaluation.csv")
            self.assertEqual(result["json_path"], run_folder / "evaluation.json")
            with (run_folder / "evaluation.csv").open(encoding="utf-8") as csv_file:
                csv_rows = list(csv.DictReader(csv_file))
            json_data = json.loads((run_folder / "evaluation.json").read_text(encoding="utf-8"))

            self.assertEqual(len(csv_rows), 2)
            self.assertEqual(csv_rows[0]["strategy"], "simple")
            self.assertEqual(csv_rows[0]["status"], "ok")
            self.assertEqual(csv_rows[0]["citation_count"], "2")
            self.assertEqual(csv_rows[0]["cited_future_article_count"], "1")
            self.assertEqual(csv_rows[1]["strategy"], "react-basic")
            self.assertEqual(csv_rows[1]["status"], "error")
            self.assertEqual(csv_rows[1]["error"], "KB unavailable")
            self.assertEqual(json_data["summary"]["strategy_count"], 2)
            self.assertEqual(json_data["summary"]["error_count"], 1)
            self.assertEqual(json_data["summary"]["future_citation_count"], 1)
            self.assertEqual(json_data["metric_families"]["temporal_validity"][0], "cited_future_article_count")
