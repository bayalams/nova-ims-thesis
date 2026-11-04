"""
Tests for the NER metric inspection script.
"""

import json
import tempfile
import unittest
from pathlib import Path

from explorer.scripts.inspect_ner_metric import build_entity_inspection_report
from knowledge_bases.evaluation.entity_metrics import make_entity_metric_config
from knowledge_bases.evaluation.entity_store import create_entity_store_schema
from knowledge_bases.evaluation.entity_store import make_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store
from knowledge_bases.evaluation.entity_store import write_entity_record
from knowledge_bases.storage.sqlite_kb import create_kb_schema
from knowledge_bases.storage.sqlite_kb import insert_article
from knowledge_bases.storage.sqlite_kb import insert_chunk
from knowledge_bases.storage.sqlite_kb import open_kb_database


class ExplorerNerInspectorTests(unittest.TestCase):
    def test_build_entity_inspection_report_reads_cached_entities_and_pair_health(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            clean_folder = temporary_path / "clean"
            output_folder = temporary_path / "kb"
            clean_folder.mkdir()
            output_folder.mkdir()

            article_text = "Lisbon welcomed Turismo de Portugal leaders today."
            article_path = clean_folder / "article-one.json"
            article_path.write_text(
                json.dumps(
                    {
                        "id": "article-one",
                        "is_valid_article": True,
                        "source": "PUBLICO",
                        "title": "Lisbon tourism",
                        "link": "https://example.com/one",
                        "text": article_text,
                        "metadata": {},
                    }
                ),
                encoding="utf-8",
            )

            connection = open_kb_database(output_folder / "kb.sqlite")
            create_kb_schema(connection)
            insert_article(
                connection,
                {
                    "article_id": "article-one",
                    "source": "PUBLICO",
                    "title": "Lisbon tourism",
                    "url": "https://example.com/one",
                    "published_at": "2026-05-01T10:00:00+00:00",
                    "indexed_at": "2026-05-01T12:00:00+00:00",
                    "indexed_at_epoch": 1777636800.0,
                    "cleaned_at": "",
                    "input_file_path": str(article_path),
                    "content_hash": "hash-one",
                    "status": "ready",
                },
            )
            insert_chunk(
                connection,
                {
                    "chunk_id": "article-one_chunk_0",
                    "article_id": "article-one",
                    "chunk_index": 0,
                    "chunk_text": article_text,
                    "character_start": 0,
                    "character_end": len(article_text),
                    "chunk_hash": "chunk-hash-one",
                },
            )
            connection.commit()
            connection.close()

            recipe = {
                "name": "fake_recipe",
                "input_corpus": str(clean_folder),
                "output_folder": str(output_folder),
            }
            config = make_entity_metric_config()
            store_path = temporary_path / "entities.sqlite"
            store_connection = open_entity_store(store_path)
            create_entity_store_schema(store_connection)
            cache_key = make_entity_cache_key(article_text, config, "mps")
            write_entity_record(
                store_connection,
                cache_key,
                "article-one",
                "hash-one",
                article_text,
                config,
                "mps",
                8,
                [
                    {
                        "text": "Lisbon",
                        "normalized_text": "lisbon",
                        "label": "location",
                        "start": 0,
                        "end": 6,
                        "score": 0.98,
                    },
                    {
                        "text": "Turismo de Portugal",
                        "normalized_text": "turismo de portugal",
                        "label": "organization",
                        "start": 16,
                        "end": 35,
                        "score": 0.91,
                    },
                ],
            )
            store_connection.close()

            report = build_entity_inspection_report(
                recipe,
                article_id="article-one",
                store_path=store_path,
                device="mps",
                compute_missing=False,
            )

        self.assertEqual(report["recipe_name"], "fake_recipe")
        self.assertEqual(report["article_count"], 1)
        article_report = report["articles"][0]
        self.assertEqual(article_report["article_id"], "article-one")
        self.assertEqual(article_report["cache_status"], "cached")
        self.assertEqual(article_report["entity_count"], 2)
        self.assertEqual(article_report["entity_counts_by_label"]["location"], 1)
        self.assertEqual(article_report["entity_pair_count"], 1)
        self.assertEqual(article_report["preserved_pair_count"], 1)
        self.assertEqual(article_report["missed_pair_count"], 0)
        self.assertEqual(article_report["pairs"][0]["preserved_in_chunk"], True)
        self.assertEqual(article_report["pairs"][0]["preserving_chunks"][0]["chunk_index"], 0)

    def test_build_entity_inspection_report_can_compute_missing_entities_with_fake_extractor(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            clean_folder = temporary_path / "clean"
            output_folder = temporary_path / "kb"
            clean_folder.mkdir()
            output_folder.mkdir()

            article_text = "Porto welcomed Turismo de Portugal leaders today."
            article_path = clean_folder / "article-two.json"
            article_path.write_text(
                json.dumps(
                    {
                        "id": "article-two",
                        "is_valid_article": True,
                        "source": "PUBLICO",
                        "title": "Porto tourism",
                        "link": "https://example.com/two",
                        "text": article_text,
                        "metadata": {},
                    }
                ),
                encoding="utf-8",
            )

            connection = open_kb_database(output_folder / "kb.sqlite")
            create_kb_schema(connection)
            insert_article(
                connection,
                {
                    "article_id": "article-two",
                    "source": "PUBLICO",
                    "title": "Porto tourism",
                    "url": "https://example.com/two",
                    "published_at": "2026-05-01T10:00:00+00:00",
                    "indexed_at": "2026-05-01T12:00:00+00:00",
                    "indexed_at_epoch": 1777636800.0,
                    "cleaned_at": "",
                    "input_file_path": str(article_path),
                    "content_hash": "hash-two",
                    "status": "ready",
                },
            )
            insert_chunk(
                connection,
                {
                    "chunk_id": "article-two_chunk_0",
                    "article_id": "article-two",
                    "chunk_index": 0,
                    "chunk_text": article_text,
                    "character_start": 0,
                    "character_end": len(article_text),
                    "chunk_hash": "chunk-hash-two",
                },
            )
            connection.commit()
            connection.close()

            calls = []

            def fake_batch_extractor(texts, config, runtime):
                calls.append(list(texts))
                return [
                    [
                        {"text": "Porto", "label": "location", "start": 0, "end": 5, "score": 0.98},
                        {
                            "text": "Turismo de Portugal",
                            "label": "organization",
                            "start": 16,
                            "end": 35,
                            "score": 0.91,
                        },
                    ]
                ]

            recipe = {
                "name": "fake_recipe",
                "input_corpus": str(clean_folder),
                "output_folder": str(output_folder),
            }
            store_path = temporary_path / "entities.sqlite"
            report = build_entity_inspection_report(
                recipe,
                article_id="article-two",
                store_path=store_path,
                device="cpu",
                compute_missing=True,
                batch_extractor_function=fake_batch_extractor,
            )

        self.assertEqual(calls, [[article_text]])
        article_report = report["articles"][0]
        self.assertEqual(article_report["cache_status"], "computed")
        self.assertEqual(article_report["entity_count"], 2)
        self.assertEqual(article_report["preserved_pair_count"], 1)


if __name__ == "__main__":
    unittest.main()
