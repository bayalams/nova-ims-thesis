"""
Tests for shared SQLite NER precompute storage.
"""

import tempfile
import unittest
from pathlib import Path

from knowledge_bases.evaluation.constants import DEFAULT_THESIS_METRIC_CONFIG
from knowledge_bases.evaluation.entity_metrics import normalize_entity_mentions
from knowledge_bases.evaluation.entity_store import create_entity_store_schema
from knowledge_bases.evaluation.entity_store import get_cached_entities
from knowledge_bases.evaluation.entity_store import make_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store
from knowledge_bases.evaluation.entity_store import write_entity_error
from knowledge_bases.evaluation.entity_store import write_entity_record


class KnowledgeBaseEntityStoreTests(unittest.TestCase):
    def test_store_writes_and_reads_ready_entity_records(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = Path(temporary_folder) / "entities.sqlite"
            connection = open_entity_store(db_path)
            create_entity_store_schema(connection)
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)
            entities = normalize_entity_mentions(
                [
                    {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.95},
                    {
                        "text": "Turismo de Portugal",
                        "label": "organization",
                        "start": 16,
                        "end": 35,
                        "score": 0.91,
                    },
                ],
                config["ner_threshold"],
            )
            cache_key = make_entity_cache_key("Article text", config, "mps")

            write_entity_record(
                connection,
                cache_key,
                "article-one",
                "hash-one",
                "Article text",
                config,
                "mps",
                8,
                entities,
            )
            cached_entities = get_cached_entities(connection, cache_key)
            connection.close()

        self.assertEqual([entity["normalized_text"] for entity in cached_entities], ["lisbon", "turismo de portugal"])

    def test_store_rewrites_existing_record_when_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = Path(temporary_folder) / "entities.sqlite"
            connection = open_entity_store(db_path)
            create_entity_store_schema(connection)
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)
            cache_key = make_entity_cache_key("Article text", config, "mps")

            first_entities = normalize_entity_mentions(
                [{"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.95}],
                config["ner_threshold"],
            )
            second_entities = normalize_entity_mentions(
                [{"text": "Porto", "label": "location", "start": 0, "end": 5, "score": 0.95}],
                config["ner_threshold"],
            )

            write_entity_record(
                connection,
                cache_key,
                "article-one",
                "hash-one",
                "Article text",
                config,
                "mps",
                8,
                first_entities,
            )
            write_entity_record(
                connection,
                cache_key,
                "article-one",
                "hash-two",
                "Article text changed",
                config,
                "mps",
                8,
                second_entities,
            )
            cached_entities = get_cached_entities(connection, cache_key)
            connection.close()

        self.assertEqual([entity["normalized_text"] for entity in cached_entities], ["porto"])

    def test_store_records_errors_without_ready_entities(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = Path(temporary_folder) / "entities.sqlite"
            connection = open_entity_store(db_path)
            create_entity_store_schema(connection)
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)
            cache_key = make_entity_cache_key("Article text", config, "mps")

            write_entity_error(
                connection,
                cache_key,
                "article-one",
                "hash-one",
                "Article text",
                config,
                "mps",
                8,
                "example failure",
            )
            cached_entities = get_cached_entities(connection, cache_key)
            row = connection.execute(
                "SELECT status, error_text FROM entity_documents WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            connection.close()

        self.assertIsNone(cached_entities)
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["error_text"], "example failure")


if __name__ == "__main__":
    unittest.main()
