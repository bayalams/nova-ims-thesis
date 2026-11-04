"""
Tests for corpus inspector SQLite queries.
"""

import json
import tempfile
import unittest
from pathlib import Path

from explorer.webapps.corpus_inspector.indexer import build_corpus_index
from explorer.webapps.corpus_inspector.queries import get_article_detail
from explorer.webapps.corpus_inspector.queries import get_article_page
from explorer.webapps.corpus_inspector.queries import get_facets
from explorer.webapps.corpus_inspector.queries import get_summary
from explorer.webapps.corpus_inspector.queries import load_json_text


class CorpusInspectorQueryTests(unittest.TestCase):
    def write_json(self, path, data):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def make_index(self):
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name)
        raw_dir = root / "raw"
        clean_dir = root / "clean"
        index_path = root / "index.sqlite"
        raw_dir.mkdir()
        clean_dir.mkdir()
        fixtures = [
            ("one", "BBC", "Airport demand", "Airport demand rises in Lisbon with more tourism bookings.", "2026-05-01T10:00:00+00:00"),
            ("two", "RTP", "Short item", "short", "2026-05-02T10:00:00+00:00"),
            ("three", "BBC", "Hotel demand", "Hotel demand rises in Porto with tourism growth.", "2026-05-03T10:00:00+00:00"),
        ]
        for article_id, source, title, text, published in fixtures:
            self.write_json(raw_dir / f"{article_id}.json", {"id": article_id, "source": source, "link": f"https://example.com/{article_id}", "metadata": {"title": title, "published": published}, "text": text})
            self.write_json(clean_dir / f"{article_id}.json", {"id": article_id, "source": source, "link": f"https://example.com/{article_id}", "title": title, "text": text, "cleaner": "test", "is_valid_article": True})
        build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=20)
        return folder, index_path

    def test_get_summary_returns_counts(self):
        folder, index_path = self.make_index()
        try:
            summary = get_summary(index_path)
        finally:
            folder.cleanup()

        self.assertEqual(summary["total_articles"], 3)
        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["clean_file_count"], 3)
        self.assertGreater(summary["issue_rate"], 0)

    def test_get_article_page_filters_sorts_and_paginates(self):
        folder, index_path = self.make_index()
        try:
            page = get_article_page(index_path, {"source": "BBC", "search": "demand", "sort": "published_at", "direction": "desc", "page": "1", "page_size": "1"})
        finally:
            folder.cleanup()

        self.assertEqual(page["total"], 2)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 1)
        self.assertEqual(len(page["rows"]), 1)
        self.assertEqual(page["rows"][0]["article_id"], "three")

    def test_get_article_page_sorts_null_published_at_last(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_json(raw_dir / "dated.json", {"id": "dated", "source": "BBC", "metadata": {"title": "Dated", "published": "2026-05-01T10:00:00+00:00"}, "text": "Dated article has enough words for checking."})
            self.write_json(clean_dir / "dated.json", {"id": "dated", "source": "BBC", "title": "Dated", "text": "Dated article has enough words for checking.", "is_valid_article": True})
            self.write_json(raw_dir / "undated.json", {"id": "undated", "source": "BBC", "metadata": {"title": "Undated"}, "text": "Undated article has enough words for checking."})
            self.write_json(clean_dir / "undated.json", {"id": "undated", "source": "BBC", "title": "Undated", "text": "Undated article has enough words for checking.", "is_valid_article": True})

            build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=20)
            page = get_article_page(index_path, {"sort": "published_at", "direction": "asc"})

        article_ids = []
        for row in page["rows"]:
            article_ids.append(row["article_id"])

        self.assertEqual(article_ids, ["dated", "undated"])

    def test_get_article_page_rejects_bad_sort(self):
        folder, index_path = self.make_index()
        try:
            with self.assertRaises(ValueError):
                get_article_page(index_path, {"sort": "bad_field"})
        finally:
            folder.cleanup()

    def test_get_facets_respects_filters(self):
        folder, index_path = self.make_index()
        try:
            facets = get_facets(index_path, {"source": "BBC"})
        finally:
            folder.cleanup()

        self.assertIn("sources", facets)
        self.assertEqual(facets["sources"]["BBC"], 2)
        self.assertIn("severities", facets)

    def test_get_article_detail_returns_issues_and_previews(self):
        folder, index_path = self.make_index()
        try:
            detail = get_article_detail(index_path, "two")
        finally:
            folder.cleanup()

        self.assertEqual(detail["article"]["article_id"], "two")
        self.assertIn("short_clean_text", detail["issues"])
        self.assertIn("clean_preview", detail)

    def test_load_json_text_uses_article_text_fallbacks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            text_path = root / "text.json"
            scrapingbee_content_path = root / "scrapingbee-content.json"
            scrapingbee_body_path = root / "scrapingbee-body.json"
            content_path = root / "content.json"
            body_path = root / "body.json"
            invalid_path = root / "invalid.json"
            whitespace_content_path = root / "whitespace-content.json"
            whitespace_scrapingbee_path = root / "whitespace-scrapingbee.json"
            self.write_json(text_path, {"text": "Top-level text preview"})
            self.write_json(scrapingbee_content_path, {"scrapingbee": {"content": "ScrapingBee content preview"}})
            self.write_json(scrapingbee_body_path, {"scrapingbee": {"body": "ScrapingBee body preview"}})
            self.write_json(content_path, {"content": "Top-level content preview"})
            self.write_json(body_path, {"body": "Top-level body preview"})
            invalid_path.write_text("{bad json", encoding="utf-8")
            self.write_json(whitespace_content_path, {"text": "   ", "content": "usable content"})
            self.write_json(whitespace_scrapingbee_path, {"text": None, "scrapingbee": {"content": "   ", "body": "usable body"}})

            text_preview = load_json_text(text_path)
            scrapingbee_content_preview = load_json_text(scrapingbee_content_path)
            scrapingbee_body_preview = load_json_text(scrapingbee_body_path)
            content_preview = load_json_text(content_path)
            body_preview = load_json_text(body_path)
            invalid_preview = load_json_text(invalid_path)
            whitespace_content_preview = load_json_text(whitespace_content_path)
            whitespace_scrapingbee_preview = load_json_text(whitespace_scrapingbee_path)

        self.assertEqual(text_preview, "Top-level text preview")
        self.assertEqual(scrapingbee_content_preview, "ScrapingBee content preview")
        self.assertEqual(scrapingbee_body_preview, "ScrapingBee body preview")
        self.assertEqual(content_preview, "Top-level content preview")
        self.assertEqual(body_preview, "Top-level body preview")
        self.assertEqual(invalid_preview, "")
        self.assertEqual(whitespace_content_preview, "usable content")
        self.assertEqual(whitespace_scrapingbee_preview, "usable body")


if __name__ == "__main__":
    unittest.main()
