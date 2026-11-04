"""
Tests for knowledge-base evaluation metrics.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_bases.evaluation.articles import load_clean_articles_for_evaluation
from knowledge_bases.evaluation.entity_metrics import make_entity_metric_config
from knowledge_bases.evaluation.entity_store import create_entity_store_schema
from knowledge_bases.evaluation.entity_store import make_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store
from knowledge_bases.evaluation.entity_store import write_entity_record
from knowledge_bases.evaluation.evaluate_kbs import evaluate_recipe
from knowledge_bases.evaluation.evaluate_kbs import evaluate_recipes
from knowledge_bases.evaluation.evaluate_kbs import make_comparison_table_rows
from knowledge_bases.evaluation.evaluate_kbs import write_comparison_tables
from knowledge_bases.evaluation.retrieval_metrics import select_retrieval_queries
from knowledge_bases.storage.sqlite_kb import create_kb_schema
from knowledge_bases.storage.sqlite_kb import insert_article
from knowledge_bases.storage.sqlite_kb import insert_chunk
from knowledge_bases.storage.sqlite_kb import insert_embedding_batch
from knowledge_bases.storage.sqlite_kb import open_kb_database


class KnowledgeBaseEvaluationTests(unittest.TestCase):
    def test_evaluate_recipe_reports_sanity_and_deterministic_thesis_metrics(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            clean_folder = temporary_path / "clean_articles"
            output_folder = temporary_path / "kb_output"
            clean_folder.mkdir(parents=True)
            output_folder.mkdir(parents=True)

            article_one_text = "Lead paragraph one.\n\nSecond paragraph has Hotel Lisbon demand rising."
            article_two_text = "Another lead.\n\nSubscribe to our newsletter for updates."
            article_three_text = "Third lead.\n\nThis article is present in the corpus but not indexed."

            article_one_path = clean_folder / "article-one.json"
            article_two_path = clean_folder / "article-two.json"
            article_three_path = clean_folder / "article-three.json"

            self.write_clean_article(
                article_one_path,
                "article-one",
                "PUBLICO",
                "Hotel demand rises",
                "https://example.com/one",
                article_one_text,
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
            )
            self.write_clean_article(
                article_two_path,
                "article-two",
                "",
                "",
                "",
                article_two_text,
                "",
                "",
            )
            self.write_clean_article(
                article_three_path,
                "article-three",
                "OBSERVADOR",
                "Not indexed",
                "https://example.com/three",
                article_three_text,
                "2026-05-02T10:00:00+00:00",
                "2026-05-02T12:00:00+00:00",
            )

            db_path = output_folder / "kb.sqlite"
            connection = open_kb_database(db_path)
            create_kb_schema(connection)
            connection.execute("CREATE TABLE vec1_chunks(rowid INTEGER PRIMARY KEY, vector BLOB)")

            insert_article(
                connection,
                {
                    "article_id": "article-one",
                    "source": "PUBLICO",
                    "title": "Hotel demand rises",
                    "url": "https://example.com/one",
                    "published_at": "2026-05-01T10:00:00+00:00",
                    "indexed_at": "2026-05-01T12:00:00+00:00",
                    "indexed_at_epoch": 1777636800.0,
                    "cleaned_at": "",
                    "input_file_path": str(article_one_path),
                    "content_hash": "hash-one",
                    "status": "ready",
                },
            )
            insert_article(
                connection,
                {
                    "article_id": "article-two",
                    "source": "",
                    "title": "",
                    "url": "",
                    "published_at": "",
                    "indexed_at": "",
                    "indexed_at_epoch": None,
                    "cleaned_at": "",
                    "input_file_path": str(article_two_path),
                    "content_hash": "hash-two",
                    "status": "ready",
                },
            )

            lisbon_start = article_one_text.index("Lisbon")
            first_chunk_text = article_one_text[: lisbon_start + 1]
            second_chunk_text = article_one_text[lisbon_start + 1 :]
            chunk_records = [
                {
                    "chunk_id": "article-one_chunk_0",
                    "article_id": "article-one",
                    "chunk_index": 0,
                    "chunk_text": first_chunk_text,
                    "character_start": 0,
                    "character_end": lisbon_start + 1,
                    "chunk_hash": "chunk-hash-one",
                },
                {
                    "chunk_id": "article-one_chunk_1",
                    "article_id": "article-one",
                    "chunk_index": 1,
                    "chunk_text": second_chunk_text,
                    "character_start": lisbon_start + 1,
                    "character_end": len(article_one_text),
                    "chunk_hash": "chunk-hash-two",
                },
                {
                    "chunk_id": "article-two_chunk_0",
                    "article_id": "article-two",
                    "chunk_index": 0,
                    "chunk_text": article_two_text,
                    "character_start": 0,
                    "character_end": len(article_two_text),
                    "chunk_hash": "chunk-hash-three",
                },
            ]

            for chunk_record in chunk_records:
                chunk_rowid = insert_chunk(connection, chunk_record)
                connection.execute(
                    "INSERT INTO vec1_chunks(rowid, vector) VALUES (?, ?)",
                    (chunk_rowid, b"fake-vector"),
                )

            insert_embedding_batch(
                connection,
                {
                    "batch_id": "batch-ok",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_dimensions": 1536,
                    "token_count": 100,
                    "status": "success",
                    "error_text": "",
                },
            )
            insert_embedding_batch(
                connection,
                {
                    "batch_id": "batch-failed",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_dimensions": 1536,
                    "token_count": 20,
                    "status": "failed",
                    "error_text": "example failure",
                },
            )
            connection.commit()
            connection.close()

            manifest = {
                "recipe_name": "fake_recipe",
                "articles_loaded": 3,
                "articles_after_filters": 3,
                "article_count": 2,
                "chunk_count": 3,
                "vector_count": 3,
                "skipped_too_large_article_count": 1,
                "build_time_seconds": 12.5,
            }
            (output_folder / "manifest.json").write_text(
                json.dumps(manifest, indent=2),
                encoding="utf-8",
            )

            recipe = {
                "name": "fake_recipe",
                "input_corpus": str(clean_folder),
                "output_folder": str(output_folder),
            }

            entity_metric_config = make_entity_metric_config()
            entity_metric_config["ner_model"] = "test-model-" + temporary_path.name
            entity_cache_path = temporary_path / "entity_cache.jsonl"
            entity_mentions_path = temporary_path / "entity_mentions.jsonl"
            entity_extractor_calls = []

            def fake_entity_extractor(text, config, runtime):
                entity_extractor_calls.append(text)
                if "Hotel Lisbon" in text:
                    return [
                        {"text": "Hotel", "label": "facility", "start": 35, "end": 40, "score": 0.9},
                        {"text": "Lisbon", "label": "location", "start": 41, "end": 47, "score": 0.9},
                    ]

                return [
                    {"text": "newsletter", "label": "product", "start": 30, "end": 40, "score": 0.9},
                    {"text": "updates", "label": "event", "start": 45, "end": 52, "score": 0.9},
                ]

            metrics = evaluate_recipe(
                recipe,
                entity_metric_config=entity_metric_config,
                entity_extractor_function=fake_entity_extractor,
                entity_cache_path=entity_cache_path,
                entity_mentions_path=entity_mentions_path,
            )

        sanity = metrics["sanity_metrics"]
        thesis = metrics["thesis_metrics"]
        diagnostics = metrics["diagnostic_metrics"]

        chunk_lengths = [len(first_chunk_text), len(second_chunk_text), len(article_two_text)]

        self.assertEqual(metrics["recipe_name"], "fake_recipe")
        self.assertEqual(metrics["status"], "evaluated")
        self.assertEqual(metrics["retrieval_metrics"]["status"], "not_requested")
        self.assertEqual(sanity["input_clean_article_count"], 3)
        self.assertEqual(sanity["expected_article_count"], 3)
        self.assertEqual(sanity["article_count"], 2)
        self.assertAlmostEqual(sanity["article_coverage_rate"], 2 / 3)
        self.assertEqual(sanity["chunk_count"], 3)
        self.assertEqual(sanity["vector_count"], 3)
        self.assertEqual(sanity["chunk_size_characters"]["min"], min(chunk_lengths))
        self.assertEqual(sanity["chunk_size_characters"]["max"], max(chunk_lengths))
        self.assertAlmostEqual(sanity["chunk_size_characters"]["average"], sum(chunk_lengths) / 3)
        self.assertEqual(sanity["chunk_size_characters"]["median"], sorted(chunk_lengths)[1])
        self.assertAlmostEqual(sanity["chunks_per_article"]["average"], 1.5)
        self.assertEqual(sanity["chunks_per_article"]["max"], 2)
        self.assertAlmostEqual(sanity["metadata_missing_rates"]["any_required"], 0.5)
        self.assertAlmostEqual(sanity["metadata_missing_rates"]["source"], 0.5)
        self.assertAlmostEqual(sanity["metadata_missing_rates"]["indexed_at"], 0.5)
        self.assertEqual(sanity["embedding_batch_count"], 2)
        self.assertEqual(sanity["failed_embedding_batch_count"], 1)
        self.assertAlmostEqual(sanity["embedding_failure_rate"], 0.5)
        self.assertGreater(sanity["db_size_bytes"], 0)
        self.assertEqual(sanity["build_time_seconds"], 12.5)
        self.assertEqual(sanity["failed_to_index_article_count"], 1)
        self.assertIsNone(sanity["query_latency_ms"])

        self.assertAlmostEqual(thesis["article_reconstruction_accuracy"], 1.0)
        self.assertAlmostEqual(thesis["lead_paragraph_intact_rate"], 1.0)
        self.assertAlmostEqual(thesis["boundary_break_rate"], 2 / 3)
        self.assertAlmostEqual(thesis["boilerplate_contamination_rate"], 1 / 3)
        self.assertIsNone(thesis["story_level_top_k_diversity"])
        self.assertEqual(metrics["pending_metrics"], [])
        self.assertIn("thesis_metric_config", metrics)
        self.assertIn("thesis_metric_errors", metrics)
        self.assertIn("thesis_metric_details", metrics)
        self.assertIn("entity_metric_artifacts", metrics)
        self.assertEqual(metrics["entity_metric_artifacts"]["cache_path"], str(entity_cache_path))
        self.assertEqual(metrics["entity_metric_artifacts"]["mentions_path"], str(entity_mentions_path))
        self.assertEqual(len(entity_extractor_calls), 2)
        self.assertAlmostEqual(thesis["entity_pair_preservation_rate"], 0.5)
        self.assertEqual(
            metrics["thesis_metric_details"]["entity_pair_preservation"]["source_entity_pair_count"],
            2,
        )
        self.assertEqual(
            metrics["thesis_metric_details"]["entity_pair_preservation"]["preserved_entity_pair_count"],
            1,
        )

        self.assertAlmostEqual(diagnostics["duplicate_chunk_rate"], 0.0)
        self.assertAlmostEqual(diagnostics["same_article_max_chunk_share"], 2 / 3)

    def test_clean_article_cache_loads_title_and_summary_for_retrieval_queries(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            clean_folder = Path(temporary_folder) / "clean_articles"
            clean_folder.mkdir(parents=True)
            self.write_clean_article(
                clean_folder / "article-one.json",
                "article-one",
                "PUBLICO",
                "Clean title",
                "https://example.com/one",
                "Article text",
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
                "Clean summary",
            )

            clean_articles = load_clean_articles_for_evaluation(clean_folder)

        clean_record = clean_articles["articles_by_id"]["article-one"]
        queries = select_retrieval_queries(
            [
                {
                    "article_id": "article-one",
                    "title": "Database title",
                }
            ],
            clean_articles,
            10,
        )

        self.assertEqual(clean_record["title"], "Clean title")
        self.assertEqual(clean_record["summary"], "Clean summary")
        self.assertEqual(queries[0]["query_type"], "title")
        self.assertEqual(queries[0]["query_text"], "Clean title")
        self.assertEqual(queries[1]["query_type"], "summary")
        self.assertEqual(queries[1]["query_text"], "Clean summary")

    def test_blank_summary_is_skipped_and_blank_clean_title_falls_back_to_db_title(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            clean_folder = Path(temporary_folder) / "clean_articles"
            clean_folder.mkdir(parents=True)
            self.write_clean_article(
                clean_folder / "article-one.json",
                "article-one",
                "PUBLICO",
                "",
                "https://example.com/one",
                "Article text",
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
                "   ",
            )

            clean_articles = load_clean_articles_for_evaluation(clean_folder)

        queries = select_retrieval_queries(
            [
                {
                    "article_id": "article-one",
                    "title": "Database title",
                }
            ],
            clean_articles,
            10,
        )

        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0]["query_type"], "title")
        self.assertEqual(queries[0]["query_text"], "Database title")

    def test_evaluate_recipe_uses_precomputed_sqlite_entities(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            clean_folder = temporary_path / "clean_articles"
            output_folder = temporary_path / "kb_output"
            clean_folder.mkdir(parents=True)
            output_folder.mkdir(parents=True)

            article_text = "Lisbon welcomed Turismo de Portugal leaders."
            article_path = clean_folder / "article-one.json"
            self.write_clean_article(
                article_path,
                "article-one",
                "PUBLICO",
                "Lisbon tourism",
                "https://example.com/one",
                article_text,
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
            )

            db_path = output_folder / "kb.sqlite"
            connection = open_kb_database(db_path)
            create_kb_schema(connection)
            self.insert_minimal_article_and_chunk(
                connection,
                article_path,
                "article-one",
                "PUBLICO",
                "Lisbon tourism",
                "2026-05-01T10:00:00+00:00",
            )
            connection.execute("UPDATE chunks SET chunk_text = ? WHERE article_id = ?", (article_text, "article-one"))
            connection.commit()
            connection.close()

            manifest = {
                "recipe_name": "fake_recipe",
                "articles_loaded": 1,
                "articles_after_filters": 1,
                "article_count": 1,
                "chunk_count": 1,
                "vector_count": 0,
                "build_time_seconds": 1.5,
            }
            (output_folder / "manifest.json").write_text(
                json.dumps(manifest, indent=2),
                encoding="utf-8",
            )

            recipe = {
                "name": "fake_recipe",
                "input_corpus": str(clean_folder),
                "output_folder": str(output_folder),
            }
            config = make_entity_metric_config()
            store_path = temporary_path / "entities.sqlite"
            store = open_entity_store(store_path)
            create_entity_store_schema(store)
            cache_key = make_entity_cache_key(article_text, config, "mps")
            write_entity_record(
                store,
                cache_key,
                "article-one",
                "hash-article-one",
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
                        "score": 0.95,
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
            store.close()

            with patch(
                "knowledge_bases.evaluation.entity_metrics.extract_entity_batches_with_gliner",
                side_effect=AssertionError("cached entity should be reused"),
            ):
                metrics = evaluate_recipe(
                    recipe,
                    entity_metric_config=config,
                    entity_store_path=store_path,
                    entity_device="mps",
                )

        self.assertAlmostEqual(metrics["thesis_metrics"]["entity_pair_preservation_rate"], 1.0)
        self.assertNotIn("entity_pair_preservation_rate", metrics["thesis_metric_errors"])
        details = metrics["thesis_metric_details"]["entity_pair_preservation"]
        self.assertEqual(details["cached_entity_count"], 1)
        self.assertEqual(details["computed_entity_count"], 0)

    def test_evaluate_recipe_computes_missing_entities_only_for_sampled_articles(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            clean_folder = temporary_path / "clean_articles"
            output_folder = temporary_path / "kb_output"
            clean_folder.mkdir(parents=True)
            output_folder.mkdir(parents=True)

            article_one_text = "Lisbon welcomed Turismo de Portugal leaders."
            article_two_text = "Porto welcomed Turismo de Portugal leaders."
            article_three_text = "Algarve welcomed Turismo de Portugal leaders."
            article_one_path = clean_folder / "article-one.json"
            article_two_path = clean_folder / "article-two.json"
            article_three_path = clean_folder / "article-three.json"
            self.write_clean_article(
                article_one_path,
                "article-one",
                "PUBLICO",
                "Lisbon tourism",
                "https://example.com/one",
                article_one_text,
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
            )
            self.write_clean_article(
                article_two_path,
                "article-two",
                "PUBLICO",
                "Porto tourism",
                "https://example.com/two",
                article_two_text,
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
            )
            self.write_clean_article(
                article_three_path,
                "article-three",
                "PUBLICO",
                "Algarve tourism",
                "https://example.com/three",
                article_three_text,
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
            )

            db_path = output_folder / "kb.sqlite"
            connection = open_kb_database(db_path)
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
                    "input_file_path": str(article_one_path),
                    "content_hash": "hash-one",
                    "status": "ready",
                },
            )
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
                    "input_file_path": str(article_two_path),
                    "content_hash": "hash-two",
                    "status": "ready",
                },
            )
            insert_article(
                connection,
                {
                    "article_id": "article-three",
                    "source": "PUBLICO",
                    "title": "Algarve tourism",
                    "url": "https://example.com/three",
                    "published_at": "2026-05-01T10:00:00+00:00",
                    "indexed_at": "2026-05-01T12:00:00+00:00",
                    "indexed_at_epoch": 1777636800.0,
                    "cleaned_at": "",
                    "input_file_path": str(article_three_path),
                    "content_hash": "hash-three",
                    "status": "ready",
                },
            )
            insert_chunk(
                connection,
                {
                    "chunk_id": "article-one_chunk_0",
                    "article_id": "article-one",
                    "chunk_index": 0,
                    "chunk_text": article_one_text,
                    "character_start": 0,
                    "character_end": len(article_one_text),
                    "chunk_hash": "chunk-hash-one",
                },
            )
            insert_chunk(
                connection,
                {
                    "chunk_id": "article-two_chunk_0",
                    "article_id": "article-two",
                    "chunk_index": 0,
                    "chunk_text": article_two_text,
                    "character_start": 0,
                    "character_end": len(article_two_text),
                    "chunk_hash": "chunk-hash-two",
                },
            )
            insert_chunk(
                connection,
                {
                    "chunk_id": "article-three_chunk_0",
                    "article_id": "article-three",
                    "chunk_index": 0,
                    "chunk_text": article_three_text,
                    "character_start": 0,
                    "character_end": len(article_three_text),
                    "chunk_hash": "chunk-hash-three",
                },
            )
            connection.commit()
            connection.close()
            (output_folder / "manifest.json").write_text(
                json.dumps({"recipe_name": "fake_recipe", "article_count": 3, "chunk_count": 3, "vector_count": 0}),
                encoding="utf-8",
            )

            recipe = {
                "name": "fake_recipe",
                "input_corpus": str(clean_folder),
                "output_folder": str(output_folder),
            }
            store_path = temporary_path / "entities.sqlite"
            calls = []

            def fake_batch_extractor(texts, config, runtime):
                calls.append(list(texts))
                results = []
                for text in texts:
                    if "Lisbon" in text:
                        city_text = "Lisbon"
                    elif "Algarve" in text:
                        city_text = "Algarve"
                    else:
                        city_text = "Porto"
                    results.append(
                        [
                            {"text": city_text, "label": "location", "start": 0, "end": len(city_text), "score": 0.95},
                            {
                                "text": "Turismo de Portugal",
                                "label": "organization",
                                "start": 16,
                                "end": 35,
                                "score": 0.95,
                            },
                        ]
                    )
                return results

            with patch(
                "knowledge_bases.evaluation.entity_metrics.extract_entity_batches_with_gliner",
                side_effect=fake_batch_extractor,
                create=True,
            ):
                metrics = evaluate_recipe(
                    recipe,
                    entity_metric_config=make_entity_metric_config(),
                    entity_store_path=store_path,
                    entity_device="mps",
                    entity_sample_size=2,
                )

            store = open_entity_store(store_path)
            stored_document_count = store.execute("SELECT count(*) FROM entity_documents").fetchone()[0]
            store.close()

        self.assertAlmostEqual(metrics["thesis_metrics"]["entity_pair_preservation_rate"], 1.0)
        self.assertNotIn("entity_pair_preservation_rate", metrics["thesis_metric_errors"])
        self.assertEqual(calls, [[article_one_text, article_three_text]])
        self.assertEqual(stored_document_count, 2)
        details = metrics["thesis_metric_details"]["entity_pair_preservation"]
        self.assertEqual(details["sample_size"], 2)
        self.assertEqual(details["sampled_article_count"], 2)
        self.assertEqual(details["checked_article_count"], 2)
        self.assertEqual(details["computed_entity_count"], 2)
        self.assertEqual(details["cached_entity_count"], 0)
        self.assertEqual(details["missing_or_error_entity_count"], 0)
        self.assertGreaterEqual(details["estimated_window_count"], 1)

    def test_evaluate_recipe_runs_injected_retrieval_metrics_and_flattens_table_fields(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            clean_folder = temporary_path / "clean_articles"
            output_folder = temporary_path / "kb_output"
            clean_folder.mkdir(parents=True)
            output_folder.mkdir(parents=True)

            self.write_clean_article(
                clean_folder / "article-one.json",
                "article-one",
                "PUBLICO",
                "Hotel demand rises",
                "https://example.com/one",
                "Article one text.",
                "2026-05-01T10:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
                "Hotels in Lisbon are seeing stronger demand.",
            )
            self.write_clean_article(
                clean_folder / "article-two.json",
                "article-two",
                "OBSERVADOR",
                "Other article",
                "https://example.com/two",
                "Article two text.",
                "2026-05-02T10:00:00+00:00",
                "2026-05-02T12:00:00+00:00",
                "Different tourism story.",
            )

            db_path = output_folder / "kb.sqlite"
            connection = open_kb_database(db_path)
            create_kb_schema(connection)
            self.insert_minimal_article_and_chunk(
                connection,
                clean_folder / "article-one.json",
                "article-one",
                "PUBLICO",
                "Hotel demand rises",
                "2026-05-01T10:00:00+00:00",
            )
            self.insert_minimal_article_and_chunk(
                connection,
                clean_folder / "article-two.json",
                "article-two",
                "OBSERVADOR",
                "Other article",
                "2026-05-02T10:00:00+00:00",
            )
            connection.commit()
            connection.close()

            manifest = {
                "recipe_name": "fake_recipe",
                "articles_loaded": 2,
                "articles_after_filters": 2,
                "article_count": 2,
                "chunk_count": 2,
                "vector_count": 2,
                "build_time_seconds": 1.5,
            }
            (output_folder / "manifest.json").write_text(
                json.dumps(manifest, indent=2),
                encoding="utf-8",
            )

            recipe = {
                "name": "fake_recipe",
                "input_corpus": str(clean_folder),
                "output_folder": str(output_folder),
                "embedding_model": "text-embedding-3-small",
                "chunking_method": "fixed",
                "chunk_size_characters": 2000,
                "chunk_overlap_characters": 200,
            }

            def fake_search(query, top_k, search_mode):
                self.assertEqual(top_k, 10)
                self.assertEqual(search_mode, "exact")

                if query["query_type"] == "title":
                    return [
                        self.make_retrieval_result(
                            "article-one",
                            0,
                            "Article one title result.",
                            "PUBLICO",
                            "2026-05-01T10:00:00+00:00",
                            0.10,
                        )
                    ]

                return [
                    self.make_retrieval_result(
                        "article-two",
                        0,
                        "Article two distracting result.",
                        "OBSERVADOR",
                        "2026-05-02T10:00:00+00:00",
                        0.25,
                    ),
                    self.make_retrieval_result(
                        "article-one",
                        0,
                        "Article one summary result.",
                        "PUBLICO",
                        "2026-05-01T10:00:00+00:00",
                        0.12,
                    ),
                ]

            entity_metric_config = make_entity_metric_config()
            entity_metric_config["ner_model"] = "test-retrieval-model-" + temporary_path.name
            entity_cache_path = temporary_path / "retrieval_entity_cache.jsonl"
            entity_mentions_path = temporary_path / "retrieval_entity_mentions.jsonl"
            entity_extractor_calls = []

            def fake_entity_extractor(text, config, runtime):
                entity_extractor_calls.append(text)
                return []

            metrics = evaluate_recipe(
                recipe,
                retrieval_options={
                    "enabled": True,
                    "sample_size": 1,
                    "top_k": 10,
                    "search_mode": "exact",
                },
                retrieval_search_function=fake_search,
                entity_metric_config=entity_metric_config,
                entity_extractor_function=fake_entity_extractor,
                entity_cache_path=entity_cache_path,
                entity_mentions_path=entity_mentions_path,
            )

        retrieval_metrics = metrics["retrieval_metrics"]
        rows = make_comparison_table_rows({"recipes": [metrics]})

        self.assertEqual(retrieval_metrics["status"], "evaluated")
        self.assertEqual(retrieval_metrics["config"]["query_count"], 2)
        self.assertAlmostEqual(retrieval_metrics["self_retrieval"]["title_mrr"], 1.0)
        self.assertAlmostEqual(retrieval_metrics["self_retrieval"]["summary_mrr"], 0.5)
        self.assertAlmostEqual(retrieval_metrics["self_retrieval"]["combined_top_5_rate"], 1.0)
        self.assertAlmostEqual(rows[0]["title_self_retrieval_mrr"], 1.0)
        self.assertAlmostEqual(rows[0]["summary_self_retrieval_mrr"], 0.5)
        self.assertAlmostEqual(rows[0]["combined_self_retrieval_top_5_rate"], 1.0)
        self.assertAlmostEqual(rows[0]["unique_articles_top_10"], 1.5)
        self.assertAlmostEqual(rows[0]["max_same_article_share"], 0.75)
        self.assertAlmostEqual(rows[0]["overlap_waste_rate"], 0.0)
        self.assertAlmostEqual(metrics["thesis_metrics"]["article_self_retrieval_top_5_rate"], 1.0)
        self.assertIsNotNone(metrics["thesis_metrics"]["story_level_top_k_diversity"])
        self.assertIsNotNone(metrics["thesis_metrics"]["hard_negative_separation_margin"])
        self.assertIsNotNone(metrics["thesis_metrics"]["retrieval_hubness_rate"])
        self.assertEqual(len(entity_extractor_calls), 2)

    def test_evaluate_recipes_error_report_keeps_thesis_metric_shape(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            output_path = temporary_path / "evaluation_report.json"
            entity_cache_path = temporary_path / "error_entity_cache.jsonl"
            entity_mentions_path = temporary_path / "error_entity_mentions.jsonl"

            report = evaluate_recipes(
                ["unknown_recipe_for_shape_test"],
                output_path=output_path,
                retrieval_metrics=True,
                entity_cache_path=entity_cache_path,
                entity_mentions_path=entity_mentions_path,
            )

        recipe_report = report["recipes"][0]

        self.assertEqual(recipe_report["recipe_name"], "unknown_recipe_for_shape_test")
        self.assertEqual(recipe_report["status"], "error")
        self.assertIn("thesis_metrics", recipe_report)
        self.assertIn("thesis_metric_config", recipe_report)
        self.assertIn("thesis_metric_errors", recipe_report)
        self.assertIn("thesis_metric_details", recipe_report)
        self.assertIn("entity_metric_artifacts", recipe_report)
        self.assertEqual(recipe_report["entity_metric_artifacts"]["cache_path"], str(entity_cache_path))
        self.assertEqual(recipe_report["entity_metric_artifacts"]["mentions_path"], str(entity_mentions_path))
        self.assertIsNone(recipe_report["thesis_metrics"]["entity_pair_preservation_rate"])
        self.assertIsNone(recipe_report["thesis_metrics"]["article_self_retrieval_top_5_rate"])
        self.assertEqual(recipe_report["retrieval_metrics"]["status"], "error")

    def test_comparison_table_rows_flatten_core_metrics(self):
        report = {
            "recipes": [
                {
                    "recipe_name": "fake_recipe",
                    "status": "evaluated",
                    "recipe_config": {
                        "embedding_model": "text-embedding-3-small",
                        "chunking_method": "fixed",
                        "chunk_size_characters": 2000,
                        "chunk_overlap_characters": 200,
                    },
                    "sanity_metrics": {
                        "expected_article_count": 3,
                        "article_count": 2,
                        "article_coverage_rate": 2 / 3,
                        "chunk_count": 3,
                        "vector_count": 3,
                        "chunk_size_characters": {
                            "average": 1000.5,
                            "median": 900,
                        },
                        "chunks_per_article": {
                            "average": 1.5,
                        },
                        "metadata_missing_rates": {
                            "any_required": 0.5,
                        },
                        "embedding_failure_rate": 0.25,
                        "db_size_bytes": 1048576,
                        "build_time_seconds": 12.5,
                        "query_latency_ms": 7.25,
                        "failed_to_index_article_count": 1,
                    },
                    "thesis_metrics": {
                        "article_reconstruction_accuracy": 1.0,
                        "lead_paragraph_intact_rate": 0.75,
                        "boundary_break_rate": 0.5,
                        "boilerplate_contamination_rate": 0.25,
                        "entity_pair_preservation_rate": 0.8,
                        "story_level_top_k_diversity": 0.7,
                        "article_self_retrieval_top_5_rate": 0.9,
                        "hard_negative_separation_margin": 0.12,
                        "retrieval_hubness_rate": 0.05,
                        "recency_aware_retrieval_score": 0.6,
                    },
                    "thesis_metric_config": {
                        "ner_backend": "gliner",
                        "ner_model": "urchade/gliner_multi-v2.1",
                        "ner_labels": ["person", "organization"],
                        "ner_threshold": 0.5,
                        "entity_pair_window_characters": 300,
                        "hubness_query_share_threshold": 0.10,
                        "recency_half_life_days": 14,
                    },
                    "thesis_metric_errors": {},
                    "thesis_metric_details": {},
                    "entity_metric_artifacts": {
                        "mentions_path": "shared_data/knowledge_bases/evaluation/entity_mentions.jsonl",
                        "cache_path": "shared_data/knowledge_bases/evaluation/entity_cache.jsonl",
                    },
                    "diagnostic_metrics": {
                        "duplicate_chunk_rate": 0.1,
                        "average_adjacent_overlap_rate": 0.2,
                    },
                },
                {
                    "recipe_name": "missing_recipe",
                    "status": "missing_database",
                },
            ],
        }

        rows = make_comparison_table_rows(report)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["recipe"], "fake_recipe")
        self.assertEqual(rows[0]["status"], "evaluated")
        self.assertEqual(rows[0]["embedding_model"], "text-embedding-3-small")
        self.assertEqual(rows[0]["chunking_method"], "fixed")
        self.assertEqual(rows[0]["chunk_size_characters"], 2000)
        self.assertEqual(rows[0]["chunk_overlap_characters"], 200)
        self.assertEqual(rows[0]["expected_articles"], 3)
        self.assertEqual(rows[0]["indexed_articles"], 2)
        self.assertAlmostEqual(rows[0]["article_coverage_rate"], 2 / 3)
        self.assertEqual(rows[0]["chunks"], 3)
        self.assertEqual(rows[0]["vectors"], 3)
        self.assertAlmostEqual(rows[0]["average_chunk_characters"], 1000.5)
        self.assertEqual(rows[0]["median_chunk_characters"], 900)
        self.assertAlmostEqual(rows[0]["average_chunks_per_article"], 1.5)
        self.assertAlmostEqual(rows[0]["metadata_missing_rate"], 0.5)
        self.assertAlmostEqual(rows[0]["embedding_failure_rate"], 0.25)
        self.assertEqual(rows[0]["db_size_mb"], 1.0)
        self.assertEqual(rows[0]["build_time_seconds"], 12.5)
        self.assertEqual(rows[0]["query_latency_ms"], 7.25)
        self.assertEqual(rows[0]["failed_to_index_articles"], 1)
        self.assertAlmostEqual(rows[0]["article_reconstruction_rate"], 1.0)
        self.assertAlmostEqual(rows[0]["lead_paragraph_intact_rate"], 0.75)
        self.assertAlmostEqual(rows[0]["boundary_break_rate"], 0.5)
        self.assertAlmostEqual(rows[0]["boilerplate_contamination_rate"], 0.25)
        self.assertAlmostEqual(rows[0]["entity_pair_preservation_rate"], 0.8)
        self.assertAlmostEqual(rows[0]["story_level_top_k_diversity"], 0.7)
        self.assertAlmostEqual(rows[0]["article_self_retrieval_top_5_rate"], 0.9)
        self.assertAlmostEqual(rows[0]["hard_negative_separation_margin"], 0.12)
        self.assertAlmostEqual(rows[0]["retrieval_hubness_rate"], 0.05)
        self.assertAlmostEqual(rows[0]["recency_aware_retrieval_score"], 0.6)
        self.assertAlmostEqual(rows[0]["duplicate_chunk_rate"], 0.1)
        self.assertAlmostEqual(rows[0]["average_adjacent_overlap_rate"], 0.2)

        self.assertEqual(rows[1]["recipe"], "missing_recipe")
        self.assertEqual(rows[1]["status"], "missing_database")
        self.assertIsNone(rows[1]["chunks"])

    def test_write_comparison_tables_writes_markdown_and_csv(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            markdown_path = temporary_path / "kb_metrics_table.md"
            csv_path = temporary_path / "kb_metrics_table.csv"
            report = {
                "recipes": [
                    {
                        "recipe_name": "fake_recipe",
                        "status": "evaluated",
                        "recipe_config": {
                            "embedding_model": "text-embedding-3-small",
                            "chunking_method": "none",
                            "chunk_size_characters": 0,
                            "chunk_overlap_characters": 0,
                        },
                        "sanity_metrics": {
                            "expected_article_count": 3,
                            "article_count": 2,
                            "article_coverage_rate": 2 / 3,
                            "chunk_count": 2,
                            "vector_count": 2,
                            "chunk_size_characters": {
                                "average": 1500,
                                "median": 1500,
                            },
                            "chunks_per_article": {
                                "average": 1,
                            },
                            "metadata_missing_rates": {
                                "any_required": 0,
                            },
                            "embedding_failure_rate": 0,
                            "db_size_bytes": 1048576,
                            "build_time_seconds": 2.5,
                            "query_latency_ms": 4.5,
                            "failed_to_index_article_count": 1,
                        },
                        "thesis_metrics": {
                            "article_reconstruction_accuracy": 1,
                            "lead_paragraph_intact_rate": 1,
                            "boundary_break_rate": 0,
                            "boilerplate_contamination_rate": None,
                        },
                        "diagnostic_metrics": {
                            "duplicate_chunk_rate": 0,
                            "average_adjacent_overlap_rate": None,
                        },
                    }
                ]
            }

            result = write_comparison_tables(report, markdown_path, csv_path)

            markdown_text = markdown_path.read_text(encoding="utf-8")
            csv_text = csv_path.read_text(encoding="utf-8")

        self.assertEqual(result["markdown_table_path"], str(markdown_path))
        self.assertEqual(result["csv_table_path"], str(csv_path))
        self.assertIn("| Recipe | Status | Embedding model |", markdown_text)
        self.assertIn("| fake_recipe | evaluated | text-embedding-3-small |", markdown_text)
        self.assertIn("66.7%", markdown_text)
        self.assertIn("n/a", markdown_text)
        self.assertIn("recipe,status,embedding_model", csv_text)
        self.assertIn("query_latency_ms", csv_text)
        self.assertIn(",4.5,", csv_text)
        self.assertIn("fake_recipe,evaluated,text-embedding-3-small", csv_text)
        self.assertIn(",0.6666666666666666,", csv_text)

    def write_clean_article(
        self,
        article_path,
        article_id,
        source,
        title,
        link,
        text,
        published_at,
        indexed_at,
        summary="",
    ):
        article = {
            "id": article_id,
            "is_valid_article": True,
            "source": source,
            "title": title,
            "link": link,
            "summary": summary,
            "text": text,
            "metadata": {
                "published": published_at,
                "indexed_at": indexed_at,
            },
        }
        article_path.write_text(json.dumps(article, indent=2), encoding="utf-8")

    def insert_minimal_article_and_chunk(
        self,
        connection,
        article_path,
        article_id,
        source,
        title,
        published_at,
    ):
        insert_article(
            connection,
            {
                "article_id": article_id,
                "source": source,
                "title": title,
                "url": f"https://example.com/{article_id}",
                "published_at": published_at,
                "indexed_at": "2026-05-01T12:00:00+00:00",
                "indexed_at_epoch": 1777636800.0,
                "cleaned_at": "",
                "input_file_path": str(article_path),
                "content_hash": f"hash-{article_id}",
                "status": "ready",
            },
        )
        insert_chunk(
            connection,
            {
                "chunk_id": f"{article_id}_chunk_0",
                "article_id": article_id,
                "chunk_index": 0,
                "chunk_text": f"Chunk text for {article_id}.",
                "character_start": 0,
                "character_end": 20,
                "chunk_hash": f"chunk-hash-{article_id}",
            },
        )

    def make_retrieval_result(
        self,
        article_id,
        chunk_index,
        chunk_text,
        source,
        published_at,
        distance,
    ):
        return {
            "article_id": article_id,
            "chunk_index": chunk_index,
            "chunk_text": chunk_text,
            "source": source,
            "published_at": published_at,
            "distance": distance,
        }


if __name__ == "__main__":
    unittest.main()
