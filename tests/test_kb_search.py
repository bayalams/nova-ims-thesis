"""
Tests for SQLite Vec1 search helpers.
"""

import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from knowledge_bases.retrieval import search_sqlite
from knowledge_bases.retrieval.search_sqlite import fetch_candidate_search_rows
from knowledge_bases.retrieval.search_sqlite import search_ann
from knowledge_bases.retrieval.search_sqlite import search_exact
from knowledge_bases.storage.sqlite_kb import create_kb_schema
from knowledge_bases.storage.sqlite_kb import create_vec1_table
from knowledge_bases.storage.sqlite_kb import find_vec1_extension
from knowledge_bases.storage.sqlite_kb import insert_article
from knowledge_bases.storage.sqlite_kb import insert_chunk
from knowledge_bases.storage.sqlite_kb import insert_vec1_vector
from knowledge_bases.storage.sqlite_kb import load_vec1_extension
from knowledge_bases.storage.sqlite_kb import pack_vector
from knowledge_bases.storage.sqlite_kb import rebuild_vec1_index


def make_test_recipe():
    """
    Create a minimal recipe dictionary for search tests.

    PARAMETERS:
    - None

    RETURNS:
    - Recipe dictionary
    """
    return {
        "name": "test_recipe",
        "search_distance": "l2",
    }


def unpack_one_float(vector_blob):
    """
    Read a one-dimensional Vec1 vector blob.

    PARAMETERS:
    - vector_blob: Packed vector bytes

    RETURNS:
    - The first float from the blob
    """
    return struct.unpack("<f", vector_blob)[0]


def fake_l2_distance(left_blob, right_blob):
    """
    Calculate a simple one-dimensional distance for tests.

    PARAMETERS:
    - left_blob: Packed query vector
    - right_blob: Packed stored vector

    RETURNS:
    - Absolute distance between the two vector values
    """
    return abs(unpack_one_float(left_blob) - unpack_one_float(right_blob))


def create_search_schema(connection, include_indexed_columns=True):
    """
    Create normal SQLite tables that behave like the Vec1 search joins.

    PARAMETERS:
    - connection: sqlite3 connection
    - include_indexed_columns: Whether articles has indexed timestamp columns

    RETURNS:
    - None
    """
    if include_indexed_columns:
        connection.execute(
            """
            CREATE TABLE articles (
                article_id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                url TEXT,
                published_at TEXT,
                indexed_at TEXT,
                indexed_at_epoch REAL
            )
            """
        )
    else:
        connection.execute(
            """
            CREATE TABLE articles (
                article_id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                url TEXT,
                published_at TEXT
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
            chunk_text TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE vec1_chunks (
            rowid INTEGER PRIMARY KEY,
            vector BLOB
        )
        """
    )


def insert_search_article(connection, article_id, indexed_at, indexed_at_epoch, vector_value):
    """
    Insert one article, chunk, and vector row.

    PARAMETERS:
    - connection: sqlite3 connection
    - article_id: Article id
    - indexed_at: RSS indexed timestamp text
    - indexed_at_epoch: RSS indexed timestamp epoch
    - vector_value: One-dimensional vector value

    RETURNS:
    - None
    """
    connection.execute(
        """
        INSERT INTO articles (
            article_id,
            source,
            title,
            url,
            published_at,
            indexed_at,
            indexed_at_epoch
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            "PUBLICO",
            article_id,
            f"https://example.com/{article_id}",
            "2026-05-01T00:00:00+00:00",
            indexed_at,
            indexed_at_epoch,
        ),
    )
    cursor = connection.execute(
        """
        INSERT INTO chunks (
            chunk_id,
            article_id,
            chunk_index,
            chunk_text
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            f"{article_id}_chunk_0",
            article_id,
            0,
            f"Chunk text for {article_id}",
        ),
    )
    connection.execute(
        """
        INSERT INTO vec1_chunks(rowid, vector)
        VALUES (?, ?)
        """,
        (cursor.lastrowid, pack_vector([vector_value])),
    )


