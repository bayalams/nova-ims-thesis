"""
Tests for RSS link indexing.

These tests avoid real network calls. They protect the RSS indexing behavior
with small fake feed entries and temporary output folders.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from collector.feeds import index_links


class IndexLinksTests(unittest.TestCase):
    def test_create_fingerprint_is_stable(self):
        first = index_links.create_fingerprint(
            "Title",
            "https://example.com/article",
            "Thu, 07 May 2026 12:00:00 GMT",
        )
        second = index_links.create_fingerprint(
            "Title",
            "https://example.com/article",
            "Thu, 07 May 2026 12:00:00 GMT",
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

        changed_title = index_links.create_fingerprint(
            "Different title",
            "https://example.com/article",
            "Thu, 07 May 2026 12:00:00 GMT",
        )
        changed_link = index_links.create_fingerprint(
            "Title",
            "https://example.com/different-article",
            "Thu, 07 May 2026 12:00:00 GMT",
        )
        changed_published = index_links.create_fingerprint(
            "Title",
            "https://example.com/article",
            "Thu, 07 May 2026 13:00:00 GMT",
        )

        self.assertNotEqual(first, changed_title)
        self.assertNotEqual(first, changed_link)
        self.assertNotEqual(first, changed_published)

    def test_freshness_filters_old_article(self):
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        old_date = now - timedelta(days=91)

        is_fresh = index_links.is_article_fresh(
            old_date.utctimetuple(),
            max_age_days=90,
            now=now,
        )

        self.assertFalse(is_fresh)

    def test_missing_parsed_date_is_kept(self):
        output = io.StringIO()

        with redirect_stdout(output):
            is_fresh = index_links.is_article_fresh(
                None,
                max_age_days=90,
                now=datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc),
            )

        self.assertTrue(is_fresh)
        self.assertEqual(output.getvalue(), "")

    def test_entry_is_converted_to_article_dictionary(self):
        entry = {
            "title": "Example headline",
            "link": "https://example.com/article",
            "published": "Thu, 07 May 2026 12:00:00 GMT",
            "summary": "Short summary",
            "author": "Reporter Name",
            "authors": [{"name": "Reporter Name"}],
            "tags": [{"term": "travel"}],
            "media_content": [{"url": "https://example.com/image.jpg"}],
            "media_thumbnail": [{"url": "https://example.com/thumb.jpg"}],
            "content": [{"value": "Body preview"}],
            "updated": "Thu, 07 May 2026 12:30:00 GMT",
            "id": "feed-entry-id",
        }

        article = index_links.article_from_entry(
            entry,
            source_name="PUBLICO",
            indexed_at="2026-05-07T12:00:00+00:00",
        )

        self.assertEqual(article["source"], "PUBLICO")
        self.assertEqual(article["title"], "Example headline")
        self.assertEqual(article["link"], "https://example.com/article")
        self.assertEqual(article["published"], "Thu, 07 May 2026 12:00:00 GMT")
        self.assertEqual(article["summary"], "Short summary")
        self.assertEqual(article["author"], "Reporter Name")
        self.assertEqual(article["authors"], [{"name": "Reporter Name"}])
        self.assertEqual(article["tags"], [{"term": "travel"}])
        self.assertEqual(article["media_content"], [{"url": "https://example.com/image.jpg"}])
        self.assertEqual(article["media_thumbnail"], [{"url": "https://example.com/thumb.jpg"}])
        self.assertEqual(article["content"], [{"value": "Body preview"}])
        self.assertEqual(article["updated"], "Thu, 07 May 2026 12:30:00 GMT")
        self.assertEqual(article["feed_id"], "feed-entry-id")
        self.assertEqual(article["indexed_at"], "2026-05-07T12:00:00+00:00")
        self.assertEqual(len(article["fingerprint"]), 64)

    def test_entry_with_missing_optional_fields_gets_safe_defaults(self):
        entry = {
            "title": "Minimal headline",
            "link": "https://example.com/minimal",
            "published": "Thu, 07 May 2026 12:00:00 GMT",
        }

        article = index_links.article_from_entry(
            entry,
            source_name="PUBLICO",
            indexed_at="2026-05-07T12:00:00+00:00",
        )

        self.assertEqual(article["summary"], "")
        self.assertEqual(article["author"], "")
        self.assertEqual(article["authors"], [])
        self.assertEqual(article["tags"], [])
        self.assertEqual(article["media_content"], [])
        self.assertEqual(article["media_thumbnail"], [])
        self.assertEqual(article["content"], [])
        self.assertEqual(article["updated"], "")
        self.assertEqual(article["feed_id"], "")

    def test_source_output_path_uses_shared_data_layout(self):
        output_path = index_links.get_source_output_path(
            "PUBLICO",
            "20260507_120000",
        )

        expected_path = Path(
            "shared_data/corpus/news/raw/links/PUBLICO/20260507_120000.jsonl"
        )
        self.assertEqual(output_path, expected_path)

    def test_write_articles_to_jsonl_writes_one_object_per_line(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            output_path = Path(temporary_folder) / "PUBLICO" / "links.jsonl"
            articles = [
                {"title": "First article", "source": "PUBLICO"},
                {"title": "Second article", "source": "PUBLICO"},
            ]

            did_write = index_links.write_articles_to_jsonl(
                articles,
                output_path,
                overwrite_existing=False,
            )

            self.assertTrue(did_write)

            lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["title"], "First article")
            self.assertEqual(json.loads(lines[1])["title"], "Second article")

    def test_write_articles_to_jsonl_skips_existing_file_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            output_path = Path(temporary_folder) / "PUBLICO" / "links.jsonl"
            output_path.parent.mkdir(parents=True)
            output_path.write_text("existing\n", encoding="utf-8")

            did_write = index_links.write_articles_to_jsonl(
                [{"title": "Replacement"}],
                output_path,
                overwrite_existing=False,
            )

            self.assertFalse(did_write)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "existing\n")

    def test_parse_feed_converts_feedparser_entries_without_network(self):
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        source = {"name": "PUBLICO", "url": "https://example.com/feed"}
        entry = {
            "title": "Example headline",
            "link": "https://example.com/article",
            "published": "Thu, 07 May 2026 12:00:00 GMT",
            "published_parsed": now.utctimetuple(),
        }

        with patch("collector.feeds.index_links.feedparser.parse") as mocked_parse:
            mocked_parse.return_value = {"entries": [entry]}
            result = index_links.parse_feed(
                source,
                max_age_days=90,
                indexed_at="2026-05-07T12:00:00+00:00",
                now=now,
            )

        self.assertEqual(result["source"], "PUBLICO")
        self.assertEqual(result["status"], "PARSED")
        self.assertEqual(result["article_count"], 1)
        self.assertEqual(result["skipped_stale"], 0)
        self.assertEqual(result["articles"][0]["title"], "Example headline")
        mocked_parse.assert_called_once_with("https://example.com/feed")

    def test_parse_feed_filters_stale_entries(self):
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        old_date = now - timedelta(days=120)
        source = {"name": "PUBLICO", "url": "https://example.com/feed"}
        entry = {
            "title": "Old headline",
            "link": "https://example.com/old",
            "published": "Old date",
            "published_parsed": old_date.utctimetuple(),
        }

        with patch("collector.feeds.index_links.feedparser.parse") as mocked_parse:
            mocked_parse.return_value = {"entries": [entry]}
            result = index_links.parse_feed(
                source,
                max_age_days=90,
                indexed_at="2026-05-07T12:00:00+00:00",
                now=now,
            )

        self.assertEqual(result["article_count"], 0)
        self.assertEqual(result["skipped_stale"], 1)

    def test_parse_feed_warns_and_keeps_unparseable_published_text(self):
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        source = {"name": "PUBLICO", "url": "https://example.com/feed"}
        entry = {
            "title": "Odd date headline",
            "link": "https://example.com/odd-date",
            "published": "not a real date",
            "published_parsed": None,
        }
        output = io.StringIO()

        with patch("collector.feeds.index_links.feedparser.parse") as mocked_parse:
            mocked_parse.return_value = {"entries": [entry]}

            with redirect_stdout(output):
                result = index_links.parse_feed(
                    source,
                    max_age_days=90,
                    indexed_at="2026-05-07T12:00:00+00:00",
                    now=now,
                )

        self.assertEqual(result["article_count"], 1)
        self.assertEqual(result["skipped_stale"], 0)
        self.assertIn("[WARNING]", output.getvalue())
        self.assertIn("not a real date", output.getvalue())

    def test_index_one_source_treats_failed_parse_as_error(self):
        source = {"name": "PUBLICO", "url": "https://example.com/feed"}

        with patch("collector.feeds.index_links.feedparser.parse") as mocked_parse:
            mocked_parse.return_value = {
                "entries": [],
                "bozo": True,
                "bozo_exception": Exception("connection failed"),
            }
            result = index_links.index_one_source(
                source,
                overwrite_existing=False,
                max_age_days=90,
                output_dir=Path("example_output"),
                timestamp_text="20260507_120000",
                indexed_at="2026-05-07T12:00:00+00:00",
            )

        self.assertEqual(result["source"], "PUBLICO")
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["article_count"], 0)
        self.assertIn("connection failed", result["error"])

    def test_index_one_source_treats_http_error_status_as_error(self):
        source = {"name": "PUBLICO", "url": "https://example.com/feed"}

        with patch("collector.feeds.index_links.feedparser.parse") as mocked_parse:
            mocked_parse.return_value = {
                "entries": [],
                "status": 500,
            }
            result = index_links.index_one_source(
                source,
                overwrite_existing=False,
                max_age_days=90,
                output_dir=Path("example_output"),
                timestamp_text="20260507_120000",
                indexed_at="2026-05-07T12:00:00+00:00",
            )

        self.assertEqual(result["source"], "PUBLICO")
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["article_count"], 0)
        self.assertIn("HTTP status", result["error"])
        self.assertIn("500", result["error"])

    def test_parse_feed_keeps_entries_from_partial_bozo_parse(self):
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        source = {"name": "PUBLICO", "url": "https://example.com/feed"}
        entry = {
            "title": "Partial parse headline",
            "link": "https://example.com/partial",
            "published": "Thu, 07 May 2026 12:00:00 GMT",
            "published_parsed": now.utctimetuple(),
        }

        with patch("collector.feeds.index_links.feedparser.parse") as mocked_parse:
            mocked_parse.return_value = {
                "entries": [entry],
                "bozo": True,
                "bozo_exception": Exception("partial parse"),
            }
            result = index_links.parse_feed(
                source,
                max_age_days=90,
                indexed_at="2026-05-07T12:00:00+00:00",
                now=now,
            )

        self.assertEqual(result["status"], "PARSED")
        self.assertEqual(result["article_count"], 1)
        self.assertEqual(result["articles"][0]["title"], "Partial parse headline")

    def test_run_indexing_uses_sequential_path_when_workers_one(self):
        sources = [
            {"name": "PUBLICO", "url": "https://example.com/publico"},
            {"name": "BBC", "url": "https://example.com/bbc"},
        ]
        calls = []

        def fake_index_one_source(
            source,
            overwrite_existing,
            max_age_days,
            output_dir,
            timestamp_text,
            indexed_at,
        ):
            calls.append(source["name"])
            return {
                "source": source["name"],
                "status": "SAVED",
                "article_count": 1,
                "output_path": str(output_dir / source["name"] / f"{timestamp_text}.jsonl"),
                "skipped_stale": 0,
                "error": None,
            }

        with patch("collector.feeds.index_links.index_one_source", fake_index_one_source):
            with patch("collector.feeds.index_links.ThreadPoolExecutor") as mocked_executor:
                results = index_links.run_indexing(
                    sources,
                    overwrite_existing=False,
                    workers=1,
                    max_age_days=90,
                    output_dir=Path("example_output"),
                    timestamp_text="20260507_120000",
                    indexed_at="2026-05-07T12:00:00+00:00",
                )

        mocked_executor.assert_not_called()
        self.assertEqual(calls, ["PUBLICO", "BBC"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["status"], "SAVED")

    def test_run_indexing_accepts_threaded_mode(self):
        sources = [
            {"name": "PUBLICO", "url": "https://example.com/publico"},
            {"name": "BBC", "url": "https://example.com/bbc"},
        ]

        def fake_index_one_source(
            source,
            overwrite_existing,
            max_age_days,
            output_dir,
            timestamp_text,
            indexed_at,
        ):
            return {
                "source": source["name"],
                "status": "SAVED",
                "article_count": 1,
                "output_path": str(output_dir / source["name"] / f"{timestamp_text}.jsonl"),
                "skipped_stale": 0,
                "error": None,
            }

        with patch("collector.feeds.index_links.index_one_source", fake_index_one_source):
            with patch(
                "collector.feeds.index_links.ThreadPoolExecutor",
                wraps=ThreadPoolExecutor,
            ) as mocked_executor:
                results = index_links.run_indexing(
                    sources,
                    overwrite_existing=False,
                    workers=2,
                    max_age_days=90,
                    output_dir=Path("example_output"),
                    timestamp_text="20260507_120000",
                    indexed_at="2026-05-07T12:00:00+00:00",
                )

        result_sources = []

        for result in results:
            result_sources.append(result["source"])

        mocked_executor.assert_called_once_with(max_workers=2)
        self.assertEqual(len(results), 2)
        self.assertCountEqual(result_sources, ["PUBLICO", "BBC"])

    def test_index_links_returns_error_when_every_source_fails(self):
        sources = [
            {"name": "PUBLICO", "url": "https://example.com/publico"},
        ]

        with patch("collector.feeds.index_links.run_indexing") as mocked_run:
            mocked_run.return_value = [
                {
                    "source": "PUBLICO",
                    "status": "ERROR",
                    "article_count": 0,
                    "output_path": None,
                    "skipped_stale": 0,
                    "error": "network failed",
                }
            ]
            exit_code = index_links.index_links(
                sources,
                overwrite_existing=False,
                workers=1,
                max_age_days=90,
            )

        self.assertEqual(exit_code, 1)
        mocked_run.assert_called_once()

        call_arguments = mocked_run.call_args
        called_sources = call_arguments.kwargs.get("sources")
        called_overwrite_existing = call_arguments.kwargs.get("overwrite_existing")
        called_workers = call_arguments.kwargs.get("workers")
        called_max_age_days = call_arguments.kwargs.get("max_age_days")

        if called_sources is None:
            called_sources = call_arguments.args[0]
        if called_overwrite_existing is None:
            called_overwrite_existing = call_arguments.args[1]
        if called_workers is None:
            called_workers = call_arguments.args[2]
        if called_max_age_days is None:
            called_max_age_days = call_arguments.args[3]

        self.assertEqual(called_sources, sources)
        self.assertEqual(called_overwrite_existing, False)
        self.assertEqual(called_workers, 1)
        self.assertEqual(called_max_age_days, 90)


if __name__ == "__main__":
    unittest.main()
