"""
Tests for GLiNER entity precompute orchestration.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_bases.evaluation import entity_precompute
from knowledge_bases.evaluation.constants import DEFAULT_THESIS_METRIC_CONFIG
from knowledge_bases.evaluation.entity_precompute import collect_entity_article_records
from knowledge_bases.evaluation.entity_precompute import precompute_entity_records
from knowledge_bases.evaluation.entity_precompute import resolve_entity_device
from knowledge_bases.evaluation.entity_store import get_cached_entities
from knowledge_bases.evaluation.entity_store import make_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store


def make_article_record(article_id, text, content_hash):
    return {
        "article_id": article_id,
        "source": "PUBLICO",
        "title": article_id,
        "content_hash": content_hash,
        "text": text,
    }


def write_clean_article(path, article_id, text):
    path.write_text(
        json.dumps(
            {
                "id": article_id,
                "is_valid_article": True,
                "title": article_id,
                "summary": "",
                "text": text,
                "metadata": {
                    "source": "PUBLICO",
                    "title": article_id,
                    "url": f"https://example.com/{article_id}",
                    "published_at": "2026-05-01T00:00:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )


class KnowledgeBaseEntityPrecomputeTests(unittest.TestCase):
    def test_resolve_entity_device_prefers_mps_when_auto_and_available(self):
        self.assertEqual(resolve_entity_device("auto", True), "mps")
        self.assertEqual(resolve_entity_device("auto", False), "cpu")
        self.assertEqual(resolve_entity_device("cpu", True), "cpu")

    def test_split_text_into_token_windows_preserves_character_offsets(self):
        text = "zero one two three four five six seven"

        windows = entity_precompute.split_text_into_token_windows(
            text,
            max_tokens=4,
            overlap_tokens=1,
        )

        self.assertEqual(len(windows), 3)
        self.assertEqual(windows[0]["token_start"], 0)
        self.assertEqual(windows[0]["character_start"], text.index("zero"))
        self.assertEqual(windows[0]["text"], "zero one two three")
        self.assertEqual(windows[1]["token_start"], 3)
        self.assertEqual(windows[1]["character_start"], text.index("three"))
        self.assertEqual(windows[1]["text"], "three four five six")
        self.assertEqual(windows[2]["token_start"], 6)
        self.assertEqual(windows[2]["character_start"], text.index("six"))
        self.assertEqual(windows[2]["text"], "six seven")

    def test_split_text_into_token_windows_counts_gliner_punctuation_tokens(self):
        text = "Lisbon, Porto; Algarve."

        windows = entity_precompute.split_text_into_token_windows(
            text,
            max_tokens=3,
            overlap_tokens=0,
        )

        self.assertEqual([window["text"] for window in windows], ["Lisbon, Porto", "; Algarve."])
        self.assertEqual(windows[1]["character_start"], text.index(";"))

    def test_merge_window_entities_offsets_and_dedupes_overlap_entities(self):
        text = "Lisbon welcomed Porto and Lisbon again."
        windows = [
            {
                "text": text[:24],
                "character_start": 0,
                "character_end": 24,
                "token_start": 0,
                "token_end": 3,
            },
            {
                "text": text[16:],
                "character_start": 16,
                "character_end": len(text),
                "token_start": 2,
                "token_end": 6,
            },
        ]
        raw_window_entities = [
            [
                {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.80},
                {"text": "Porto", "label": "location", "start": 16, "end": 21, "score": 0.70},
            ],
            [
                {"text": "Porto", "label": "location", "start": 0, "end": 5, "score": 0.95},
                {"text": "Lisbon", "label": "location", "start": 10, "end": 16, "score": 0.90},
            ],
        ]

        entities = entity_precompute.merge_window_entities(
            windows,
            raw_window_entities,
            threshold=0.5,
        )

        self.assertEqual(
            [(entity["text"], entity["start"], entity["end"], entity["score"]) for entity in entities],
            [
                ("Lisbon", 0, 6, 0.80),
                ("Porto", 16, 21, 0.95),
                ("Lisbon", 26, 32, 0.90),
            ],
        )

    def test_collect_entity_article_records_loads_unique_clean_corpus_articles_for_all(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            clean_folder = Path(temporary_folder) / "clean"
            clean_folder.mkdir()
            write_clean_article(clean_folder / "one.json", "one", "Lisbon welcomed visitors.")
            write_clean_article(clean_folder / "two.json", "two", "Porto welcomed visitors.")

            recipes = {
                "recipe-a": {"name": "recipe-a", "input_corpus": str(clean_folder)},
                "recipe-b": {"name": "recipe-b", "input_corpus": str(clean_folder)},
            }

            def fake_load_recipe(recipe_name):
                return recipes[recipe_name]

            with patch("knowledge_bases.evaluation.entity_precompute.resolve_selected_recipe_names", return_value=["recipe-a", "recipe-b"]), \
                 patch("knowledge_bases.evaluation.entity_precompute.load_recipe", side_effect=fake_load_recipe):
                records = collect_entity_article_records(["all"])

        self.assertEqual([record["article_id"] for record in records], ["one", "two"])
        self.assertEqual([record["text"] for record in records], ["Lisbon welcomed visitors.", "Porto welcomed visitors."])

    def test_precompute_entity_records_batches_dedupes_and_skips_cached(self):
        calls = []

        def fake_batch_extractor(texts, config, runtime):
            calls.append(list(texts))
            results = []
            for text in texts:
                if "Lisbon" in text:
                    results.append(
                        [
                            {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.95},
                        ]
                    )
                else:
                    results.append(
                        [
                            {"text": "Madrid", "label": "location", "start": 0, "end": 6, "score": 0.95},
                        ]
                    )
            return results

        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = Path(temporary_folder) / "entities.sqlite"
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)
            article_records = [
                make_article_record("article-one", "Lisbon welcomed visitors.", "hash-one"),
                make_article_record("article-one-duplicate", "Lisbon welcomed visitors.", "hash-one"),
                make_article_record("article-two", "Madrid hosted executives.", "hash-two"),
            ]

            first_summary = precompute_entity_records(
                article_records,
                db_path,
                config,
                "mps",
                2,
                False,
                fake_batch_extractor,
                {},
            )
            second_summary = precompute_entity_records(
                article_records,
                db_path,
                config,
                "mps",
                2,
                False,
                fake_batch_extractor,
                {},
            )
            connection = open_entity_store(db_path)
            lisbon_key = make_entity_cache_key("Lisbon welcomed visitors.", config, "mps")
            cached_entities = get_cached_entities(connection, lisbon_key)
            connection.close()

        self.assertEqual(first_summary["candidate_count"], 3)
        self.assertEqual(first_summary["unique_count"], 2)
        self.assertEqual(first_summary["processed_count"], 2)
        self.assertEqual(first_summary["cached_count"], 0)
        self.assertEqual(second_summary["processed_count"], 0)
        self.assertEqual(second_summary["cached_count"], 2)
        self.assertEqual(calls, [["Lisbon welcomed visitors.", "Madrid hosted executives."]])
        self.assertEqual(cached_entities[0]["normalized_text"], "lisbon")

    def test_precompute_entity_records_records_batch_errors_and_continues(self):
        def fake_batch_extractor(texts, config, runtime):
            if "Broken text" in texts:
                raise ValueError("batch failed")
            return [[{"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.95}]]

        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = Path(temporary_folder) / "entities.sqlite"
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)
            article_records = [
                make_article_record("article-one", "Broken text", "hash-one"),
                make_article_record("article-two", "Lisbon text", "hash-two"),
            ]

            summary = precompute_entity_records(
                article_records,
                db_path,
                config,
                "mps",
                1,
                False,
                fake_batch_extractor,
                {},
            )
            connection = open_entity_store(db_path)
            rows = connection.execute(
                "SELECT article_id, status, error_text FROM entity_documents ORDER BY article_id"
            ).fetchall()
            connection.close()

        self.assertEqual(summary["processed_count"], 1)
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(rows[0]["article_id"], "article-one")
        self.assertEqual(rows[0]["status"], "error")
        self.assertEqual(rows[0]["error_text"], "batch failed")
        self.assertEqual(rows[1]["article_id"], "article-two")
        self.assertEqual(rows[1]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
