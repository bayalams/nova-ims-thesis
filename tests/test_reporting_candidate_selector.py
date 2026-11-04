"""
Tests for embedding-prototype report candidate selection.
"""

import unittest
from unittest.mock import patch

from reporting.candidate_selector import article_selector_text
from reporting.candidate_selector import build_article_embeddings
from reporting.candidate_selector import score_article_embedding
from reporting.candidate_selector import select_articles_from_scores


class ReportingCandidateSelectorTests(unittest.TestCase):
    def test_article_selector_text_uses_title_source_tags_summary_and_text(self):
        article = {
            "text": "Hotel demand increased in Porto.",
            "metadata": {
                "title": "Hotels see stronger demand",
                "source": "PUBLICO",
                "tags": ["tourism", "hotels"],
                "summary": "Demand improved.",
            },
        }

        text = article_selector_text(article)

        self.assertIn("Hotels see stronger demand", text)
        self.assertIn("PUBLICO", text)
        self.assertIn("tourism", text)
        self.assertIn("Demand improved.", text)
        self.assertIn("Hotel demand increased in Porto.", text)

    def test_score_article_embedding_keeps_article_when_positive_margin_is_clear(self):
        prototype_embeddings = [
            {
                "id": "tourism_demand",
                "label": "Tourism demand",
                "polarity": "positive",
                "embedding": [1.0, 0.0],
            },
            {
                "id": "generic_crime",
                "label": "Generic crime",
                "polarity": "negative",
                "embedding": [0.0, 1.0],
            },
        ]

        score = score_article_embedding(
            article_embedding=[1.0, 0.0],
            prototype_embeddings=prototype_embeddings,
            positive_threshold=0.5,
            margin_threshold=0.2,
        )

        self.assertEqual(score["is_selected"], True)
        self.assertEqual(score["positive_prototype_id"], "tourism_demand")
        self.assertEqual(score["negative_prototype_id"], "generic_crime")

    def test_score_article_embedding_rejects_article_when_negative_is_too_close(self):
        prototype_embeddings = [
            {
                "id": "destination_safety",
                "label": "Destination safety",
                "polarity": "positive",
                "embedding": [1.0, 0.0],
            },
            {
                "id": "generic_online_child_safety",
                "label": "Generic online child safety",
                "polarity": "negative",
                "embedding": [0.0, 1.0],
            },
        ]

        score = score_article_embedding(
            article_embedding=[0.55, 0.83],
            prototype_embeddings=prototype_embeddings,
            positive_threshold=0.5,
            margin_threshold=0.2,
        )

        self.assertEqual(score["is_selected"], False)
        self.assertLess(score["margin"], 0.2)

    def test_select_articles_from_scores_sorts_by_score_and_limits_results(self):
        articles = [
            {"id": "weak", "metadata": {"title": "Weak"}},
            {"id": "strong", "metadata": {"title": "Strong"}},
            {"id": "rejected", "metadata": {"title": "Rejected"}},
        ]
        score_by_article_id = {
            "weak": {
                "is_selected": True,
                "score": 0.3,
                "margin": 0.3,
                "reason": "weak",
            },
            "strong": {
                "is_selected": True,
                "score": 0.8,
                "margin": 0.8,
                "reason": "strong",
            },
            "rejected": {
                "is_selected": False,
                "score": -0.1,
                "margin": -0.1,
                "reason": "rejected",
            },
        }

        result = select_articles_from_scores(
            articles,
            score_by_article_id,
            candidate_limit=1,
        )

        self.assertEqual([article["id"] for article in result["articles"]], ["strong"])
        self.assertEqual(result["selection"]["raw_count"], 3)
        self.assertEqual(result["selection"]["kept_count"], 1)
        self.assertEqual(result["selection"]["excluded_count"], 2)
        self.assertEqual(result["selection"]["method"], "embedding_prototypes_v2")

    def test_build_article_embeddings_splits_large_embedding_requests(self):
        articles = [
            {"id": "a1", "text": "A" * 200, "metadata": {"title": "One"}},
            {"id": "a2", "text": "B" * 200, "metadata": {"title": "Two"}},
            {"id": "a3", "text": "C" * 200, "metadata": {"title": "Three"}},
        ]
        batch_lengths = []

        def fake_create_embedding_batch(client, texts, model_name):
            batch_lengths.append(len(texts))
            vectors = []
            for text in texts:
                vectors.append([float(len(batch_lengths)), float(len(text))])
            return {
                "vectors": vectors,
                "token_count": 0,
            }

        with patch("reporting.candidate_selector.create_embedding_batch", side_effect=fake_create_embedding_batch), \
             patch("reporting.candidate_selector.time.sleep") as fake_sleep:
            article_embeddings = build_article_embeddings(
                client=object(),
                articles=articles,
                model_name="text-embedding-3-small",
                max_batch_tokens=80,
            )

        self.assertEqual(batch_lengths, [1, 1, 1])
        self.assertEqual(fake_sleep.call_count, 2)
        fake_sleep.assert_any_call(30.0)
        self.assertEqual(sorted(article_embeddings.keys()), ["a1", "a2", "a3"])

    def test_build_article_embeddings_retries_rate_limit_with_backoff(self):
        articles = [
            {"id": "a1", "text": "Beach demand", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Hotel occupancy", "metadata": {"title": "Two"}},
        ]
        call_count = 0

        def fake_create_embedding_batch(client, texts, model_name):
            nonlocal call_count
            call_count = call_count + 1

            if call_count == 1:
                raise ValueError(
                    "Error code: 429 - Please retry after 60 seconds."
                )

            return {
                "vectors": [[1.0, 2.0], [3.0, 4.0]],
                "token_count": 0,
            }

        with patch("reporting.candidate_selector.create_embedding_batch", side_effect=fake_create_embedding_batch), \
             patch("reporting.candidate_selector.time.sleep") as fake_sleep:
            article_embeddings = build_article_embeddings(
                client=object(),
                articles=articles,
                model_name="text-embedding-3-small",
                max_batch_tokens=1000,
            )

        self.assertEqual(call_count, 2)
        fake_sleep.assert_called_once_with(120.0)
        self.assertEqual(sorted(article_embeddings.keys()), ["a1", "a2"])


if __name__ == "__main__":
    unittest.main()
