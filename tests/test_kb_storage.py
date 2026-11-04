"""
Tests for SQLite knowledge-base storage helpers.
"""

import tempfile
import unittest
from pathlib import Path

from knowledge_bases.storage.sqlite_kb import create_kb_schema
from knowledge_bases.storage.sqlite_kb import find_vec1_extension
from knowledge_bases.storage.sqlite_kb import get_article_hashes
from knowledge_bases.storage.sqlite_kb import insert_article
from knowledge_bases.storage.sqlite_kb import list_table_names
from knowledge_bases.storage.sqlite_kb import open_kb_database


def make_article_record(article_id, status, content_hash):
    """
    Create one article record for storage tests.

    PARAMETERS:
    - article_id: Article id
    - status: Article build status
    - content_hash: Stored article hash

    RETURNS:
    - Article record dictionary
    """
    return {
        "article_id": article_id,
        "source": "PUBLICO",
        "title": "Title",
        "url": f"https://example.com/{article_id}",
        "published_at": "Fri, 01 May 2026 10:00:00 GMT",
        "indexed_at": "2026-05-01T12:00:00+00:00",
        "indexed_at_epoch": 1777636800.0,
        "cleaned_at": "2026-05-01T13:00:00+00:00",
        "input_file_path": f"shared_data/corpus/news/clean/articles/{article_id}.json",
        "content_hash": content_hash,
        "status": status,
    }


class KnowledgeBaseStorageTests(unittest.TestCase):
    def test_create_kb_schema_creates_expected_tables(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            connection = open_kb_database(db_path)

            create_kb_schema(connection)
            table_names = list_table_names(connection)
            connection.close()

        self.assertIn("articles", table_names)
        self.assertIn("build_info", table_names)
        self.assertIn("chunks", table_names)
        self.assertIn("embedding_batches", table_names)

    def test_insert_article_stores_indexed_timestamp_fields(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            connection = open_kb_database(db_path)
            create_kb_schema(connection)

            insert_article(
                connection,
                {
                    "article_id": "article-one",
                    "source": "PUBLICO",
                    "title": "Title",
                    "url": "https://example.com/one",
                    "published_at": "Fri, 01 May 2026 10:00:00 GMT",
                    "indexed_at": "2026-05-01T12:00:00+00:00",
                    "indexed_at_epoch": 1777636800.0,
                    "cleaned_at": "2026-05-01T13:00:00+00:00",
                    "input_file_path": "shared_data/corpus/news/clean/articles/article-one.json",
                    "content_hash": "abc123",
                    "status": "ready",
                },
            )

            row = connection.execute(
                """
                SELECT indexed_at, indexed_at_epoch
                FROM articles
                WHERE article_id = ?
                """,
                ("article-one",),
            ).fetchone()
            connection.close()

        self.assertEqual(row["indexed_at"], "2026-05-01T12:00:00+00:00")
        self.assertEqual(row["indexed_at_epoch"], 1777636800.0)

    def test_get_article_hashes_only_returns_ready_articles(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            connection = open_kb_database(db_path)
            create_kb_schema(connection)

            insert_article(connection, make_article_record("ready-article", "ready", "ready-hash"))
            insert_article(connection, make_article_record("embedding-article", "embedding", "embedding-hash"))

            article_hashes = get_article_hashes(connection)
            connection.close()

        self.assertEqual(article_hashes, {"ready-article": "ready-hash"})

    def test_find_vec1_extension_returns_existing_dylib(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            tools_folder = Path(temp_folder)
            extension_path = tools_folder / "vec1.dylib"
            extension_path.write_text("fake extension", encoding="utf-8")

            found_path = find_vec1_extension(tools_folder)

        self.assertEqual(found_path, extension_path)

    def test_find_vec1_extension_returns_existing_so(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            tools_folder = Path(temp_folder)
            extension_path = tools_folder / "vec1.so"
            extension_path.write_text("fake extension", encoding="utf-8")

            found_path = find_vec1_extension(tools_folder)

        self.assertEqual(found_path, extension_path)

    def test_find_vec1_extension_fails_when_missing(self):
        with self.assertRaises(ValueError):
            find_vec1_extension(Path("/path/that/does/not/exist"))


if __name__ == "__main__":
    unittest.main()
