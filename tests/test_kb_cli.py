"""
Tests for the knowledge-base command-line parser.
"""

import unittest

from knowledge_bases.cli import parse_run_arguments
from knowledge_bases.cli import parse_evaluate_arguments
from knowledge_bases.cli import parse_precompute_entities_arguments
from knowledge_bases.cli import parse_search_arguments


class KnowledgeBaseCliTests(unittest.TestCase):
    def test_run_arguments_default_to_adaptive_embedding_settings(self):
        result = parse_run_arguments(["all"])

        self.assertEqual(result["recipe_arguments"], ["all"])
        self.assertEqual(result["workers"], 2)
        self.assertEqual(result["embedding_batch_size"], 50)
        self.assertEqual(result["embedding_max_batch_tokens"], 100000)
        self.assertEqual(result["embedding_request_delay_seconds"], 0.0)
        self.assertIsNone(result["sample_articles"])
        self.assertNotIn("published_before", result)
        self.assertNotIn("indexed_before", result)

    def test_run_arguments_parse_embedding_rate_limit_options(self):
        result = parse_run_arguments(
            [
                "news_no_chunking_3small",
                "--workers",
                "2",
                "--embedding-batch-size",
                "10",
                "--embedding-max-batch-tokens",
                "25000",
                "--embedding-request-delay-seconds",
                "2.5",
                "--embedding-max-retries",
                "12",
                "--sample-articles",
                "100",
                "--random-seed",
                "9",
            ]
        )

        self.assertEqual(result["workers"], 2)
        self.assertEqual(result["embedding_batch_size"], 10)
        self.assertEqual(result["embedding_max_batch_tokens"], 25000)
        self.assertEqual(result["embedding_request_delay_seconds"], 2.5)
        self.assertEqual(result["embedding_max_retries"], 12)
        self.assertEqual(result["sample_articles"], 100)
        self.assertEqual(result["random_seed"], 9)

    def test_run_arguments_reject_removed_timestamp_options(self):
        with self.assertRaises(ValueError):
            parse_run_arguments(
                [
                    "news_no_chunking_3small",
                    "--published-before",
                    "2026-05-01T00:00:00+00:00",
                ]
            )

        with self.assertRaises(ValueError):
            parse_run_arguments(
                [
                    "news_no_chunking_3small",
                    "--indexed-before",
                    "2026-05-01T00:00:00+00:00",
                ]
            )

    def test_search_arguments_accept_indexed_before(self):
        result = parse_search_arguments(
            [
                "news_no_chunking_3small",
                "hotel demand in Lisbon",
                "--indexed-before",
                "20260501_000000",
            ]
        )

        self.assertEqual(result["recipe_name"], "news_no_chunking_3small")
        self.assertEqual(result["query_text"], "hotel demand in Lisbon")
        self.assertEqual(result["search_mode"], "ann")
        self.assertEqual(result["indexed_before"], "20260501_000000")

    def test_evaluate_arguments_default_to_retrieval_metrics(self):
        result = parse_evaluate_arguments(
            [
                "all",
                "--output",
                "shared_data/knowledge_bases/evaluation_metrics.json",
            ]
        )

        self.assertEqual(result["recipe_arguments"], ["all"])
        self.assertEqual(
            result["output_path"],
            "shared_data/knowledge_bases/evaluation_metrics.json",
        )
        self.assertFalse(result["write_tables"])
        self.assertIsNone(result["markdown_table_path"])
        self.assertIsNone(result["csv_table_path"])
        self.assertTrue(result["retrieval_metrics"])
        self.assertEqual(result["retrieval_sample_size"], 100)
        self.assertEqual(result["retrieval_top_k"], 10)
        self.assertEqual(result["retrieval_search_mode"], "ann")
        self.assertEqual(result["entity_sample_size"], 100)
        self.assertEqual(result["entity_device"], "auto")
        self.assertEqual(result["entity_window_batch_size"], 8)

    def test_evaluate_arguments_accept_table_options(self):
        result = parse_evaluate_arguments(
            [
                "all",
                "--table",
                "--markdown-table",
                "shared_data/knowledge_bases/kb_metrics_table.md",
                "--csv-table",
                "shared_data/knowledge_bases/kb_metrics_table.csv",
            ]
        )

        self.assertEqual(result["recipe_arguments"], ["all"])
        self.assertTrue(result["write_tables"])
        self.assertEqual(
            result["markdown_table_path"],
            "shared_data/knowledge_bases/kb_metrics_table.md",
        )
        self.assertEqual(
            result["csv_table_path"],
            "shared_data/knowledge_bases/kb_metrics_table.csv",
        )

    def test_evaluate_arguments_accept_retrieval_tuning_options(self):
        result = parse_evaluate_arguments(
            [
                "news_no_chunking_3small",
                "--retrieval-sample-size",
                "25",
                "--retrieval-top-k",
                "5",
                "--retrieval-search-mode",
                "ann",
                "--entity-sample-size",
                "25",
                "--entity-device",
                "cpu",
                "--entity-window-batch-size",
                "1",
            ]
        )

        self.assertEqual(result["recipe_arguments"], ["news_no_chunking_3small"])
        self.assertTrue(result["retrieval_metrics"])
        self.assertEqual(result["retrieval_sample_size"], 25)
        self.assertEqual(result["retrieval_top_k"], 5)
        self.assertEqual(result["retrieval_search_mode"], "ann")
        self.assertEqual(result["entity_sample_size"], 25)
        self.assertEqual(result["entity_device"], "cpu")
        self.assertEqual(result["entity_window_batch_size"], 1)

    def test_evaluate_arguments_reject_invalid_retrieval_search_mode(self):
        with self.assertRaisesRegex(ValueError, "--retrieval-search-mode"):
            parse_evaluate_arguments(
                [
                    "all",
                    "--retrieval-search-mode",
                    "bad",
                ]
            )

    def test_evaluate_arguments_reject_invalid_entity_sample_size(self):
        with self.assertRaisesRegex(ValueError, "--entity-sample-size"):
            parse_evaluate_arguments(
                [
                    "all",
                    "--entity-sample-size",
                    "0",
                ]
            )

        with self.assertRaisesRegex(ValueError, "--entity-sample-size"):
            parse_evaluate_arguments(
                [
                    "all",
                    "--entity-sample-size",
                ]
            )

    def test_evaluate_arguments_reject_invalid_entity_device_and_window_batch_size(self):
        with self.assertRaisesRegex(ValueError, "--entity-device"):
            parse_evaluate_arguments(["all", "--entity-device", "gpu"])

        with self.assertRaisesRegex(ValueError, "--entity-window-batch-size"):
            parse_evaluate_arguments(["all", "--entity-window-batch-size", "0"])

        with self.assertRaisesRegex(ValueError, "--entity-window-batch-size"):
            parse_evaluate_arguments(["all", "--entity-window-batch-size"])

    def test_precompute_entities_arguments_default_to_mps_auto_config(self):
        result = parse_precompute_entities_arguments(["all"])

        self.assertEqual(result["recipe_arguments"], ["all"])
        self.assertEqual(result["device"], "auto")
        self.assertEqual(result["batch_size"], 8)
        self.assertIsNone(result["limit"])
        self.assertFalse(result["overwrite_existing"])

    def test_precompute_entities_arguments_accept_tuning_options(self):
        result = parse_precompute_entities_arguments(
            [
                "news_fixed_2000_overlap_3small",
                "--device",
                "cpu",
                "--batch-size",
                "4",
                "--limit",
                "100",
                "--overwrite-existing",
            ]
        )

        self.assertEqual(result["recipe_arguments"], ["news_fixed_2000_overlap_3small"])
        self.assertEqual(result["device"], "cpu")
        self.assertEqual(result["batch_size"], 4)
        self.assertEqual(result["limit"], 100)
        self.assertTrue(result["overwrite_existing"])

    def test_precompute_entities_arguments_reject_bad_values(self):
        with self.assertRaisesRegex(ValueError, "--device"):
            parse_precompute_entities_arguments(["all", "--device", "gpu"])

        with self.assertRaisesRegex(ValueError, "--batch-size"):
            parse_precompute_entities_arguments(["all", "--batch-size", "0"])

        with self.assertRaisesRegex(ValueError, "--limit"):
            parse_precompute_entities_arguments(["all", "--limit", "0"])


if __name__ == "__main__":
    unittest.main()
