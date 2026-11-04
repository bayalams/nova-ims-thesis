"""
Tests for corpus inspector SQLite indexing.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from explorer.webapps.corpus_inspector.indexer import build_corpus_index
from explorer.webapps.corpus_inspector.indexer import get_index_status


class CorpusInspectorIndexerTests(unittest.TestCase):
    def write_json(self, path, data):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def test_build_corpus_index_writes_articles_issues_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_json(
                raw_dir / "one.json",
                {
                    "id": "one",
                    "source": "BBC",
                    "link": "https://example.com/one",
                    "metadata": {"title": "One", "published": "2026-05-01T10:00:00+00:00"},
                    "text": "One article has enough useful words for checking.",
                },
            )
            self.write_json(
                clean_dir / "one.json",
                {
                    "id": "one",
                    "source": "BBC",
                    "link": "https://example.com/one",
                    "title": "One",
                    "text": "One article has enough useful words for checking.",
                    "is_valid_article": True,
                    "cleaner": "test",
                },
            )

            result = build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=20)

            connection = sqlite3.connect(index_path)
            connection.row_factory = sqlite3.Row
            articles = connection.execute("SELECT * FROM articles").fetchall()
            metadata = connection.execute("SELECT key, value FROM index_metadata").fetchall()
            issues = connection.execute("SELECT * FROM article_issues").fetchall()
            connection.close()

        self.assertEqual(result["article_count"], 1)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["article_id"], "one")
        self.assertEqual(articles[0]["source"], "BBC")
        self.assertEqual(articles[0]["severity"], "pass")
        self.assertEqual(len(issues), 0)
        self.assertIn(("article_count", "1"), [(row["key"], row["value"]) for row in metadata])

    def test_build_corpus_index_records_missing_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_json(raw_dir / "missing-clean.json", {"id": "missing-clean", "source": "BBC", "text": "Raw only"})
            (clean_dir / "bad-clean.json").write_text("{bad json", encoding="utf-8")

            result = build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path)

            connection = sqlite3.connect(index_path)
            issues = [row[0] for row in connection.execute("SELECT issue_name FROM article_issues ORDER BY issue_name").fetchall()]
            connection.close()

        self.assertEqual(result["article_count"], 2)
        self.assertIn("missing_clean_file", issues)
        self.assertIn("missing_raw_file", issues)
        self.assertIn("invalid_clean_json", issues)

    def test_build_corpus_index_records_both_invalid_json_issues(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            (raw_dir / "bad.json").write_text("{bad raw", encoding="utf-8")
            (clean_dir / "bad.json").write_text("{bad clean", encoding="utf-8")

            build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path)

            connection = sqlite3.connect(index_path)
            connection.row_factory = sqlite3.Row
            article = connection.execute("SELECT * FROM articles WHERE article_id = ?", ("bad",)).fetchone()
            issues = [
                row[0]
                for row in connection.execute(
                    "SELECT issue_name FROM article_issues WHERE article_id = ? ORDER BY issue_name",
                    ("bad",),
                ).fetchall()
            ]
            connection.close()

        self.assertEqual(article["raw_json_valid"], 0)
        self.assertEqual(article["clean_json_valid"], 0)
        self.assertEqual(article["issue_count"], 2)
        self.assertEqual(article["recommended_action"], "reclean")
        self.assertEqual(issues, ["invalid_clean_json", "invalid_raw_json"])

    def test_build_corpus_index_records_non_utf8_json_as_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            (raw_dir / "bad-utf8.json").write_bytes(b"\xff\xfe\xfa")

            result = build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path)

            connection = sqlite3.connect(index_path)
            connection.row_factory = sqlite3.Row
            article = connection.execute("SELECT * FROM articles WHERE article_id = ?", ("bad-utf8",)).fetchone()
            issues = [
                row[0]
                for row in connection.execute(
                    "SELECT issue_name FROM article_issues WHERE article_id = ?",
                    ("bad-utf8",),
                ).fetchall()
            ]
            connection.close()

        self.assertEqual(result["article_count"], 1)
        self.assertEqual(article["raw_json_valid"], 0)
        self.assertIn("invalid_raw_json", issues)

    def test_build_corpus_index_pairs_raw_stem_with_clean_internal_id(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_json(
                raw_dir / "stem.json",
                {
                    "id": "real-id",
                    "source": "BBC",
                    "link": "https://example.com/real-id",
                    "metadata": {"title": "Real ID"},
                    "text": "This raw article has enough useful words for checking.",
                },
            )
            self.write_json(
                clean_dir / "real-id.json",
                {
                    "id": "real-id",
                    "source": "BBC",
                    "link": "https://example.com/real-id",
                    "title": "Real ID",
                    "text": "This raw article has enough useful words for checking.",
                    "is_valid_article": True,
                },
            )

            result = build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=20)

            connection = sqlite3.connect(index_path)
            connection.row_factory = sqlite3.Row
            articles = connection.execute("SELECT * FROM articles").fetchall()
            issues = [row[0] for row in connection.execute("SELECT issue_name FROM article_issues").fetchall()]
            connection.close()

        self.assertEqual(result["article_count"], 1)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["article_id"], "real-id")
        self.assertEqual(articles[0]["has_raw_file"], 1)
        self.assertEqual(articles[0]["has_clean_file"], 1)
        self.assertNotIn("missing_raw_file", issues)
        self.assertNotIn("missing_clean_file", issues)

    def test_missing_pair_rows_keep_existing_file_metadata_and_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_json(
                raw_dir / "raw-only.json",
                {
                    "id": "raw-only",
                    "source": "BBC",
                    "link": "https://example.com/raw-only",
                    "metadata": {"title": "Raw Only", "published": "2026-05-01T10:00:00"},
                    "text": "Raw only article keeps useful metadata and counts.",
                },
            )
            self.write_json(
                clean_dir / "clean-only.json",
                {
                    "id": "clean-only",
                    "source": "RTP",
                    "link": "https://example.com/clean-only",
                    "title": "Clean Only",
                    "text": "Clean only article keeps useful metadata and counts.",
                    "cleaner": "test",
                    "is_valid_article": True,
                },
            )

            build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=10)

            connection = sqlite3.connect(index_path)
            connection.row_factory = sqlite3.Row
            raw_row = connection.execute("SELECT * FROM articles WHERE article_id = ?", ("raw-only",)).fetchone()
            clean_row = connection.execute("SELECT * FROM articles WHERE article_id = ?", ("clean-only",)).fetchone()
            raw_issues = [row[0] for row in connection.execute("SELECT issue_name FROM article_issues WHERE article_id = ?", ("raw-only",)).fetchall()]
            clean_issues = [row[0] for row in connection.execute("SELECT issue_name FROM article_issues WHERE article_id = ?", ("clean-only",)).fetchall()]
            connection.close()

        self.assertEqual(raw_row["source"], "BBC")
        self.assertEqual(raw_row["title"], "Raw Only")
        self.assertGreater(raw_row["raw_word_count"], 0)
        self.assertEqual(raw_row["has_clean_file"], 0)
        self.assertEqual(raw_issues, ["missing_clean_file"])
        self.assertEqual(clean_row["source"], "RTP")
        self.assertEqual(clean_row["title"], "Clean Only")
        self.assertGreater(clean_row["clean_word_count"], 0)
        self.assertEqual(clean_row["has_raw_file"], 0)
        self.assertEqual(clean_issues, ["missing_raw_file"])

    def test_clean_only_non_object_json_does_not_crash_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            self.write_json(clean_dir / "clean-list.json", ["not", "an", "article"])

            build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=10)

            connection = sqlite3.connect(index_path)
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM articles WHERE article_id = ?", ("clean-list",)).fetchone()
            issues = [issue_row[0] for issue_row in connection.execute("SELECT issue_name FROM article_issues WHERE article_id = ?", ("clean-list",)).fetchall()]
            connection.close()

        self.assertEqual(row["source"], "UNKNOWN")
        self.assertEqual(row["has_raw_file"], 0)
        self.assertEqual(row["clean_json_valid"], 1)
        self.assertEqual(issues, ["missing_raw_file"])

    def test_duplicate_clean_text_updates_group_sizes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw_dir = root / "raw"
            clean_dir = root / "clean"
            index_path = root / "index.sqlite"
            raw_dir.mkdir()
            clean_dir.mkdir()
            for article_id in ["one", "two"]:
                self.write_json(raw_dir / f"{article_id}.json", {"id": article_id, "source": "BBC", "text": "Raw text"})
                self.write_json(clean_dir / f"{article_id}.json", {"id": article_id, "source": "BBC", "title": article_id, "link": "https://example.com", "text": "Same clean text with enough length"})

            build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=10)

            connection = sqlite3.connect(index_path)
            group_sizes = [row[0] for row in connection.execute("SELECT duplicate_group_size FROM articles ORDER BY article_id").fetchall()]
            issues = [row[0] for row in connection.execute("SELECT issue_name FROM article_issues ORDER BY article_id").fetchall()]
            connection.close()

        self.assertEqual(group_sizes, [2, 2])
        self.assertEqual(issues.count("duplicate_clean_text"), 2)

    def test_get_index_status_reports_missing_and_existing_index(self):
        with tempfile.TemporaryDirectory() as folder:
            index_path = Path(folder) / "index.sqlite"
            missing = get_index_status(index_path)
            index_path.write_text("", encoding="utf-8")
            existing = get_index_status(index_path)

        self.assertFalse(missing["exists"])
        self.assertTrue(existing["exists"])


if __name__ == "__main__":
    unittest.main()
