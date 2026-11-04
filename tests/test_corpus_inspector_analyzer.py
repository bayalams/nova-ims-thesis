"""
Tests for corpus inspector article analysis.
"""

import tempfile
import unittest
from pathlib import Path

from explorer.webapps.corpus_inspector.analyzer import analyze_article_pair
from explorer.webapps.corpus_inspector.analyzer import count_words
from explorer.webapps.corpus_inspector.analyzer import parse_timestamp_to_epoch
from explorer.webapps.corpus_inspector.analyzer import shorten_text


class CorpusInspectorAnalyzerTests(unittest.TestCase):
    def test_shorten_text_caps_long_text(self):
        text = "a" * 30

        result = shorten_text(text, 10)

        self.assertEqual(result, "aaaaaaaaaa\n\n[TRUNCATED]")

    def test_count_words_handles_plain_text(self):
        self.assertEqual(count_words("Hotel demand rises in Lisbon."), 5)

    def test_parse_timestamp_treats_naive_values_as_utc(self):
        naive_iso = parse_timestamp_to_epoch("2026-05-01T10:00:00")
        utc_iso = parse_timestamp_to_epoch("2026-05-01T10:00:00+00:00")
        naive_rss = parse_timestamp_to_epoch("Fri, 01 May 2026 10:00:00")
        utc_rss = parse_timestamp_to_epoch("Fri, 01 May 2026 10:00:00 +0000")

        self.assertEqual(naive_iso, utc_iso)
        self.assertEqual(naive_rss, utc_rss)

    def test_analyze_article_pair_detects_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "one.json"
            clean_path = Path(folder) / "one.json"
            raw_article = {
                "id": "one",
                "source": "BBC",
                "link": "https://example.com/one",
                "metadata": {
                    "title": "Hotel demand rises",
                    "published": "2026-05-01T10:00:00+00:00",
                    "indexed_at": "2026-05-01T11:00:00+00:00",
                },
                "scraped_at": "2026-05-01T12:00:00+00:00",
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
            }
            clean_article = {
                "id": "one",
                "source": "BBC",
                "link": "https://example.com/one",
                "title": "Hotel demand rises",
                "summary": "Visitors booked more rooms.",
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
                "cleaned_at": "2026-05-01T13:00:00+00:00",
                "cleaner": "test_cleaner",
                "is_valid_article": True,
            }

            result = analyze_article_pair(raw_article, clean_article, raw_path, clean_path, 20)

        self.assertEqual(result["article_id"], "one")
        self.assertEqual(result["source"], "BBC")
        self.assertEqual(result["severity"], "pass")
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["passed_deterministic_checks"])
        self.assertEqual(result["raw_word_count"], 9)
        self.assertEqual(result["clean_word_count"], 9)
        self.assertEqual(result["cleaner"], "test_cleaner")

    def test_analyze_article_pair_detects_common_issues(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "two.json"
            clean_path = Path(folder) / "two.json"
            raw_article = {
                "id": "two",
                "source": "BBC",
                "link": "https://example.com/raw",
                "metadata": {"title": "Raw title"},
                "text": "A raw article with enough text for comparison.",
            }
            clean_article = {
                "id": "two",
                "source": "OTHER",
                "link": "",
                "title": "",
                "text": "<div>Subscribe to our newsletter</div>",
                "is_valid_article": False,
            }

            result = analyze_article_pair(raw_article, clean_article, raw_path, clean_path, 100)

        self.assertIn("source_mismatch", result["issues"])
        self.assertIn("missing_clean_link", result["issues"])
        self.assertIn("missing_title", result["issues"])
        self.assertIn("clean_marked_invalid", result["issues"])
        self.assertIn("short_clean_text", result["issues"])
        self.assertIn("contains_html_tags", result["issues"])
        self.assertIn("contains_boilerplate", result["issues"])
        self.assertEqual(result["severity"], "error")
        self.assertFalse(result["passed_deterministic_checks"])

    def test_analyze_article_pair_uses_clean_metadata_source_and_link(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "three.json"
            clean_path = Path(folder) / "three.json"
            raw_article = {
                "id": "three",
                "source": "BBC",
                "link": "https://example.com/three",
                "metadata": {"title": "Metadata source and link"},
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
            }
            clean_article = {
                "id": "three",
                "title": "Metadata source and link",
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
                "metadata": {
                    "source": "BBC",
                    "link": "https://example.com/three",
                },
                "is_valid_article": True,
            }

            result = analyze_article_pair(raw_article, clean_article, raw_path, clean_path, 20)

        self.assertNotIn("source_mismatch", result["issues"])
        self.assertNotIn("missing_clean_link", result["issues"])
        self.assertNotIn("link_mismatch", result["issues"])
        self.assertEqual(result["link"], "https://example.com/three")

    def test_analyze_article_pair_prefers_raw_id_over_clean_id(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "raw-id.json"
            clean_path = Path(folder) / "raw-id.json"
            raw_article = {
                "id": "raw-id",
                "source": "BBC",
                "link": "https://example.com/raw-id",
                "metadata": {"title": "Raw ID wins"},
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
            }
            clean_article = {
                "id": "wrong-clean-id",
                "source": "BBC",
                "link": "https://example.com/raw-id",
                "title": "Raw ID wins",
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
                "is_valid_article": True,
            }

            result = analyze_article_pair(raw_article, clean_article, raw_path, clean_path, 20)

        self.assertEqual(result["article_id"], "raw-id")

    def test_analyze_article_pair_prefers_raw_path_stem_over_clean_id(self):
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "raw-stem-id.json"
            clean_path = Path(folder) / "raw-stem-id.json"
            raw_article = {
                "source": "BBC",
                "link": "https://example.com/raw-stem-id",
                "metadata": {"title": "Raw path stem wins"},
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
            }
            clean_article = {
                "id": "wrong-clean-id",
                "source": "BBC",
                "link": "https://example.com/raw-stem-id",
                "title": "Raw path stem wins",
                "text": "Hotel demand rises in Lisbon. Visitors booked more rooms.",
                "is_valid_article": True,
            }

            result = analyze_article_pair(raw_article, clean_article, raw_path, clean_path, 20)

        self.assertEqual(result["article_id"], "raw-stem-id")


if __name__ == "__main__":
    unittest.main()
