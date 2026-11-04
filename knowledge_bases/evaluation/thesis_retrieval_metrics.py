"""
Retrieval-derived thesis metrics for knowledge-base evaluation.
"""

import math

from knowledge_bases.build_knowledge_base import parse_timestamp_to_epoch
from knowledge_bases.evaluation.utils import average_or_none
from knowledge_bases.evaluation.utils import safe_rate


def make_empty_thesis_retrieval_metrics():
    """
    Create empty retrieval-derived thesis metric values.

    PARAMETERS:
    - None

    RETURNS:
    - Thesis retrieval metric dictionary
    """
    return {
        "story_level_top_k_diversity": None,
        "article_self_retrieval_top_5_rate": None,
        "hard_negative_separation_margin": None,
        "retrieval_hubness_rate": None,
        "recency_aware_retrieval_score": None,
    }


def calculate_thesis_retrieval_metrics(query_results, top_k, config):
    """
    Calculate retrieval-derived thesis metrics.

    PARAMETERS:
    - query_results: List of query/result dictionaries
    - top_k: Number of ranked results to inspect
    - config: Thesis metric configuration dictionary

    RETURNS:
    - Thesis retrieval metric dictionary
    """
    top_k_query_results = limit_query_results_for_top_k(query_results, top_k)

    return {
        "story_level_top_k_diversity": calculate_story_level_top_k_diversity(query_results, top_k),
        "article_self_retrieval_top_5_rate": calculate_article_self_retrieval_top_5_rate(query_results),
        "hard_negative_separation_margin": calculate_hard_negative_separation_margin(query_results),
        "retrieval_hubness_rate": calculate_retrieval_hubness_rate(query_results, top_k, config),
        "recency_aware_retrieval_score": calculate_recency_aware_retrieval_score(top_k_query_results, config),
    }


def limit_query_results_for_top_k(query_results, top_k):
    """
    Copy query results with each result list limited to top-k.
    """
    limit = safe_positive_limit(top_k)
    limited_query_results = []

    for query_result in query_results:
        limited_query_results.append(
            {
                "query": query_result.get("query", {}),
                "results": query_result.get("results", [])[:limit],
            }
        )

    return limited_query_results


def calculate_article_self_retrieval_top_5_rate(query_results):
    """
    Count how often each query retrieves its own article in the first five results.

    PARAMETERS:
    - query_results: List of query/result dictionaries

    RETURNS:
    - Hit rate, or None
    """
    hit_count = 0
    query_count = 0

    for query_result in query_results:
        query = query_result.get("query", {})
        results = query_result.get("results", [])
        article_id = str(query.get("article_id", "")).strip()
        if not article_id:
            continue

        query_count = query_count + 1
        matching_rank = find_first_matching_rank(results, article_id, 5)
        if matching_rank is not None:
            hit_count = hit_count + 1

    return safe_rate(hit_count, query_count)


def calculate_story_level_top_k_diversity(query_results, top_k):
    """
    Average the distinct-article share inside each query's top-k results.

    PARAMETERS:
    - query_results: List of query/result dictionaries
    - top_k: Number of ranked results to inspect

    RETURNS:
    - Average diversity, or None
    """
    limit = safe_positive_limit(top_k)
    diversity_scores = []

    for query_result in query_results:
        results = query_result.get("results", [])[:limit]
        if not results:
            continue

        article_ids = {}
        for result in results:
            article_id = str(result.get("article_id", "")).strip()
            if article_id:
                article_ids[article_id] = True

        diversity_scores.append(len(article_ids) / len(results))

    return average_or_none(diversity_scores)


def calculate_hard_negative_separation_margin(query_results):
    """
    Compare the correct article distance with the closest wrong article distance.

    PARAMETERS:
    - query_results: List of query/result dictionaries

    RETURNS:
    - Average margin, or None
    """
    margins = []

    for query_result in query_results:
        query = query_result.get("query", {})
        results = query_result.get("results", [])
        article_id = str(query.get("article_id", "")).strip()
        if not article_id:
            continue

        best_correct_distance = None
        best_wrong_distance = None

        for result in results:
            distance = safe_float(result.get("distance"))
            if distance is None:
                continue

            result_article_id = str(result.get("article_id", "")).strip()
            if result_article_id == article_id:
                if best_correct_distance is None or distance < best_correct_distance:
                    best_correct_distance = distance
            else:
                if best_wrong_distance is None or distance < best_wrong_distance:
                    best_wrong_distance = distance

        if best_wrong_distance is None:
            continue

        if best_correct_distance is None:
            margins.append(0.0)
            continue

        margins.append(best_wrong_distance - best_correct_distance)

    return average_or_none(margins)


