"""
Tests for passive cleaning quality control.

These tests use temporary folders. They do not touch the real shared_data
corpus or quality report folders.
"""

import json
import tempfile
import unittest
from pathlib import Path

from collector.quality import cleaning_quality


class CleaningQualityTests(unittest.TestCase):
    def write_raw_article(self, raw_dir, article_id, source, text):
        raw_article = {
            "id": article_id,
            "source": source,
            "link": f"https://example.com/{article_id}",
            "published": "Fri, 10 Apr 2026 09:44:51 GMT",
            "scraped_at": "2026-04-10T10:00:00+00:00",
            "metadata": {
                "source": source,
                "link": f"https://example.com/{article_id}",
                "title": "Raw Title",
                "tags": [],
            },
            "text": text,
        }
        raw_path = raw_dir / f"{article_id}.json"
        raw_path.write_text(json.dumps(raw_article), encoding="utf-8")
        return raw_path

    def write_clean_article(self, clean_dir, article_id, source, text):
        clean_article = {
            "id": article_id,
            "source": source,
            "link": f"https://example.com/{article_id}",
            "title": "Clean Title",
            "text": text,
            "metadata": {"source": source},
            "cleaned_at": "2026-05-08T23:19:01+00:00",
            "is_valid_article": True,
        }
        clean_path = clean_dir / f"{article_id}.json"
        clean_path.write_text(json.dumps(clean_article), encoding="utf-8")
        return clean_path

    def test_text_has_html_tags_detects_obvious_html(self):
        result = cleaning_quality.text_has_html_tags("<div>Article body</div>")

        self.assertTrue(result)

    def test_parse_timestamp_to_epoch_handles_rss_and_iso_dates(self):
        rss_epoch = cleaning_quality.parse_timestamp_to_epoch(
            "Fri, 10 Apr 2026 09:44:51 GMT"
        )
        iso_epoch = cleaning_quality.parse_timestamp_to_epoch("2026-05-08T23:19:01+00:00")

        self.assertGreater(rss_epoch, 0)
        self.assertGreater(iso_epoch, rss_epoch)

    def test_check_clean_article_flags_short_html_and_boilerplate(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_path = base_dir / "article-one.json"
            clean_path = base_dir / "article-one.json"
            raw_article = {
                "id": "article-one",
                "source": "PUBLICO",
                "link": "https://example.com/article-one",
                "metadata": {"title": "Raw Title"},
                "text": "This is the raw article body. " * 20,
            }
            clean_article = {
                "id": "article-one",
                "source": "PUBLICO",
                "link": "https://example.com/article-one",
                "title": "",
                "text": "<p>Accept cookies</p>",
                "is_valid_article": True,
            }

            result = cleaning_quality.check_clean_article(
                raw_article,
                clean_article,
                raw_path,
                clean_path,
                minimum_text_characters=50,
            )

        self.assertIn("missing_title", result["issues"])
        self.assertIn("short_clean_text", result["issues"])
        self.assertIn("contains_html_tags", result["issues"])
        self.assertIn("contains_boilerplate", result["issues"])
        self.assertEqual(result["title"], "Raw Title")
        self.assertEqual(result["link"], "https://example.com/article-one")
        self.assertEqual(result["severity"], "warning")
        self.assertEqual(result["recommended_action"], "inspect_source_cleaner")
        self.assertEqual(result["boilerplate_phrase_count"], 1)
        self.assertGreater(result["html_tag_count"], 0)
        self.assertIn("raw_excerpt", result)
        self.assertIn("clean_excerpt", result)
        self.assertFalse(result["passed_deterministic_checks"])

    def test_build_article_quality_results_detects_missing_clean_file(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_raw_article(raw_dir, "article-one", "PUBLICO", "Raw body")

            article_results, source_stats, counts = cleaning_quality.build_article_quality_results(
                [{"name": "PUBLICO"}],
                raw_dir=raw_dir,
                clean_dir=clean_dir,
                include_unlisted_sources=False,
            )

        self.assertEqual(len(article_results), 1)
        self.assertIn("missing_clean_file", article_results[0]["issues"])
        self.assertEqual(counts["missing_clean_files"], 1)
        self.assertEqual(source_stats["PUBLICO"]["missing_clean_articles"], 1)

    def test_duplicate_clean_text_is_flagged(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            clean_dir.mkdir()
            duplicate_text = "This cleaned text is repeated across two articles. " * 10
            self.write_raw_article(raw_dir, "article-one", "PUBLICO", "Raw body one " * 30)
            self.write_raw_article(raw_dir, "article-two", "PUBLICO", "Raw body two " * 30)
            self.write_clean_article(clean_dir, "article-one", "PUBLICO", duplicate_text)
            self.write_clean_article(clean_dir, "article-two", "PUBLICO", duplicate_text)

            article_results, source_stats, counts = cleaning_quality.build_article_quality_results(
                [{"name": "PUBLICO"}],
                raw_dir=raw_dir,
                clean_dir=clean_dir,
                include_unlisted_sources=False,
            )

        self.assertEqual(len(article_results), 2)
        self.assertEqual(counts["clean_files_seen"], 2)
        self.assertEqual(source_stats["PUBLICO"]["articles_with_issues"], 2)

        for result in article_results:
            self.assertIn("duplicate_clean_text", result["issues"])
            self.assertEqual(result["duplicate_group_size"], 2)
            self.assertEqual(result["recommended_action"], "inspect_duplicate")

    def test_choose_llm_judge_sample_limits_each_source(self):
        article_results = [
            {
                "article_id": "p1",
                "source": "PUBLICO",
                "sample_priority": 3,
                "issue_count": 2,
                "raw_characters": 100,
            },
            {
                "article_id": "p2",
                "source": "PUBLICO",
                "sample_priority": 1,
                "issue_count": 0,
                "raw_characters": 100,
            },
            {
                "article_id": "b1",
                "source": "BBC",
                "sample_priority": 2,
                "issue_count": 1,
                "raw_characters": 100,
            },
            {
                "article_id": "b2",
                "source": "BBC",
                "sample_priority": 0,
                "issue_count": 0,
                "raw_characters": 100,
            },
        ]

        sample = cleaning_quality.choose_llm_judge_sample(
            article_results,
            sample_per_source=1,
            sample_mode="suspicious",
            random_seed=42,
        )
        sampled_ids = []

        for result in sample:
            sampled_ids.append(result["article_id"])

        self.assertEqual(sampled_ids, ["b1", "p1"])

    def test_quality_cleaning_writes_report_files(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            output_dir = base_dir / "report"
            raw_dir.mkdir()
            clean_dir.mkdir()
            raw_text = "This is a full raw article body for quality control. " * 20
            clean_text = "This is a clean article body for quality control. " * 20
            self.write_raw_article(raw_dir, "article-one", "PUBLICO", raw_text)
            self.write_clean_article(clean_dir, "article-one", "PUBLICO", clean_text)

            exit_code = cleaning_quality.quality_cleaning(
                [{"name": "PUBLICO"}],
                raw_dir=raw_dir,
                clean_dir=clean_dir,
                output_dir=output_dir,
                include_unlisted_sources=False,
                sample_per_source=1,
                sample_mode="suspicious",
                minimum_text_characters=50,
            )

            summary_path = output_dir / "summary.json"
            checks_path = output_dir / "article_checks.jsonl"
            judge_path = output_dir / "llm_judge_queue.jsonl"
            report_path = output_dir / "report.md"
            html_path = output_dir / "report.html"
            checks_exists = checks_path.exists()
            report_exists = report_path.exists()
            html_exists = html_path.exists()
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            check_lines = checks_path.read_text(encoding="utf-8").strip().splitlines()
            judge_lines = judge_path.read_text(encoding="utf-8").strip().splitlines()
            first_check = json.loads(check_lines[0])
            first_judge = json.loads(judge_lines[0])
            html_text = html_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertTrue(checks_exists)
        self.assertTrue(report_exists)
        self.assertTrue(html_exists)
        self.assertEqual(summary["totals"]["checked_articles"], 1)
        self.assertEqual(summary["totals"]["sampled_for_llm_judge"], 1)
        self.assertEqual(summary["totals"]["rates"]["clean_coverage_rate"], 1)
        self.assertEqual(summary["sources"]["PUBLICO"]["clean_coverage_rate"], 1)
        self.assertEqual(len(judge_lines), 1)
        self.assertEqual(first_check["title"], "Clean Title")
        self.assertEqual(first_check["cleaner"], "")
        self.assertEqual(first_check["is_llm_judge_sample"], True)
        self.assertIn("clean_word_count", first_check)
        self.assertIn("quality_checked_at", first_check)
        self.assertGreater(first_check["published_at_epoch"], 0)
        self.assertGreater(first_check["latest_known_at_epoch"], 0)
        self.assertEqual(first_judge["title"], "Clean Title")
        self.assertEqual(first_judge["recommended_action"], "none")
        self.assertIn("News Cleaning Quality Report", html_text)
        self.assertIn("sourceFilter", html_text)
        self.assertIn("severityFilter", html_text)
        self.assertIn("<th>Collected</th>", html_text)
        self.assertIn("<th>Cleaned</th>", html_text)
        self.assertIn("2026-04-10 10:00 UTC", html_text)
        self.assertIn("2026-05-08 23:19 UTC", html_text)
        self.assertIn("sortFieldFilter", html_text)
        self.assertIn("sortDirectionFilter", html_text)
        self.assertIn("Published timestamp", html_text)
        self.assertIn("Ascending", html_text)
        self.assertIn("open in Sublime", html_text)
        self.assertIn("subl://open?url=", html_text)
        self.assertIn("copy path", html_text)
        self.assertIn("file://", html_text)
        self.assertIn("Clean Coverage", html_text)
        self.assertIn("article-one", html_text)


if __name__ == "__main__":
    unittest.main()
