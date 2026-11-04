"""
Tests for static HTML report batch viewers.
"""

import json
import tempfile
import unittest
from pathlib import Path

from reporting.html_viewer import write_report_batch_viewer


class ReportingHtmlViewerTests(unittest.TestCase):
    def test_write_report_batch_viewer_renders_reports_and_manifest_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_folder = Path(tmp) / "reports" / "may13_context_check"
            run_folder.mkdir(parents=True)
            simple_report = run_folder / "simple.md"
            simple_manifest = run_folder / "simple_manifest.json"

            simple_report.write_text(
                "# Daily Report\n\n"
                "Tourism **demand** changed [Source 1](https://example.com/source).\n",
                encoding="utf-8",
            )
            simple_manifest.write_text(
                json.dumps({
                    "context_strategy": "simple",
                    "knowledge_base_recipe": "news_recursive_2000_overlap_3large",
                    "metrics": {
                        "citation_count": 3,
                        "cited_rag_article_count": 1,
                    },
                    "model_metrics": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "llm_calls": 2,
                    },
                    "candidate_selection": {
                        "method": "embedding_prototypes_v2",
                        "raw_count": 20,
                        "kept_count": 5,
                        "excluded_count": 15,
                    },
                    "retrieved_chunk_ids": ["chunk-1"],
                    "available_tools": ["search_knowledge_base"],
                    "required_tool_policy": {
                        "minimum_search_knowledge_base_calls": 1,
                    },
                    "tool_call_counts": {
                        "search_knowledge_base": 1,
                    },
                    "kb_search_call_count": 1,
                    "read_article_call_count": 0,
                    "kb_requirement_satisfied": True,
                    "tool_call_log": [
                        {
                            "strategy": "react-basic",
                            "phase": "final_report",
                            "iteration": 1,
                            "tool_name": "search_knowledge_base",
                            "arguments": {"query": "airport demand Portugal"},
                            "status": "ok",
                            "result_count": 1,
                            "retrieved_chunk_ids": ["chunk-1"],
                            "error": "",
                        }
                    ],
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
                    "started_at": "2026-05-17T20:26:58+00:00",
                    "finished_at": "2026-05-17T20:30:22+00:00",
                    "strategies": [
                        {
                            "strategy": "simple",
                            "status": "ok",
                            "report_path": str(simple_report),
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
            (run_folder / "evaluation.json").write_text(
                json.dumps({
                    "summary": {
                        "strategy_count": 2,
                        "error_count": 1,
                        "future_citation_count": 0,
                        "kb_requirement_failure_count": 0,
                    },
                    "strategies": [
                        {
                            "strategy": "simple",
                            "status": "ok",
                            "citation_count": 3,
                            "cited_past_article_count": 2,
                            "cited_future_article_count": 0,
                            "kb_requirement_satisfied": True,
                        }
                    ],
                    "metric_families": {
                        "temporal_validity": ["cited_future_article_count"],
                    },
                }),
                encoding="utf-8",
            )

            viewer_path = write_report_batch_viewer(run_folder)
            html_text = viewer_path.read_text(encoding="utf-8")

            self.assertEqual(viewer_path, run_folder / "index.html")
            self.assertIn("may13_context_check", html_text)
            self.assertIn("completed_with_errors", html_text)
            self.assertIn("<h1>Daily Report</h1>", html_text)
            self.assertIn("<strong>demand</strong>", html_text)
            self.assertIn("href=\"https://example.com/source\"", html_text)
            self.assertIn("embedding_prototypes_v2", html_text)
            self.assertIn("<h3>Tool Summary</h3>", html_text)
            self.assertIn("<th>kb_search_call_count</th>", html_text)
            self.assertIn("airport demand Portugal", html_text)
            self.assertIn("chunk-1", html_text)
            self.assertIn("KB unavailable", html_text)
            self.assertIn("Evaluation Summary", html_text)
            self.assertIn("future_citation_count", html_text)
            self.assertIn("<th>cited_past_article_count</th>", html_text)
            self.assertIn("<td>2</td>", html_text)
            self.assertIn("cited_future_article_count", html_text)
            self.assertIn("Full Manifest JSON", html_text)

    def test_write_report_batch_viewer_rejects_folder_without_run_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as error:
                write_report_batch_viewer(Path(tmp))

        self.assertIn("run_manifest.json", str(error.exception))