def calculate_retrieval_hubness_rate(query_results, top_k, config):
    """
    Measure how much of the top-k space is taken by repeated hub articles.

    PARAMETERS:
    - query_results: List of query/result dictionaries
    - top_k: Number of ranked results to inspect
    - config: Thesis metric configuration dictionary

    RETURNS:
    - Hub slot rate, or None
    """
    limit = safe_positive_limit(top_k)
    query_count = len(query_results)
    if query_count == 0:
        return None

    query_hits_by_article_id = {}
    result_slots = []

    for query_result in query_results:
        seen_in_query = {}
        results = query_result.get("results", [])[:limit]
        for result in results:
            article_id = str(result.get("article_id", "")).strip()
            if not article_id:
                continue

            result_slots.append(article_id)
            seen_in_query[article_id] = True

        for article_id in seen_in_query:
            if article_id not in query_hits_by_article_id:
                query_hits_by_article_id[article_id] = 0
            query_hits_by_article_id[article_id] = query_hits_by_article_id[article_id] + 1

    if not result_slots:
        return None

    hub_share_threshold = safe_float(config.get("hubness_query_share_threshold"))
    if hub_share_threshold is None:
        hub_share_threshold = 0.10

    hub_article_ids = {}
    for article_id in query_hits_by_article_id:
        article_query_share = query_hits_by_article_id[article_id] / query_count
        if article_query_share > hub_share_threshold:
            hub_article_ids[article_id] = True

    hub_slot_count = 0
    for article_id in result_slots:
        if article_id in hub_article_ids:
            hub_slot_count = hub_slot_count + 1

    return safe_rate(hub_slot_count, len(result_slots))


def calculate_recency_aware_retrieval_score(query_results, config):
    """
    Combine result rank and age decay.

    PARAMETERS:
    - query_results: List of query/result dictionaries
    - config: Thesis metric configuration dictionary

    RETURNS:
    - Average recency-aware score, or None
    """
    half_life_days = safe_float(config.get("recency_half_life_days"))
    if half_life_days is None:
        half_life_days = 14.0
    if half_life_days <= 0:
        return None

    query_scores = []

    for query_result in query_results:
        query = query_result.get("query", {})
        results = query_result.get("results", [])
        reference_timestamp = parse_timestamp_to_epoch(query.get("published_at"))

        if reference_timestamp is None:
            continue

        result_scores = []
        for rank, result in enumerate(results, start=1):
            result_timestamp = parse_timestamp_to_epoch(result.get("published_at"))
            if result_timestamp is None:
                continue

            rank_credit = 1 / rank
            age_seconds = reference_timestamp - result_timestamp
            age_days = max(0.0, age_seconds / 86400)
            age_decay = 0.5 ** (age_days / half_life_days)
            result_scores.append(rank_credit * age_decay)

        query_score = average_or_none(result_scores)
        if query_score is not None:
            query_scores.append(query_score)

    return average_or_none(query_scores)


def find_first_matching_rank(results, article_id, limit):
    """
    Find the first rank where the result article id matches the target article id.

    PARAMETERS:
    - results: Ranked result dictionaries
    - article_id: Target article id
    - limit: Maximum number of results to inspect

    RETURNS:
    - 1-based rank, or None
    """
    expected_article_id = str(article_id).strip()
    if not expected_article_id:
        return None

    limited_results = results[:safe_positive_limit(limit)]
    for position, result in enumerate(limited_results, start=1):
        result_article_id = str(result.get("article_id", "")).strip()
        if result_article_id == expected_article_id:
            return position

    return None


def safe_float(value):
    """
    Convert a value to a finite float when possible.

    PARAMETERS:
    - value: Value to convert

    RETURNS:
    - Float, or None
    """
    if value is None:
        return None

    try:
        number = float(value)
    except Exception:
        return None

    if math.isnan(number):
        return None

    if math.isinf(number):
        return None

    return number


def safe_positive_limit(value):
    """
    Convert a limit value to a non-negative integer.
    """
    try:
        limit = int(value)
    except Exception:
        return 0

    if limit < 0:
        return 0

    return limit
