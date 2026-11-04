"""
Tests for article cleaning.

These tests use temporary raw and clean folders. They do not touch the real
shared_data corpus.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collector.cleaning import clean_articles


class CleanArticlesTests(unittest.TestCase):
    def write_raw_article(self, raw_dir, article_id, source, extra_fields):
        raw_data = {
            "id": article_id,
            "link": f"https://example.com/{article_id}",
            "source": source,
            "metadata": {
                "source": source,
                "link": f"https://example.com/{article_id}",
                "title": "Example Title",
                "tags": [],
            },
        }
        raw_data.update(extra_fields)
        raw_path = raw_dir / f"{article_id}.json"
        raw_path.write_text(json.dumps(raw_data), encoding="utf-8")
        return raw_path

    def test_get_clean_output_path_uses_clean_folder(self):
        output_path = clean_articles.get_clean_output_path("abc123")

        self.assertEqual(
            output_path,
            Path("shared_data/corpus/news/clean/articles/abc123.json"),
        )

    def test_extract_text_prefers_legacy_text(self):
        raw_article = {
            "text": "Already cleaned text",
            "scrapingbee": {"content": "Raw scrapingbee content"},
        }

        text, source_kind = clean_articles.extract_text_for_cleaning(raw_article)

        self.assertEqual(text, "Already cleaned text")
        self.assertEqual(source_kind, "legacy_text")

    def test_extract_text_uses_scrapingbee_content_without_legacy_text(self):
        raw_article = {
            "scrapingbee": {"content": "Raw scrapingbee content"},
        }

        text, source_kind = clean_articles.extract_text_for_cleaning(raw_article)

        self.assertEqual(text, "Raw scrapingbee content")
        self.assertEqual(source_kind, "scrapingbee_content")

    def test_make_clean_metadata_normalizes_rss_tag_dictionaries(self):
        raw_article = {
            "id": "article-with-rss-tags",
            "link": "https://example.com/article-with-rss-tags",
            "source": "GUARDIAN_GENERAL",
            "metadata": {
                "title": "Example Title",
                "tags": [
                    {"term": "Health", "scheme": "https://example.com/health", "label": None},
                    {"term": "Travel", "scheme": None, "label": None},
                    {"term": "Health", "scheme": None, "label": None},
                ],
            },
        }

        metadata = clean_articles.make_clean_metadata(raw_article)

        self.assertEqual(metadata["tags"], ["Health", "Travel"])

    def test_clean_one_article_passes_string_tags_to_dispatcher(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            raw_path = self.write_raw_article(
                raw_dir,
                "article-with-dict-tags",
                "GUARDIAN_GENERAL",
                {
                    "scrapingbee": {"success": True, "content": "Raw body"},
                    "metadata": {
                        "source": "GUARDIAN_GENERAL",
                        "link": "https://example.com/article-with-dict-tags",
                        "title": "Example Title",
                        "tags": [
                            {"term": "Culture", "scheme": "https://example.com/culture"},
                            {"term": "Music", "scheme": "https://example.com/music"},
                        ],
                    },
                },
            )
            item = {
                "raw_path": raw_path,
                "article_id": "article-with-dict-tags",
                "source": "GUARDIAN_GENERAL",
            }

            with patch("collector.cleaning.clean_articles.clean_and_enrich_text") as mocked_clean:
                mocked_clean.return_value = "Cleaned body"
                result = clean_articles.clean_one_article(item, clean_dir)

            metadata_passed_to_dispatcher = mocked_clean.call_args[0][1]

        self.assertEqual(result["status"], "CLEANED")
        self.assertEqual(metadata_passed_to_dispatcher["tags"], ["Culture", "Music"])

    def test_dispatcher_handles_rss_tag_dictionaries_before_source_cleaning(self):
        metadata = {
            "source": "UNKNOWN_SOURCE",
            "link": "https://example.com/video/article",
            "title": "Example Title",
            "tags": [{"term": "videos", "scheme": None, "label": None}],
        }

        cleaned_text = clean_articles.clean_and_enrich_text("Raw body", metadata)

        self.assertEqual(cleaned_text, "")
        self.assertEqual(metadata["tags"], ["videos"])

    def test_clean_one_article_reuses_legacy_text_without_dispatcher(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            raw_path = self.write_raw_article(
                raw_dir,
                "article-one",
                "PUBLICO",
                {"text": "Legacy clean body"},
            )
            item = {
                "raw_path": raw_path,
                "article_id": "article-one",
                "source": "PUBLICO",
            }

            with patch("collector.cleaning.clean_articles.clean_and_enrich_text") as mocked_clean:
                result = clean_articles.clean_one_article(item, clean_dir)

            output_path = clean_dir / "article-one.json"
            saved_data = json.loads(output_path.read_text(encoding="utf-8"))

        mocked_clean.assert_not_called()
        self.assertEqual(result["status"], "CLEANED")
        self.assertEqual(saved_data["text"], "Legacy clean body")
        self.assertEqual(saved_data["cleaner"], "legacy_text")
        self.assertTrue(saved_data["is_valid_article"])

    def test_clean_one_article_writes_clean_summary_from_metadata(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            raw_path = self.write_raw_article(
                raw_dir,
                "article-with-summary",
                "PUBLICO",
                {
                    "text": "Legacy clean body",
                    "metadata": {
                        "source": "PUBLICO",
                        "link": "https://example.com/article-with-summary",
                        "title": "Example Title",
                        "summary": "<p>Hotel&nbsp;demand <strong>rises</strong></p>",
                        "tags": [],
                    },
                },
            )
            item = {
                "raw_path": raw_path,
                "article_id": "article-with-summary",
                "source": "PUBLICO",
            }

            result = clean_articles.clean_one_article(item, clean_dir)

            output_path = clean_dir / "article-with-summary.json"
            saved_data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "CLEANED")
        self.assertEqual(saved_data["summary"], "Hotel demand rises")

    def test_clean_one_article_uses_dispatcher_for_scrapingbee_content(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            raw_path = self.write_raw_article(
                raw_dir,
                "article-two",
                "BBC",
                {"scrapingbee": {"success": True, "content": "Raw body"}},
            )
            item = {
                "raw_path": raw_path,
                "article_id": "article-two",
                "source": "BBC",
            }

            with patch("collector.cleaning.clean_articles.clean_and_enrich_text") as mocked_clean:
                mocked_clean.return_value = "Cleaned body"
                result = clean_articles.clean_one_article(item, clean_dir)

            output_path = clean_dir / "article-two.json"
            saved_data = json.loads(output_path.read_text(encoding="utf-8"))

        mocked_clean.assert_called_once()
        self.assertEqual(result["status"], "CLEANED")
        self.assertEqual(saved_data["text"], "Cleaned body")
        self.assertEqual(saved_data["cleaner"], "legacy_dispatcher")
        self.assertTrue(saved_data["is_valid_article"])

    def test_clean_one_article_writes_invalid_artifact_for_missing_content(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            raw_path = self.write_raw_article(raw_dir, "article-three", "PUBLICO", {})
            item = {
                "raw_path": raw_path,
                "article_id": "article-three",
                "source": "PUBLICO",
            }

            result = clean_articles.clean_one_article(item, clean_dir)

            output_path = clean_dir / "article-three.json"
            saved_data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "FILTERED")
        self.assertEqual(saved_data["text"], "")
        self.assertEqual(saved_data["cleaner"], "missing_content")
        self.assertFalse(saved_data["is_valid_article"])

    def test_build_clean_queue_skips_existing_by_default(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_raw_article(raw_dir, "article-one", "PUBLICO", {"text": "Body"})
            (clean_dir / "article-one.json").write_text("{}", encoding="utf-8")

            queue, counts = clean_articles.build_clean_queue(
                [{"name": "PUBLICO"}],
                raw_dir=raw_dir,
                clean_dir=clean_dir,
                overwrite_existing=False,
                limit=None,
                per_source=None,
                include_unlisted_sources=False,
            )

        self.assertEqual(queue, [])
        self.assertEqual(counts["skipped_existing"], 1)

    def test_build_clean_queue_overwrite_selects_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_raw_article(raw_dir, "article-one", "PUBLICO", {"text": "Body"})
            (clean_dir / "article-one.json").write_text("{}", encoding="utf-8")

            queue, counts = clean_articles.build_clean_queue(
                [{"name": "PUBLICO"}],
                raw_dir=raw_dir,
                clean_dir=clean_dir,
                overwrite_existing=True,
                limit=None,
                per_source=None,
                include_unlisted_sources=False,
            )

        self.assertEqual(len(queue), 1)
        self.assertEqual(counts["skipped_existing"], 0)

    def test_build_clean_queue_can_include_unlisted_legacy_sources_for_all(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            raw_dir = base_dir / "raw"
            clean_dir = base_dir / "clean"
            raw_dir.mkdir()
            self.write_raw_article(raw_dir, "legacy-one", "publico_turismo", {"text": "Body"})

            queue, counts = clean_articles.build_clean_queue(
                [{"name": "PUBLICO"}],
                raw_dir=raw_dir,
                clean_dir=clean_dir,
                overwrite_existing=False,
                limit=None,
                per_source=None,
                include_unlisted_sources=True,
            )

        self.assertEqual(len(queue), 1)
        self.assertEqual(counts["skipped_source"], 0)

    def test_run_cleaning_uses_sequential_path_when_workers_one(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            clean_dir = Path(temporary_folder)
            queue = [
                {"raw_path": Path("one.json"), "article_id": "one", "source": "PUBLICO"},
                {"raw_path": Path("two.json"), "article_id": "two", "source": "PUBLICO"},
            ]
            calls = []

            def fake_clean_one_article(item, clean_dir):
                calls.append(item["article_id"])
                return {
                    "article_id": item["article_id"],
                    "source": item["source"],
                    "status": "CLEANED",
                    "output_path": str(clean_dir / f"{item['article_id']}.json"),
                    "error": None,
                }

            with patch("collector.cleaning.clean_articles.clean_one_article", fake_clean_one_article):
                with patch("collector.cleaning.clean_articles.ThreadPoolExecutor") as mocked_executor:
                    results = clean_articles.run_cleaning(queue, clean_dir, workers=1)

        mocked_executor.assert_not_called()
        self.assertEqual(calls, ["one", "two"])
        self.assertEqual(len(results), 2)

    def test_run_cleaning_uses_thread_pool_when_workers_above_one(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            clean_dir = Path(temporary_folder)
            queue = [
                {"raw_path": Path("one.json"), "article_id": "one", "source": "PUBLICO"},
            ]

            def fake_clean_one_article(item, clean_dir):
                return {
                    "article_id": item["article_id"],
                    "source": item["source"],
                    "status": "CLEANED",
                    "output_path": str(clean_dir / f"{item['article_id']}.json"),
                    "error": None,
                }

            with patch("collector.cleaning.clean_articles.clean_one_article", fake_clean_one_article):
                with patch(
                    "collector.cleaning.clean_articles.ThreadPoolExecutor",
                    wraps=clean_articles.ThreadPoolExecutor,
                ) as mocked_executor:
                    results = clean_articles.run_cleaning(queue, clean_dir, workers=2)

        mocked_executor.assert_called_once_with(max_workers=2)
        self.assertEqual(results[0]["status"], "CLEANED")


if __name__ == "__main__":
    unittest.main()
