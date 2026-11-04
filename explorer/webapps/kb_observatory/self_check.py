"""
Small self-checks for the KB Observatory explorer.

These checks stay inside explorer/ so the app can be developed without changing
the repo's standard tests.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from explorer.webapps.kb_observatory.queries import get_kb_summary
from explorer.webapps.kb_observatory.queries import get_recipe_detail


class KbObservatorySelfCheck(unittest.TestCase):
    def test_summary_and_detail_load_real_examples_from_sample_kb(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            root = Path(temporary_folder)
            recipe_folder = root / "sample_recipe"
            recipe_folder.mkdir()
            db_path = recipe_folder / "kb.sqlite"
            manifest_path = recipe_folder / "manifest.json"
            skip_path = recipe_folder / "embedding_skipped_articles.jsonl"
            evaluation_path = root / "evaluation_metrics.json"

            create_sample_kb(db_path)
            manifest_path.write_text(
                json.dumps(
                    {
                        "recipe_name": "sample_recipe",
                        "embedding_model": "text-embedding-3-small",
                        "chunking_method": "fixed_size",
                        "chunk_size_characters": 2000,
                        "chunk_overlap_characters": 200,
                        "article_count": 2,
                        "chunk_count": 3,
                        "vector_count": 3,
                        "skipped_too_large_article_count": 1,
                        "recipe": {
                            "name": "sample_recipe",
                            "output_folder": str(recipe_folder),
                            "embedding_model": "text-embedding-3-small",
                            "search_distance": "cos",
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            skip_path.write_text(
                json.dumps(
                    {
                        "article_id": "skipped-one",
                        "title": "Long skipped article",
                        "reason": "OpenAI rejected this embedding input because it exceeds the maximum input length",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            evaluation_path.write_text(
                json.dumps(
                    {
                        "recipes": [
                            {
                                "recipe_name": "sample_recipe",
                                "status": "evaluated",
                                "recipe_config": {
                                    "embedding_model": "text-embedding-3-small",
                                    "chunking_method": "fixed_size",
                                    "chunk_size_characters": 2000,
                                    "chunk_overlap_characters": 200,
                                },
                                "sanity_metrics": {
                                    "expected_article_count": 2,
                                    "article_count": 2,
                                    "article_coverage_rate": 1.0,
                                    "chunk_count": 3,
                                    "vector_count": 3,
                                    "skipped_too_large_article_count": 1,
                                },
                                "thesis_metrics": {
                                    "boundary_break_rate": 0.25,
                                    "lead_paragraph_intact_rate": 0.5,
                                },
                                "diagnostic_metrics": {
                                    "duplicate_chunk_rate": 0.0,
                                    "same_article_max_chunk_share": 0.67,
                                },
                                "retrieval_metrics": {
                                    "status": "evaluated",
                                    "context_efficiency": {
                                        "overlap_waste_rate": 0.1,
                                    },
                                },
                            }
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            summary = get_kb_summary(root, evaluation_path)
            detail = get_recipe_detail(root, "sample_recipe", evaluation_path)

        self.assertEqual(summary["recipe_count"], 1)
        self.assertEqual(summary["built_recipe_count"], 1)
        self.assertEqual(summary["recipes"][0]["recipe_name"], "sample_recipe")
        self.assertEqual(summary["recipes"][0]["article_count"], 2)
        self.assertEqual(detail["recipe_name"], "sample_recipe")
        self.assertEqual(detail["metrics"]["sanity_metrics"]["article_count"], 2)
        self.assertEqual(detail["skipped_articles"][0]["article_id"], "skipped-one")
        self.assertEqual(detail["examples"]["longest_chunks"][0]["article_id"], "article-two")
        self.assertEqual(detail["examples"]["articles_by_chunk_count"][0]["article_id"], "article-one")


def create_sample_kb(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            url TEXT,
            published_at TEXT,
            indexed_at TEXT,
            indexed_at_epoch REAL,
            cleaned_at TEXT,
            input_file_path TEXT,
            content_hash TEXT,
            status TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE chunks (
            chunk_rowid INTEGER PRIMARY KEY,
            chunk_id TEXT,
            article_id TEXT,
            chunk_index INTEGER,
            chunk_text TEXT,
            character_start INTEGER,
            character_end INTEGER,
            chunk_hash TEXT
        )
        """
    )
    connection.execute("CREATE TABLE vec1_chunks (rowid INTEGER PRIMARY KEY, vector BLOB)")
    connection.execute(
        """
        CREATE TABLE embedding_batches (
            batch_id TEXT PRIMARY KEY,
            embedding_model TEXT,
            embedding_dimensions INTEGER,
            token_count INTEGER,
            status TEXT,
            error_text TEXT
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO articles (
            article_id, source, title, url, published_at, indexed_at,
            indexed_at_epoch, cleaned_at, input_file_path, content_hash, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "article-one",
                "PUBLICO",
                "First article",
                "https://example.com/one",
                "2026-05-01",
                "2026-05-01T10:00:00+00:00",
                1760000000,
                "",
                "",
                "hash-one",
                "ready",
            ),
            (
                "article-two",
                "EXPRESSO",
                "Second article",
                "https://example.com/two",
                "2026-05-02",
                "2026-05-02T10:00:00+00:00",
                1760100000,
                "",
                "",
                "hash-two",
                "ready",
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO chunks (
            chunk_id, article_id, chunk_index, chunk_text,
            character_start, character_end, chunk_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("one-0", "article-one", 0, "Short tourism demand chunk.", 0, 27, "chunk-hash-1"),
            ("one-1", "article-one", 1, "Another Lisbon hotel demand chunk.", 28, 60, "chunk-hash-2"),
            ("two-0", "article-two", 0, "A much longer Algarve airport capacity and tourism demand chunk.", 0, 62, "chunk-hash-3"),
        ],
    )
    connection.executemany(
        "INSERT INTO vec1_chunks(rowid, vector) VALUES (?, ?)",
        [(1, b"fake"), (2, b"fake"), (3, b"fake")],
    )
    connection.execute(
        """
        INSERT INTO embedding_batches (
            batch_id, embedding_model, embedding_dimensions, token_count, status, error_text
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("batch-one", "text-embedding-3-small", 2, 100, "success", ""),
    )
    connection.commit()
    connection.close()


if __name__ == "__main__":
    unittest.main()