def insert_real_search_article(connection, article_id, vector, indexed_at_epoch=1777593600.0):
    """
    Insert one article, chunk, and real Vec1 vector row.

    PARAMETERS:
    - connection: sqlite3 connection
    - article_id: Article id
    - vector: Small vector list
    - indexed_at_epoch: RSS indexed timestamp epoch

    RETURNS:
    - None
    """
    insert_article(
        connection,
        {
            "article_id": article_id,
            "source": "PUBLICO",
            "title": article_id,
            "url": f"https://example.com/{article_id}",
            "published_at": "2026-05-01T00:00:00+00:00",
            "indexed_at": "2026-05-01T00:00:00+00:00",
            "indexed_at_epoch": indexed_at_epoch,
            "cleaned_at": "2026-05-01T00:00:00+00:00",
            "input_file_path": f"{article_id}.json",
            "content_hash": article_id,
            "status": "ready",
        },
    )
    chunk_rowid = insert_chunk(
        connection,
        {
            "chunk_id": f"{article_id}_chunk_0",
            "article_id": article_id,
            "chunk_index": 0,
            "chunk_text": f"Chunk text for {article_id}",
            "character_start": 0,
            "character_end": 10,
            "chunk_hash": f"{article_id}_chunk_hash",
        },
    )
    insert_vec1_vector(connection, chunk_rowid, vector)


