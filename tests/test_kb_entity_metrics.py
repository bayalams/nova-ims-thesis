"""
Tests for GLiNER-backed entity-pair thesis metrics.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_bases.evaluation.constants import DEFAULT_THESIS_METRIC_CONFIG
from knowledge_bases.evaluation.entity_metrics import build_entity_pairs
from knowledge_bases.evaluation.entity_metrics import calculate_entity_pair_preservation_rate
from knowledge_bases.evaluation.entity_metrics import make_entity_cache_key
from knowledge_bases.evaluation.entity_metrics import normalize_entity_mentions
from knowledge_bases.evaluation.entity_metrics import normalize_entity_text
from knowledge_bases.evaluation.entity_metrics import pair_is_preserved_in_chunks


def make_clean_articles():
    return {
        "valid_count": 2,
        "invalid_count": 0,
        "articles_by_id": {
            "article-one": {
                "article_id": "article-one",
                "text": "Lisbon welcomed Turismo de Portugal leaders today.",
                "title": "Lisbon tourism",
            },
            "article-two": {
                "article_id": "article-two",
                "text": "Madrid hosted Iberia executives yesterday.",
                "title": "Madrid travel",
            },
        },
        "articles_by_path": {},
    }


def make_article_rows():
    return [
        {
            "article_id": "article-one",
            "source": "PUBLICO",
            "title": "Lisbon tourism",
            "published_at": "2026-05-18T10:00:00+00:00",
            "content_hash": "hash-one",
        },
        {
            "article_id": "article-two",
            "source": "EL_PAIS",
            "title": "Madrid travel",
            "published_at": "2026-05-18T11:00:00+00:00",
            "content_hash": "hash-two",
        },
    ]


def make_chunk_rows():
    return [
        {
            "article_id": "article-one",
            "chunk_index": 0,
            "chunk_text": "Lisbon welcomed Turismo de Portugal leaders today.",
        },
        {
            "article_id": "article-two",
            "chunk_index": 0,
            "chunk_text": "Madrid hosted travel leaders.",
        },
        {
            "article_id": "article-two",
            "chunk_index": 1,
            "chunk_text": "Iberia executives arrived yesterday.",
        },
    ]


def fake_entity_extractor(text, config, runtime):
    if "Lisbon" in text:
        return [
            {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.98},
            {"text": "Turismo de Portugal", "label": "organization", "start": 16, "end": 35, "score": 0.91},
        ]

    return [
        {"text": "Madrid", "label": "location", "start": 0, "end": 6, "score": 0.94},
        {"text": "Iberia", "label": "organization", "start": 14, "end": 20, "score": 0.90},
    ]


def fake_single_entity_extractor(text, config, runtime):
    return [
        {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.98},
    ]


class KnowledgeBaseEntityMetricsTests(unittest.TestCase):
    def test_normalize_entity_text_lowercases_and_collapses_whitespace(self):
        self.assertEqual(normalize_entity_text("  Turismo   de Portugal  "), "turismo de portugal")

    def test_normalize_entity_mentions_removes_duplicates_and_low_scores(self):
        raw_entities = [
            {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.8},
            {"text": "Lisbon", "label": "location", "start": 0, "end": 6, "score": 0.8},
            {"text": "Weak", "label": "organization", "start": 10, "end": 14, "score": 0.1},
            {"text": "   ", "label": "organization", "start": 20, "end": 23, "score": 0.9},
        ]

        entities = normalize_entity_mentions(raw_entities, 0.5)

        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["text"], "Lisbon")
        self.assertEqual(entities[0]["normalized_text"], "lisbon")

    def test_build_entity_pairs_uses_window_and_canonical_order(self):
        entities = [
            {"normalized_text": "turismo de portugal", "start": 16, "end": 35, "label": "organization"},
            {"normalized_text": "lisbon", "start": 0, "end": 6, "label": "location"},
            {"normalized_text": "far entity", "start": 1000, "end": 1010, "label": "event"},
        ]

        pairs = build_entity_pairs(entities, 300)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["left"], "lisbon")
        self.assertEqual(pairs[0]["right"], "turismo de portugal")

    def test_make_entity_cache_key_changes_when_config_changes(self):
        first_config = dict(DEFAULT_THESIS_METRIC_CONFIG)
        second_config = dict(DEFAULT_THESIS_METRIC_CONFIG)
        second_config["ner_threshold"] = 0.7

        first_key = make_entity_cache_key("Article text", first_config)
        second_key = make_entity_cache_key("Article text", second_config)

        self.assertNotEqual(first_key, second_key)

    def test_pair_preservation_requires_exact_contiguous_tokens(self):
        pair = {"left": "iran", "right": "us"}
        chunk_rows = [
            {"chunk_text": "Russia discussed a transiranian railway."},
            {"chunk_text": "Iran met with US officials."},
        ]

        self.assertTrue(pair_is_preserved_in_chunks(pair, chunk_rows))
        self.assertFalse(pair_is_preserved_in_chunks(pair, chunk_rows[:1]))

    def test_pair_preservation_treats_punctuation_as_token_boundary(self):
        pair = {"left": "lisbon", "right": "turismo de portugal"}
        chunk_rows = [
            {"chunk_text": "Lisbon. Turismo de Portugal, welcomed leaders."},
        ]

        self.assertTrue(pair_is_preserved_in_chunks(pair, chunk_rows))

    def test_calculate_entity_pair_preservation_rate_with_fake_extractor(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            cache_path = Path(temporary_folder) / "entity_cache.jsonl"
            mentions_path = Path(temporary_folder) / "entity_mentions.jsonl"
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)

            result = calculate_entity_pair_preservation_rate(
                make_article_rows(),
                make_chunk_rows(),
                make_clean_articles(),
                "fake_recipe",
                config,
                cache_path,
                mentions_path,
                {},
                fake_entity_extractor,
                True,
            )

            mention_lines = mentions_path.read_text(encoding="utf-8").strip().splitlines()
            mention_records = [json.loads(line) for line in mention_lines]

        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["value"], 0.5)
        self.assertEqual(result["details"]["source_entity_pair_count"], 2)
        self.assertEqual(result["details"]["preserved_entity_pair_count"], 1)
        self.assertEqual(len(mention_records), 2)
        self.assertTrue(mention_records[0]["entity_pairs"][0]["preserved_in_chunk"])
        self.assertFalse(mention_records[1]["entity_pairs"][0]["preserved_in_chunk"])

    def test_calculate_entity_pair_preservation_rate_returns_none_when_no_pairs_exist(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            cache_path = Path(temporary_folder) / "entity_cache.jsonl"
            mentions_path = Path(temporary_folder) / "entity_mentions.jsonl"
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)

            result = calculate_entity_pair_preservation_rate(
                make_article_rows(),
                make_chunk_rows(),
                make_clean_articles(),
                "fake_recipe",
                config,
                cache_path,
                mentions_path,
                {},
                fake_single_entity_extractor,
                True,
            )

        self.assertIsNone(result["value"])
        self.assertEqual(result["details"]["source_entity_pair_count"], 0)
        self.assertEqual(result["details"]["preserved_entity_pair_count"], 0)

    def test_entity_cache_prevents_repeated_extraction(self):
        calls = []

        def counting_extractor(text, config, runtime):
            calls.append(text)
            return fake_entity_extractor(text, config, runtime)

        with tempfile.TemporaryDirectory() as temporary_folder:
            cache_path = Path(temporary_folder) / "entity_cache.jsonl"
            mentions_path = Path(temporary_folder) / "entity_mentions.jsonl"
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)

            first_result = calculate_entity_pair_preservation_rate(
                make_article_rows(),
                make_chunk_rows(),
                make_clean_articles(),
                "fake_recipe",
                config,
                cache_path,
                mentions_path,
                {},
                counting_extractor,
                True,
            )
            second_result = calculate_entity_pair_preservation_rate(
                make_article_rows(),
                make_chunk_rows(),
                make_clean_articles(),
                "fake_recipe",
                config,
                cache_path,
                mentions_path,
                {},
                counting_extractor,
                True,
            )

        self.assertAlmostEqual(first_result["value"], 0.5)
        self.assertAlmostEqual(second_result["value"], 0.5)
        self.assertEqual(len(calls), 2)

    def test_calculate_entity_pair_preservation_rate_uses_configured_window_batch_size(self):
        calls = []
        seen_batch_sizes = []

        def fake_batch_extractor(texts, config, runtime):
            calls.append(list(texts))
            seen_batch_sizes.append(config["entity_window_batch_size"])
            results = []
            for text in texts:
                results.append(fake_entity_extractor(text, config, runtime))
            return results

        with tempfile.TemporaryDirectory() as temporary_folder:
            temporary_path = Path(temporary_folder)
            cache_path = temporary_path / "entity_cache.jsonl"
            mentions_path = temporary_path / "entity_mentions.jsonl"
            store_path = temporary_path / "entities.sqlite"
            config = dict(DEFAULT_THESIS_METRIC_CONFIG)

            with patch(
                "knowledge_bases.evaluation.entity_metrics.extract_entity_batches_with_gliner",
                side_effect=fake_batch_extractor,
            ):
                result = calculate_entity_pair_preservation_rate(
                    article_rows=make_article_rows(),
                    chunk_rows=make_chunk_rows(),
                    clean_articles=make_clean_articles(),
                    recipe_name="fake_recipe",
                    config=config,
                    cache_path=cache_path,
                    mentions_path=mentions_path,
                    runtime={},
                    reset_mentions=True,
                    entity_store_path=store_path,
                    entity_device="cpu",
                    entity_window_batch_size=1,
                )

        expected_texts = make_clean_articles()["articles_by_id"]
        self.assertEqual(
            calls,
            [
                [expected_texts["article-one"]["text"]],
                [expected_texts["article-two"]["text"]],
            ],
        )
        self.assertEqual(seen_batch_sizes, [1, 1])
        self.assertEqual(result["details"]["computed_entity_count"], 2)

    def test_default_gliner_extractor_reports_missing_dependency_plainly(self):
        from knowledge_bases.evaluation.entity_metrics import extract_entities_with_gliner

        runtime = {"force_import_error_for_test": True}

        with self.assertRaises(ValueError) as context:
            extract_entities_with_gliner("Lisbon text", DEFAULT_THESIS_METRIC_CONFIG, runtime)

        self.assertIn("GLiNER dependency is not installed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
