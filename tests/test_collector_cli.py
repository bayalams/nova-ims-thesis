"""
Tests for the collector command-line interface.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from collector import cli


class CollectorCliTests(unittest.TestCase):
    def test_list_sources_prints_known_sources(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli.main(["list-sources"])

        self.assertEqual(exit_code, 0)
        self.assertIn("PUBLICO", output.getvalue())
        self.assertIn("enabled", output.getvalue())

    def test_status_prints_overall_summary(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli.main(["status"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Overall collector status", output.getvalue())
        self.assertIn("Source-by-source details", output.getvalue())

    def test_status_counts_link_raw_and_clean_files_per_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base_dir = Path(temporary_directory)
            links_dir = base_dir / "links"
            raw_articles_dir = base_dir / "raw"
            clean_articles_dir = base_dir / "clean"

            publico_links_dir = links_dir / "PUBLICO"
            bbc_links_dir = links_dir / "BBC"
            publico_links_dir.mkdir(parents=True)
            bbc_links_dir.mkdir(parents=True)
            (publico_links_dir / "snapshot.jsonl").write_text("{}\n", encoding="utf-8")
            (bbc_links_dir / "snapshot.jsonl").write_text("{}\n", encoding="utf-8")

            raw_articles_dir.mkdir()
            raw_article = {
                "id": "raw-publico",
                "source": "PUBLICO",
            }
            raw_articles_dir.joinpath("raw-publico.json").write_text(
                json.dumps(raw_article),
                encoding="utf-8",
            )

            clean_articles_dir.mkdir()
            clean_article = {
                "id": "clean-publico",
                "metadata": {
                    "source": "PUBLICO",
                },
            }
            clean_articles_dir.joinpath("clean-publico.json").write_text(
                json.dumps(clean_article),
                encoding="utf-8",
            )

            output = io.StringIO()

            with patch("collector.cli.STATUS_LINKS_DIR", links_dir, create=True):
                with patch("collector.cli.STATUS_RAW_ARTICLES_DIR", raw_articles_dir, create=True):
                    with patch("collector.cli.STATUS_CLEAN_ARTICLES_DIR", clean_articles_dir, create=True):
                        with redirect_stdout(output):
                            exit_code = cli.main(["status"])

        status_text = output.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("indexed link snapshots: 2", status_text)
        self.assertIn("raw articles: 1", status_text)
        self.assertIn("clean articles: 1", status_text)
        self.assertIn("PUBLICO: link_snapshots=1 raw_articles=1 clean_articles=1", status_text)

    def test_unknown_source_returns_error_code(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli.main(["index-rss", "not_a_source"])

        self.assertEqual(exit_code, 1)
        self.assertIn("[ERROR] Unknown source: not_a_source", output.getvalue())

    def test_index_rss_accepts_overwrite_flag(self):
        output = io.StringIO()

        with patch("collector.cli.index_links") as mocked_index:
            mocked_index.return_value = 0

            with redirect_stdout(output):
                exit_code = cli.main(["index-rss", "publico", "--overwrite-existing"])

        self.assertEqual(exit_code, 0)
        call_arguments = mocked_index.call_args
        self.assertTrue(call_arguments.kwargs["overwrite_existing"])

    def test_index_rss_parses_workers_and_max_age_days(self):
        output = io.StringIO()

        with patch("collector.cli.index_links") as mocked_index:
            mocked_index.return_value = 0

            with redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "index-rss",
                        "publico",
                        "--workers",
                        "3",
                        "--max-age-days",
                        "14",
                    ]
                )

        self.assertEqual(exit_code, 0)
        call_arguments = mocked_index.call_args
        self.assertEqual(call_arguments.kwargs["workers"], 3)
        self.assertEqual(call_arguments.kwargs["max_age_days"], 14)

    def test_index_rss_invalid_workers_stops_before_processing(self):
        output = io.StringIO()

        with patch("collector.cli.index_links") as mocked_index:
            with redirect_stdout(output):
                exit_code = cli.main(["index-rss", "publico", "--workers", "0"])

        self.assertEqual(exit_code, 1)
        self.assertIn("[ERROR] --workers must be a positive whole number.", output.getvalue())
        mocked_index.assert_not_called()

    def test_index_rss_missing_max_age_days_value_stops_before_processing(self):
        output = io.StringIO()

        with patch("collector.cli.index_links") as mocked_index:
            with redirect_stdout(output):
                exit_code = cli.main(["index-rss", "publico", "--max-age-days"])

        self.assertEqual(exit_code, 1)
        self.assertIn("[ERROR] --max-age-days needs a value.", output.getvalue())
        mocked_index.assert_not_called()

    def test_fetch_articles_parses_fetch_options(self):
        output = io.StringIO()

        with patch("collector.cli.fetch_articles") as mocked_fetch:
            mocked_fetch.return_value = 0

            with redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "fetch-articles",
                        "publico",
                        "--workers",
                        "3",
                        "--limit",
                        "10",
                        "--per-source",
                        "2",
                        "--no-filters",
                        "--overwrite-existing",
                    ]
                )

        self.assertEqual(exit_code, 0)
        call_arguments = mocked_fetch.call_args
        self.assertEqual(call_arguments.kwargs["workers"], 3)
        self.assertEqual(call_arguments.kwargs["limit"], 10)
        self.assertEqual(call_arguments.kwargs["per_source"], 2)
        self.assertEqual(call_arguments.kwargs["use_filters"], False)
        self.assertEqual(call_arguments.kwargs["overwrite_existing"], True)

    def test_retry_failed_articles_parses_options(self):
        output = io.StringIO()

        with patch("collector.cli.retry_failed_articles") as mocked_retry:
            mocked_retry.return_value = 0

            with redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "retry-failed-articles",
                        "publico",
                        "--workers",
                        "4",
                        "--limit",
                        "8",
                        "--per-source",
                        "1",
                    ]
                )

        self.assertEqual(exit_code, 0)
        call_arguments = mocked_retry.call_args
        self.assertEqual(call_arguments.kwargs["workers"], 4)
        self.assertEqual(call_arguments.kwargs["limit"], 8)
        self.assertEqual(call_arguments.kwargs["per_source"], 1)

    def test_clean_articles_parses_options(self):
        output = io.StringIO()

        with patch("collector.cli.clean_articles") as mocked_clean:
            mocked_clean.return_value = 0

            with redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "clean-articles",
                        "all",
                        "--workers",
                        "5",
                        "--limit",
                        "20",
                        "--per-source",
                        "3",
                        "--overwrite-existing",
                    ]
                )

        self.assertEqual(exit_code, 0)
        call_arguments = mocked_clean.call_args
        self.assertEqual(call_arguments.kwargs["workers"], 5)
        self.assertEqual(call_arguments.kwargs["limit"], 20)
        self.assertEqual(call_arguments.kwargs["per_source"], 3)
        self.assertEqual(call_arguments.kwargs["overwrite_existing"], True)
        self.assertEqual(call_arguments.kwargs["include_unlisted_sources"], True)

    def test_quality_cleaning_parses_options(self):
        output = io.StringIO()

        with patch("collector.cli.quality_cleaning") as mocked_quality:
            mocked_quality.return_value = 0

            with redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "quality-cleaning",
                        "all",
                        "--sample-per-source",
                        "7",
                        "--sample-mode",
                        "shortest",
                        "--seed",
                        "123",
                        "--minimum-text-characters",
                        "400",
                        "--output-dir",
                        "tmp-quality-report",
                    ]
                )

        self.assertEqual(exit_code, 0)
        call_arguments = mocked_quality.call_args
        self.assertEqual(call_arguments.kwargs["sample_per_source"], 7)
        self.assertEqual(call_arguments.kwargs["sample_mode"], "shortest")
        self.assertEqual(call_arguments.kwargs["random_seed"], 123)
        self.assertEqual(call_arguments.kwargs["minimum_text_characters"], 400)
        self.assertEqual(call_arguments.kwargs["output_dir"], "tmp-quality-report")
        self.assertEqual(call_arguments.kwargs["include_unlisted_sources"], True)

    def test_quality_cleaning_rejects_unknown_sample_mode(self):
        output = io.StringIO()

        with patch("collector.cli.quality_cleaning") as mocked_quality:
            with redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "quality-cleaning",
                        "publico",
                        "--sample-mode",
                        "middle",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("[ERROR] --sample-mode must be one of:", output.getvalue())
        mocked_quality.assert_not_called()


if __name__ == "__main__":
    unittest.main()
