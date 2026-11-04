"""
Tests for opt-in KB retrieval metrics.
"""

import unittest
from unittest.mock import patch

from knowledge_bases.evaluation.retrieval_metrics import aggregate_retrieval_query_results
from knowledge_bases.evaluation.retrieval_metrics import calculate_reciprocal_rank
from knowledge_bases.evaluation.retrieval_metrics import evaluate_retrieval_metrics


def make_query(article_id, query_type):
    """
    Create one fake retrieval metric query.

    PARAMETERS:
    - article_id: Expected article id
    - query_type: title or summary

    RETURNS:
    - Query dictionary
    """
    return {
        "article_id": article_id,
        "query_type": query_type,
        "query_text": f"{query_type} for {article_id}",
    }


def make_result(article_id, chunk_index, chunk_text):
    """
    Create one fake ranked retrieval result.

    PARAMETERS:
    - article_id: Result article id
    - chunk_index: Chunk index inside the article
    - chunk_text: Returned chunk text

    RETURNS:
    - Result dictionary
    """
    return {
        "article_id": article_id,
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
        "source": f"source-{article_id}",
        "published_at": "2026-05-01T10:00:00+00:00",
    }


class KnowledgeBaseRetrievalMetricsTests(unittest.TestCase):
    def test_evaluate_retrieval_metrics_batches_query_embeddings_before_search(self):
        article_rows = [
            {
                "article_id": "article-one",
                "title": "Database title one",
                "published_at": "2026-05-01T10:00:00+00:00",
            },
            {
                "article_id": "article-two",
                "title": "Database title two",
                "published_at": "2026-05-02T10:00:00+00:00",
            },
        ]
        clean_articles = {
            "articles_by_id": {
                "article-one": {
                    "title": "Clean title one",
                    "summary": "Clean summary one",
                },
                "article-two": {
                    "title": "Clean title two",
                    "summary": "",
                },
            }
        }
        recipe = {
            "embedding_model": "text-embedding-3-small",
        }
        retrieval_options = {
            "enabled": True,
            "sample_size": 2,
            "top_k": 10,
            "search_mode": "ann",
        }
        embedding_calls = []
        searched_blobs = []

        def fake_create_embedding_batch(client, texts, model):
            embedding_calls.append(list(texts))
            vectors = []
            for index, text in enumerate(texts, start=1):
                vectors.append([float(index), float(len(text))])
            return {
                "vectors": vectors,
                "token_count": 10,
            }

        def fake_search(connection, recipe, query_blob, top_k):
            searched_blobs.append(query_blob)
            return []

        with patch("knowledge_bases.evaluation.retrieval_metrics.find_vec1_extension", return_value="vec1.so"), \
             patch("knowledge_bases.evaluation.retrieval_metrics.load_vec1_extension"), \
             patch(
                 "knowledge_bases.evaluation.retrieval_metrics.create_embedding_batch",
                 side_effect=fake_create_embedding_batch,
             ), \
             patch("knowledge_bases.evaluation.retrieval_metrics.search_ann", side_effect=fake_search):
            metrics = evaluate_retrieval_metrics(
                None,
                recipe,
                article_rows,
                clean_articles,
                retrieval_options,
                retrieval_runtime={"openai_client": object()},
            )

        self.assertEqual(embedding_calls, [["Clean title one", "Clean summary one", "Clean title two"]])
        self.assertEqual(len(searched_blobs), 3)
        self.assertEqual(metrics["config"]["query_count"], 3)

    def test_evaluate_retrieval_metrics_reports_average_query_latency(self):
        article_rows = [
            {
                "article_id": "article-one",
                "title": "Database title one",
                "published_at": "2026-05-01T10:00:00+00:00",
            },
            {
                "article_id": "article-two",
                "title": "Database title two",
                "published_at": "2026-05-02T10:00:00+00:00",
            },
        ]
        clean_articles = {
            "articles_by_id": {
                "article-one": {
                    "title": "Clean title one",
                    "summary": "",
                },
                "article-two": {
                    "title": "Clean title two",
                    "summary": "",
                },
            }
        }
        recipe = {
            "embedding_model": "text-embedding-3-small",
        }
        retrieval_options = {
            "enabled": True,
            "sample_size": 2,
            "top_k": 10,
            "search_mode": "ann",
        }
        perf_counter_values = [10.0, 10.004, 20.0, 20.010]

        def fake_search(query, top_k, search_mode):
            return []

        with patch("knowledge_bases.evaluation.retrieval_metrics.time.perf_counter", side_effect=perf_counter_values):
            metrics = evaluate_retrieval_metrics(
                None,
                recipe,
                article_rows,
                clean_articles,
                retrieval_options,
                retrieval_search_function=fake_search,
            )

        self.assertAlmostEqual(metrics["config"]["query_latency_ms"], 7.0)

    def test_reciprocal_rank_scores_rank_one_rank_five_and_missing_matches(self):
        self.assertEqual(
            calculate_reciprocal_rank(
                "article-one",
                [
                    make_result("article-one", 0, "matching chunk"),
                    make_result("article-two", 0, "other chunk"),
                ],
            ),
            1.0,
        )
        self.assertEqual(
            calculate_reciprocal_rank(
                "article-one",
                [
                    make_result("article-two", 0, "other 1"),
                    make_result("article-three", 0, "other 2"),
                    make_result("article-four", 0, "other 3"),
                    make_result("article-five", 0, "other 4"),
                    make_result("article-one", 0, "matching chunk"),
                ],
            ),
            0.2,
        )
        self.assertEqual(
            calculate_reciprocal_rank(
                "article-one",
                [
                    make_result("article-two", 0, "other 1"),
                    make_result("article-three", 0, "other 2"),
                ],
            ),
            0.0,
        )

    def test_self_retrieval_metrics_average_title_summary_and_combined_queries(self):
        query_results = [
            {
                "query": make_query("article-one", "title"),
                "results": [
                    make_result("article-one", 0, "matching title chunk"),
                    make_result("article-two", 0, "other chunk"),
                ],
            },
            {
                "query": make_query("article-one", "summary"),
                "results": [
                    make_result("article-two", 0, "other 1"),
                    make_result("article-three", 0, "other 2"),
                    make_result("article-four", 0, "other 3"),
                    make_result("article-five", 0, "other 4"),
                    make_result("article-one", 0, "matching summary chunk"),
                ],
            },
            {
                "query": make_query("article-six", "title"),
                "results": [
                    make_result("article-two", 0, "other 1"),
                    make_result("article-three", 0, "other 2"),
                ],
            },
        ]

        metrics = aggregate_retrieval_query_results(query_results, 3, 10, "exact")

        self.assertAlmostEqual(metrics["self_retrieval"]["title_mrr"], 0.5)
        self.assertAlmostEqual(metrics["self_retrieval"]["summary_mrr"], 0.2)
        self.assertAlmostEqual(metrics["self_retrieval"]["combined_mrr"], 0.4)
        self.assertAlmostEqual(metrics["self_retrieval"]["combined_top_5_rate"], 2 / 3)
        self.assertAlmostEqual(metrics["self_retrieval"]["combined_top_10_rate"], 2 / 3)
        self.assertAlmostEqual(metrics["thesis_retrieval"]["article_self_retrieval_top_5_rate"], 2 / 3)
        self.assertIsNotNone(metrics["thesis_retrieval"]["story_level_top_k_diversity"])

    def test_duplicate_chunks_increase_duplicate_text_share(self):
        query_results = [
            {
                "query": make_query("article-one", "title"),
                "results": [
                    make_result("article-one", 0, "Repeated text"),
                    make_result("article-two", 0, "Repeated   text"),
                    make_result("article-three", 0, "Different text"),
                ],
            }
        ]

        metrics = aggregate_retrieval_query_results(query_results, 1, 10, "exact")

        self.assertAlmostEqual(metrics["context_efficiency"]["duplicate_text_share"], 1 / 3)

    def test_same_article_repeated_chunks_increase_crowding(self):
        query_results = [
            {
                "query": make_query("article-one", "title"),
                "results": [
                    make_result("article-one", 0, "first chunk"),
                    make_result("article-one", 2, "third chunk"),
                    make_result("article-two", 0, "other chunk"),
                ],
            }
        ]

        metrics = aggregate_retrieval_query_results(query_results, 1, 10, "exact")

        self.assertAlmostEqual(metrics["top_k_crowding"]["max_same_article_share"], 2 / 3)

    def test_adjacent_chunk_indexes_increase_pair_count_and_overlap_waste(self):
        query_results = [
            {
                "query": make_query("article-one", "title"),
                "results": [
                    make_result("article-one", 0, "abc def ghi"),
                    make_result("article-one", 1, "ghi jkl mno"),
                    make_result("article-one", 3, "not adjacent"),
                    make_result("article-two", 0, "other chunk"),
                ],
            }
        ]

        metrics = aggregate_retrieval_query_results(query_results, 1, 10, "exact")

        self.assertEqual(metrics["top_k_crowding"]["adjacent_chunk_pair_count"], 1)
        self.assertGreater(metrics["context_efficiency"]["overlap_waste_rate"], 0)


if __name__ == "__main__":
    unittest.main()