class KnowledgeBaseSearchTests(unittest.TestCase):
    def test_ann_search_uses_vec1_candidates_without_reading_ann_cursor_vector(self):
        try:
            extension_path = find_vec1_extension()
        except ValueError:
            self.skipTest("Vec1 extension is not set up")

        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            connection = sqlite3.connect(str(db_path))
            connection.row_factory = sqlite3.Row
            create_kb_schema(connection)
            load_vec1_extension(connection, extension_path)
            create_vec1_table(connection)

            insert_real_search_article(connection, "far", [10.0, 10.0])
            insert_real_search_article(connection, "near", [0.1, 0.1])
            rebuild_vec1_index(connection, workers=1, distance="l2")

            results = search_ann(
                connection,
                make_test_recipe(),
                pack_vector([0.0, 0.0]),
                top_k=2,
            )
            connection.close()

        self.assertEqual([result["article_id"] for result in results], ["near", "far"])

    def test_fetch_candidate_search_rows_reranks_only_ann_candidates(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection)
        insert_search_article(connection, "candidate_far", "2026-05-01T00:00:00+00:00", 100.0, 9.0)
        insert_search_article(connection, "not_candidate_best", "2026-05-01T00:00:00+00:00", 100.0, 0.1)
        insert_search_article(connection, "candidate_near", "2026-05-01T00:00:00+00:00", 100.0, 1.0)
        insert_search_article(connection, "candidate_middle", "2026-05-01T00:00:00+00:00", 100.0, 4.0)

        rows = fetch_candidate_search_rows(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            [1, 3, 4],
            top_k=2,
        )

        self.assertEqual([row["article_id"] for row in rows], ["candidate_near", "candidate_middle"])

    def test_fetch_candidate_search_rows_returns_empty_list_without_candidates(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection)

        rows = fetch_candidate_search_rows(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            [],
            top_k=2,
        )

        self.assertEqual(rows, [])

    def test_fetch_candidate_search_rows_filters_temporal_ann_candidates(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection)
        insert_search_article(connection, "old_far", "2026-05-01T00:00:00+00:00", 100.0, 9.0)
        insert_search_article(connection, "new_near", "2026-05-03T00:00:00+00:00", 300.0, 0.1)
        insert_search_article(connection, "old_near", "2026-05-01T01:00:00+00:00", 120.0, 1.0)

        rows = fetch_candidate_search_rows(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            [1, 2, 3],
            top_k=3,
            indexed_before_epoch=150.0,
        )

        self.assertEqual([row["article_id"] for row in rows], ["old_near", "old_far"])
        self.assertEqual(rows[0]["indexed_at"], "2026-05-01T01:00:00+00:00")
        self.assertEqual(rows[0]["indexed_at_epoch"], 120.0)

    def test_fetch_candidate_search_rows_returns_fewer_temporal_ann_results_when_candidates_filtered(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection)
        insert_search_article(connection, "new_near", "2026-05-03T00:00:00+00:00", 300.0, 0.1)
        insert_search_article(connection, "old_far", "2026-05-01T00:00:00+00:00", 100.0, 9.0)

        rows = fetch_candidate_search_rows(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            [1, 2],
            top_k=2,
            indexed_before_epoch=150.0,
        )

        self.assertEqual([row["article_id"] for row in rows], ["old_far"])

    def test_search_ann_passes_temporal_cutoff_to_candidate_fetch(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        create_search_schema(connection)

        with patch("knowledge_bases.retrieval.search_sqlite.get_ann_candidate_rowids", return_value=[1, 2]) as fake_candidates, \
             patch("knowledge_bases.retrieval.search_sqlite.fetch_candidate_search_rows", return_value=[]) as fake_fetch:
            results = search_ann(
                connection,
                make_test_recipe(),
                pack_vector([0.0]),
                top_k=5,
                indexed_before_epoch=150.0,
            )

        self.assertEqual(results, [])
        fake_candidates.assert_called_once_with(connection, pack_vector([0.0]), 100)
        fake_fetch.assert_called_once_with(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            [1, 2],
            5,
            150.0,
        )

    def test_search_recipe_routes_indexed_before_ann_to_ann_search(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            db_path.write_text("", encoding="utf-8")
            fake_connection = Mock()

            with patch("knowledge_bases.retrieval.search_sqlite.load_recipe", return_value={
                "name": "test_recipe",
                "output_folder": temp_folder,
                "embedding_model": "test-embedding-model",
            }), \
                 patch("knowledge_bases.retrieval.search_sqlite.find_vec1_extension", return_value="vec1.so"), \
                 patch("knowledge_bases.retrieval.search_sqlite.open_kb_database", return_value=fake_connection), \
                 patch("knowledge_bases.retrieval.search_sqlite.load_vec1_extension"), \
                 patch("knowledge_bases.retrieval.search_sqlite.ensure_indexed_before_supported"), \
                 patch("knowledge_bases.retrieval.search_sqlite.build_embedding_client", return_value=object()), \
                 patch("knowledge_bases.retrieval.search_sqlite.create_embedding_batch", return_value={"vectors": [[0.0]]}), \
                 patch("knowledge_bases.retrieval.search_sqlite.search_ann", return_value=[]) as fake_ann, \
                 patch("knowledge_bases.retrieval.search_sqlite.search_exact", return_value=[]) as fake_exact, \
                 patch("knowledge_bases.retrieval.search_sqlite.print_search_results"):
                results = search_sqlite.search_recipe(
                    "test_recipe",
                    "tourism in Portugal",
                    top_k=5,
                    search_mode="ann",
                    indexed_before="20260501_000000",
                )

        self.assertEqual(results, [])
        self.assertEqual(fake_ann.call_count, 1)
        self.assertEqual(fake_ann.call_args.args[0], fake_connection)
        self.assertEqual(fake_ann.call_args.args[3], 5)
        self.assertIsNotNone(fake_ann.call_args.args[4])
        self.assertEqual(fake_exact.call_count, 0)
        fake_connection.close.assert_called_once()

    def test_search_recipe_keeps_exact_mode_when_indexed_before_is_exact(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            db_path.write_text("", encoding="utf-8")
            fake_connection = Mock()

            with patch("knowledge_bases.retrieval.search_sqlite.load_recipe", return_value={
                "name": "test_recipe",
                "output_folder": temp_folder,
                "embedding_model": "test-embedding-model",
            }), \
                 patch("knowledge_bases.retrieval.search_sqlite.find_vec1_extension", return_value="vec1.so"), \
                 patch("knowledge_bases.retrieval.search_sqlite.open_kb_database", return_value=fake_connection), \
                 patch("knowledge_bases.retrieval.search_sqlite.load_vec1_extension"), \
                 patch("knowledge_bases.retrieval.search_sqlite.ensure_indexed_before_supported"), \
                 patch("knowledge_bases.retrieval.search_sqlite.build_embedding_client", return_value=object()), \
                 patch("knowledge_bases.retrieval.search_sqlite.create_embedding_batch", return_value={"vectors": [[0.0]]}), \
                 patch("knowledge_bases.retrieval.search_sqlite.search_ann", return_value=[]) as fake_ann, \
                 patch("knowledge_bases.retrieval.search_sqlite.search_exact", return_value=[]) as fake_exact, \
                 patch("knowledge_bases.retrieval.search_sqlite.print_search_results"):
                results = search_sqlite.search_recipe(
                    "test_recipe",
                    "tourism in Portugal",
                    top_k=5,
                    search_mode="exact",
                    indexed_before="20260501_000000",
                )

        self.assertEqual(results, [])
        self.assertEqual(fake_ann.call_count, 0)
        self.assertEqual(fake_exact.call_count, 1)
        self.assertEqual(fake_exact.call_args.args[0], fake_connection)
        self.assertEqual(fake_exact.call_args.args[3], 5)
        self.assertIsNotNone(fake_exact.call_args.args[4])
        fake_connection.close.assert_called_once()

    def test_exact_search_uses_rowid_lookup_vectors_after_flat_rebuild(self):
        try:
            extension_path = find_vec1_extension()
        except ValueError:
            self.skipTest("Vec1 extension is not set up")

        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            connection = sqlite3.connect(str(db_path))
            connection.row_factory = sqlite3.Row
            create_kb_schema(connection)
            load_vec1_extension(connection, extension_path)
            create_vec1_table(connection)

            insert_real_search_article(connection, "far", [10.0, 10.0])
            insert_real_search_article(connection, "near", [0.1, 0.1])
            rebuild_vec1_index(connection, workers=1, distance="l2")
            connection.close()

            connection = sqlite3.connect(str(db_path))
            connection.row_factory = sqlite3.Row
            load_vec1_extension(connection, extension_path)
            results = search_exact(
                connection,
                make_test_recipe(),
                pack_vector([0.0, 0.0]),
                top_k=2,
            )
            connection.close()

        self.assertEqual([result["article_id"] for result in results], ["near", "far"])

    def test_bounded_exact_search_uses_rowid_lookup_vectors_after_flat_rebuild(self):
        try:
            extension_path = find_vec1_extension()
        except ValueError:
            self.skipTest("Vec1 extension is not set up")

        with tempfile.TemporaryDirectory() as temp_folder:
            db_path = Path(temp_folder) / "kb.sqlite"
            connection = sqlite3.connect(str(db_path))
            connection.row_factory = sqlite3.Row
            create_kb_schema(connection)
            load_vec1_extension(connection, extension_path)
            create_vec1_table(connection)

            insert_real_search_article(connection, "old_far", [10.0, 10.0], indexed_at_epoch=100.0)
            insert_real_search_article(connection, "new_near", [0.1, 0.1], indexed_at_epoch=300.0)
            rebuild_vec1_index(connection, workers=1, distance="l2")
            connection.close()

            connection = sqlite3.connect(str(db_path))
            connection.row_factory = sqlite3.Row
            load_vec1_extension(connection, extension_path)
            results = search_exact(
                connection,
                make_test_recipe(),
                pack_vector([0.0, 0.0]),
                top_k=2,
                indexed_before_epoch=150.0,
            )
            connection.close()

        self.assertEqual([result["article_id"] for result in results], ["old_far"])

    def test_exact_search_with_indexed_before_excludes_newer_better_vector(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection)
        insert_search_article(connection, "older", "2026-05-01T00:00:00+00:00", 100.0, 10.0)
        insert_search_article(connection, "newer", "2026-05-03T00:00:00+00:00", 300.0, 0.1)

        results = search_exact(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            top_k=2,
            indexed_before_epoch=150.0,
        )

        self.assertEqual([result["article_id"] for result in results], ["older"])
        self.assertEqual(results[0]["indexed_at"], "2026-05-01T00:00:00+00:00")
        self.assertEqual(results[0]["indexed_at_epoch"], 100.0)

    def test_exact_search_without_indexed_before_keeps_unbounded_behavior(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection)
        insert_search_article(connection, "older", "2026-05-01T00:00:00+00:00", 100.0, 10.0)
        insert_search_article(connection, "newer", "2026-05-03T00:00:00+00:00", 300.0, 0.1)

        results = search_exact(
            connection,
            make_test_recipe(),
            pack_vector([0.0]),
            top_k=1,
        )

        self.assertEqual([result["article_id"] for result in results], ["newer"])

    def test_indexed_before_fails_clearly_on_old_schema(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.create_function("vec1_l2_distance", 2, fake_l2_distance)
        create_search_schema(connection, include_indexed_columns=False)

        with self.assertRaisesRegex(ValueError, "rebuild the KB before using --indexed-before"):
            search_exact(
                connection,
                make_test_recipe(),
                pack_vector([0.0]),
                top_k=1,
                indexed_before_epoch=150.0,
            )


if __name__ == "__main__":
    unittest.main()
