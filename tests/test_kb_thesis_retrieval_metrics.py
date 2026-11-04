"""
Tests for thesis retrieval metrics.
"""

import unittest

from knowledge_bases.evaluation.constants import DEFAULT_THESIS_METRIC_CONFIG
from knowledge_bases.evaluation.thesis_retrieval_metrics import calculate_hard_negative_separation_margin
from knowledge_bases.evaluation.thesis_retrieval_metrics import calculate_recency_aware_retrieval_score
from knowledge_bases.evaluation.thesis_retrieval_metrics import calculate_retrieval_hubness_rate
from knowledge_bases.evaluation.thesis_retrieval_metrics import calculate_thesis_retrieval_metrics
from knowledge_bases.evaluation.thesis_retrieval_metrics import make_empty_thesis_retrieval_metrics
from knowledge_bases.evaluation.thesis_retrieval_metrics import safe_float


def make_query(article_id, published_at="2026-05-18T12:00:00+00:00"):
    """
    Create one fake thesis retrieval query.
    """
    return {
        "article_id": article_id,
        "published_at": published_at,
    }


def make_result(article_id, distance, published_at="2026-05-18T12:00:00+00:00"):
    """
    Create one fake thesis retrieval result.
    """
    return {
        "article_id": article_id,
        "distance": distance,
        "published_at": published_at,
    }


class KnowledgeBaseThesisRetrievalMetricsTests(unittest.TestCase):
    def test_empty_thesis_retrieval_metrics_are_null(self):
        metrics = make_empty_thesis_retrieval_metrics()

        self.assertIsNone(metrics["story_level_top_k_diversity"])
        self.assertIsNone(metrics["article_self_retrieval_top_5_rate"])
        self.assertIsNone(metrics["hard_negative_separation_margin"])
        self.assertIsNone(metrics["retrieval_hubness_rate"])
        self.assertIsNone(metrics["recency_aware_retrieval_score"])
        self.assertNotIn("entity_pair_preservation_rate", metrics)

    def test_calculate_thesis_retrieval_metrics_from_query_results(self):
        query_results = [
            {
                "query": make_query("article-one"),
                "results": [
                    make_result("article-one", 0.10),
                    make_result("article-two", 0.25, "2026-05-17T12:00:00+00:00"),
                    make_result("article-three", 0.30, "2026-05-01T12:00:00+00:00"),
                ],
            },
            {
                "query": make_query("article-four"),
                "results": [
                    make_result("article-two", 0.20),
                    make_result("article-four", 0.35, "2026-05-10T12:00:00+00:00"),
                    make_result("article-two", 0.21),
                ],
            },
            {
                "query": make_query("article-five"),
                "results": [
                    make_result("article-two", 0.18),
                    make_result("article-six", 0.40, "2026-04-18T12:00:00+00:00"),
                ],
            },
        ]

        metrics = calculate_thesis_retrieval_metrics(query_results, 3, DEFAULT_THESIS_METRIC_CONFIG)

        self.assertAlmostEqual(metrics["article_self_retrieval_top_5_rate"], 2 / 3)
        self.assertAlmostEqual(metrics["story_level_top_k_diversity"], ((3 / 3) + (2 / 3) + (2 / 2)) / 3)
        self.assertAlmostEqual(metrics["hard_negative_separation_margin"], ((0.25 - 0.10) + (0.20 - 0.35) + 0.0) / 3)
        self.assertGreater(metrics["retrieval_hubness_rate"], 0)
        self.assertGreater(metrics["recency_aware_retrieval_score"], 0)
        self.assertLessEqual(metrics["recency_aware_retrieval_score"], 1)
        self.assertNotIn("entity_pair_preservation_rate", metrics)

    def test_safe_float_rejects_nan_and_infinity(self):
        self.assertIsNone(safe_float(float("nan")))
        self.assertIsNone(safe_float(float("inf")))
        self.assertIsNone(safe_float(float("-inf")))

    def test_hard_negative_margin_skips_queries_without_wrong_finite_distance(self):
        query_results = [
            {
                "query": make_query("article-empty"),
                "results": [],
            },
            {
                "query": make_query("article-one"),
                "results": [
                    make_result("article-one", 0.10),
                    make_result("article-one", 0.09),
                    make_result("article-two", "not-a-number"),
                ],
            },
            {
                "query": make_query("article-three"),
                "results": [
                    make_result("article-four", 0.40),
                    make_result("article-five", 0.50),
                    make_result("article-six", 0.60),
                    make_result("article-seven", 0.70),
                    make_result("article-eight", 0.80),
                    make_result("article-three", 0.20),
                ],
            },
        ]

        margin = calculate_hard_negative_separation_margin(query_results)

        self.assertAlmostEqual(margin, 0.20)

    def test_hard_negative_margin_counts_missing_correct_when_wrong_distance_exists(self):
        query_results = [
            {
                "query": make_query("article-one"),
                "results": [
                    make_result("article-two", 0.10),
                    make_result("article-three", 0.20),
                ],
            }
        ]

        margin = calculate_hard_negative_separation_margin(query_results)

        self.assertAlmostEqual(margin, 0.0)

    def test_hubness_uses_query_share_threshold_not_occurrence_share(self):
        config = dict(DEFAULT_THESIS_METRIC_CONFIG)
        config["hubness_query_share_threshold"] = 0.50
        query_results = [
            {
                "query": make_query("query-one"),
                "results": [
                    make_result("article-hub", 0.10),
                    make_result("article-hub", 0.11),
                    make_result("article-hub", 0.12),
                ],
            },
            {
                "query": make_query("query-two"),
                "results": [
                    make_result("article-other", 0.20),
                    make_result("article-other", 0.21),
                    make_result("article-other", 0.22),
                ],
            },
        ]

        rate_at_threshold = calculate_retrieval_hubness_rate(query_results, 3, config)
        config["hubness_query_share_threshold"] = 0.49
        rate_above_threshold = calculate_retrieval_hubness_rate(query_results, 3, config)

        self.assertAlmostEqual(rate_at_threshold, 0.0)
        self.assertAlmostEqual(rate_above_threshold, 1.0)

    def test_recency_score_ignores_distance_and_rejects_bad_half_life(self):
        config = dict(DEFAULT_THESIS_METRIC_CONFIG)
        config["recency_half_life_days"] = 14
        query_results = [
            {
                "query": make_query("article-one"),
                "results": [
                    make_result("article-two", 2.50),
                    make_result("article-three", 3.00, "2026-05-17T12:00:00+00:00"),
                ],
            }
        ]

        score = calculate_recency_aware_retrieval_score(query_results, config)
        config["recency_half_life_days"] = 0

        self.assertGreater(score, 0)
        self.assertIsNone(calculate_recency_aware_retrieval_score(query_results, config))


if __name__ == "__main__":
    unittest.main()
