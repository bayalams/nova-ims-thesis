"""
Opt-in retrieval metrics for knowledge-base evaluation.
"""

import time

from knowledge_bases.embedding.openai_embeddings import build_embedding_client
from knowledge_bases.embedding.openai_embeddings import create_embedding_batch
from knowledge_bases.embedding.openai_embeddings import estimate_input_tokens
from knowledge_bases.evaluation.constants import DEFAULT_THESIS_METRIC_CONFIG
from knowledge_bases.evaluation.metrics import count_suffix_prefix_overlap
from knowledge_bases.evaluation.thesis_retrieval_metrics import calculate_thesis_retrieval_metrics
from knowledge_bases.evaluation.thesis_retrieval_metrics import make_empty_thesis_retrieval_metrics
from knowledge_bases.evaluation.utils import average_or_none
from knowledge_bases.evaluation.utils import normalize_text_for_comparison
from knowledge_bases.evaluation.utils import safe_int
from knowledge_bases.evaluation.utils import safe_rate
from knowledge_bases.retrieval.search_sqlite import search_ann
from knowledge_bases.retrieval.search_sqlite import search_exact
from knowledge_bases.storage.sqlite_kb import find_vec1_extension
from knowledge_bases.storage.sqlite_kb import load_vec1_extension
from knowledge_bases.storage.sqlite_kb import pack_vector


DEFAULT_RETRIEVAL_SAMPLE_SIZE = 100
DEFAULT_RETRIEVAL_TOP_K = 10
DEFAULT_RETRIEVAL_SEARCH_MODE = "ann"
DEFAULT_RETRIEVAL_EMBEDDING_BATCH_SIZE = 50
DEFAULT_RETRIEVAL_EMBEDDING_MAX_BATCH_TOKENS = 100000


def make_retrieval_options(enabled, sample_size, top_k, search_mode):
    """
    Create retrieval metric options from CLI values.

    PARAMETERS:
    - enabled: Whether retrieval metrics should run
    - sample_size: Number of indexed articles to sample
    - top_k: Number of results per query
    - search_mode: exact or ann

    RETURNS:
    - Options dictionary
    """
    return {
        "enabled": enabled,
        "sample_size": sample_size,
        "top_k": top_k,
        "search_mode": search_mode,
    }


def make_not_requested_retrieval_metrics():
    """
    Create the retrieval metric placeholder for normal evaluations.

    PARAMETERS:
    - None

    RETURNS:
    - Retrieval metrics dictionary
    """
    return {
        "status": "not_requested",
        "config": {},
        "self_retrieval": make_empty_self_retrieval_metrics(),
        "context_efficiency": make_empty_context_efficiency_metrics(),
        "top_k_crowding": make_empty_top_k_crowding_metrics(),
        "thesis_retrieval": make_empty_thesis_retrieval_metrics(),
    }


def make_error_retrieval_metrics(retrieval_options, error):
    """
    Create a retrieval metric error report.

    PARAMETERS:
    - retrieval_options: Retrieval metric options
    - error: Exception that stopped retrieval evaluation

    RETURNS:
    - Retrieval metrics dictionary
    """
    return {
        "status": "error",
        "error": str(error),
        "config": make_retrieval_config(
            retrieval_options.get("sample_size", DEFAULT_RETRIEVAL_SAMPLE_SIZE),
            retrieval_options.get("top_k", DEFAULT_RETRIEVAL_TOP_K),
            retrieval_options.get("search_mode", DEFAULT_RETRIEVAL_SEARCH_MODE),
            0,
            0,
            0,
            None,
        ),
        "self_retrieval": make_empty_self_retrieval_metrics(),
        "context_efficiency": make_empty_context_efficiency_metrics(),
        "top_k_crowding": make_empty_top_k_crowding_metrics(),
        "thesis_retrieval": make_empty_thesis_retrieval_metrics(),
    }


def evaluate_retrieval_metrics(
    connection,
    recipe,
    article_rows,
    clean_articles,
    retrieval_options,
    embedding_cache=None,
    retrieval_runtime=None,
    retrieval_search_function=None,
):
    """
    Evaluate retrieval metrics for one recipe.

    PARAMETERS:
    - connection: Open SQLite connection for the KB
    - recipe: Recipe dictionary
    - article_rows: Indexed article rows
    - clean_articles: Clean article cache
    - retrieval_options: Retrieval metric options
    - embedding_cache: Kept for older test hooks; retrieval queries are batch embedded per recipe
    - retrieval_runtime: Shared mutable runtime values
    - retrieval_search_function: Optional fake search function for tests

    RETURNS:
    - Retrieval metrics dictionary
    """
    sample_size = retrieval_options.get("sample_size", DEFAULT_RETRIEVAL_SAMPLE_SIZE)
    top_k = retrieval_options.get("top_k", DEFAULT_RETRIEVAL_TOP_K)
    search_mode = retrieval_options.get("search_mode", DEFAULT_RETRIEVAL_SEARCH_MODE)

    queries = select_retrieval_queries(article_rows, clean_articles, sample_size)
    print(f"[INFO] Retrieval metric queries: {len(queries)}", flush=True)

    if retrieval_runtime is None:
        retrieval_runtime = {}

    if retrieval_search_function is None and queries:
        vec1_extension_path = find_vec1_extension()
        load_vec1_extension(connection, vec1_extension_path)
        embed_retrieval_queries(recipe, queries, retrieval_runtime)

    query_results = []
    query_latency_values = []
    for position, query in enumerate(queries, start=1):
        print(
            f"[{position}/{len(queries)}] Retrieval query: {query['query_type']} {query['article_id']}",
            flush=True,
        )
        query_started_at = time.perf_counter()
        results = run_retrieval_query(
            connection,
            recipe,
            query,
            top_k,
            search_mode,
            retrieval_search_function,
        )
        query_elapsed_ms = (time.perf_counter() - query_started_at) * 1000
        query_latency_values.append(query_elapsed_ms)
        query_results.append(
            {
                "query": query,
                "results": results,
            }
        )

    query_latency_ms = average_or_none(query_latency_values)
    return aggregate_retrieval_query_results(query_results, sample_size, top_k, search_mode, query_latency_ms)


def select_retrieval_queries(article_rows, clean_articles, sample_size):
    """
    Select title and summary queries from the first N indexed articles.

    PARAMETERS:
    - article_rows: Indexed article rows
    - clean_articles: Clean article cache
    - sample_size: Number of sorted article ids to use

    RETURNS:
    - List of query dictionaries
    """
    sorted_article_rows = sorted(article_rows, key=get_article_sort_key)
    selected_rows = sorted_article_rows[:sample_size]
    queries = []

    for article_row in selected_rows:
        article_id = str(article_row.get("article_id", "")).strip()
        if not article_id:
            continue

        clean_record = clean_articles["articles_by_id"].get(article_id, {})
        clean_title = str(clean_record.get("title", "")).strip()
        db_title = str(article_row.get("title", "")).strip()
        published_at = str(article_row.get("published_at", "")).strip()
        summary = str(clean_record.get("summary", "")).strip()

        title = clean_title
        if not title:
            title = db_title

        if title:
            queries.append(
                {
                    "article_id": article_id,
                    "published_at": published_at,
                    "query_type": "title",
                    "query_text": title,
                }
            )

        if summary:
            queries.append(
                {
                    "article_id": article_id,
                    "published_at": published_at,
                    "query_type": "summary",
                    "query_text": summary,
                }
            )

    return queries


def get_article_sort_key(article_row):
    """
    Return a stable article id sort key.

    PARAMETERS:
    - article_row: Article row dictionary

    RETURNS:
    - Sort key string
    """
    return str(article_row.get("article_id", ""))


def run_retrieval_query(
    connection,
    recipe,
    query,
    top_k,
    search_mode,
    retrieval_search_function,
):
    """
    Run one retrieval metric query.

    PARAMETERS:
    - connection: Open SQLite connection
    - recipe: Recipe dictionary
    - query: Query dictionary
    - top_k: Number of results
    - search_mode: exact or ann
    - retrieval_search_function: Optional fake search function for tests

    RETURNS:
    - Ranked result dictionaries
    """
    if retrieval_search_function is not None:
        return retrieval_search_function(query, top_k, search_mode)

    query_blob = query.get("query_blob")
    if query_blob is None:
        raise ValueError("Retrieval query is missing a precomputed embedding")

    if search_mode == "exact":
        return search_exact(connection, recipe, query_blob, top_k)

    return search_ann(connection, recipe, query_blob, top_k)


def embed_retrieval_queries(
    recipe,
    queries,
    retrieval_runtime,
    batch_size=DEFAULT_RETRIEVAL_EMBEDDING_BATCH_SIZE,
    max_batch_tokens=DEFAULT_RETRIEVAL_EMBEDDING_MAX_BATCH_TOKENS,
):
    """
    Embed retrieval metric query texts in batches.

    PARAMETERS:
    - recipe: Recipe dictionary
    - queries: Query dictionaries to update with query_blob
    - retrieval_runtime: Shared runtime values
    - batch_size: Maximum query texts per embedding request
    - max_batch_tokens: Maximum estimated tokens per embedding request

    RETURNS:
    - None
    """
    client = retrieval_runtime.get("embedding_client")
    if client is None:
        client = retrieval_runtime.get("openai_client")
    if client is None:
        client = build_embedding_client(recipe)
    retrieval_runtime["embedding_client"] = client

    query_batches = make_retrieval_embedding_batches(queries, batch_size, max_batch_tokens)
    for query_batch in query_batches:
        query_texts = []
        for query in query_batch:
            query_texts.append(query["query_text"])

        embedding_result = create_embedding_batch(client, query_texts, recipe)
        vectors = embedding_result["vectors"]
        if len(vectors) != len(query_batch):
            raise ValueError("Embedding provider returned the wrong number of retrieval query vectors")

        for index, query in enumerate(query_batch):
            query["query_blob"] = pack_vector(vectors[index])


def make_retrieval_embedding_batches(queries, batch_size, max_batch_tokens):
    """
    Split retrieval queries into safe embedding request batches.

    PARAMETERS:
    - queries: Query dictionaries
    - batch_size: Maximum query texts in one request
    - max_batch_tokens: Maximum estimated tokens in one request

    RETURNS:
    - List of query batches
    """
    batches = []
    current_batch = []
    current_tokens = 0

    for query in queries:
        query_tokens = estimate_input_tokens(query["query_text"])
        batch_is_full = len(current_batch) >= batch_size
        batch_would_exceed_tokens = current_tokens + query_tokens > max_batch_tokens

        if current_batch and (batch_is_full or batch_would_exceed_tokens):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(query)
        current_tokens = current_tokens + query_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


def aggregate_retrieval_query_results(query_results, sample_size, top_k, search_mode, query_latency_ms=None):
    """
    Aggregate ranked query results into retrieval metrics.

    PARAMETERS:
    - query_results: List of query/result dictionaries
    - sample_size: Configured sample size
    - top_k: Configured result count
    - search_mode: exact or ann
    - query_latency_ms: Average local search latency per query, excluding embedding

    RETURNS:
    - Retrieval metrics dictionary
    """
    title_scores = []
    summary_scores = []
    combined_scores = []
    top_5_hit_count = 0
    top_10_hit_count = 0
    title_query_count = 0
    summary_query_count = 0

    for query_result in query_results:
        query = query_result["query"]
        results = query_result["results"]
        query_type = query["query_type"]
        target_article_id = query["article_id"]
        reciprocal_rank = calculate_reciprocal_rank(target_article_id, results)
        matching_rank = find_first_matching_rank(target_article_id, results)

        if query_type == "title":
            title_scores.append(reciprocal_rank)
            title_query_count = title_query_count + 1

        if query_type == "summary":
            summary_scores.append(reciprocal_rank)
            summary_query_count = summary_query_count + 1

        combined_scores.append(reciprocal_rank)

        if matching_rank is not None and matching_rank <= 5:
            top_5_hit_count = top_5_hit_count + 1
        if matching_rank is not None and matching_rank <= 10:
            top_10_hit_count = top_10_hit_count + 1

    query_count = len(query_results)

    return {
        "status": "evaluated",
        "config": make_retrieval_config(
            sample_size,
            top_k,
            search_mode,
            query_count,
            title_query_count,
            summary_query_count,
            query_latency_ms,
        ),
        "self_retrieval": {
            "title_mrr": average_or_none(title_scores),
            "summary_mrr": average_or_none(summary_scores),
            "combined_mrr": average_or_none(combined_scores),
            "combined_top_5_rate": safe_rate(top_5_hit_count, query_count),
            "combined_top_10_rate": safe_rate(top_10_hit_count, query_count),
        },
        "context_efficiency": calculate_context_efficiency(query_results),
        "top_k_crowding": calculate_top_k_crowding(query_results),
        "thesis_retrieval": calculate_thesis_retrieval_metrics(query_results, top_k, DEFAULT_THESIS_METRIC_CONFIG),
    }


def make_retrieval_config(
    sample_size,
    top_k,
    search_mode,
    query_count,
    title_query_count,
    summary_query_count,
    query_latency_ms=None,
):
    """
    Create the retrieval metric config block.

    PARAMETERS:
    - sample_size: Configured article sample size
    - top_k: Configured retrieval result count
    - search_mode: exact or ann
    - query_count: Number of queries actually evaluated
    - title_query_count: Number of title queries
    - summary_query_count: Number of summary queries
    - query_latency_ms: Average local search latency per query, excluding embedding

    RETURNS:
    - Config dictionary
    """
    return {
        "sample_size": sample_size,
        "top_k": top_k,
        "search_mode": search_mode,
        "query_count": query_count,
        "title_query_count": title_query_count,
        "summary_query_count": summary_query_count,
        "query_latency_ms": query_latency_ms,
    }


def calculate_reciprocal_rank(target_article_id, results):
    """
    Calculate reciprocal rank for one self-retrieval query.

    PARAMETERS:
    - target_article_id: Expected article id
    - results: Ranked result dictionaries

    RETURNS:
    - 1 / rank, or 0.0 when no matching article is returned
    """
    matching_rank = find_first_matching_rank(target_article_id, results)

    if matching_rank is None:
        return 0.0

    return 1 / matching_rank


def find_first_matching_rank(target_article_id, results):
    """
    Find the first rank whose article id matches the query article.

    PARAMETERS:
    - target_article_id: Expected article id
    - results: Ranked result dictionaries

    RETURNS:
    - 1-based rank, or None
    """
    expected_article_id = str(target_article_id)

    for position, result in enumerate(results, start=1):
        if str(result.get("article_id", "")) == expected_article_id:
            return position

    return None


def calculate_context_efficiency(query_results):
    """
    Calculate retrieved-context efficiency metrics across all returned chunks.

    PARAMETERS:
    - query_results: List of query/result dictionaries

    RETURNS:
    - Context efficiency dictionary
    """
    result_count = 0
    unique_articles = {}
    unique_sources = {}
    unique_dates = {}
    seen_texts = {}
    duplicate_text_count = 0
    total_returned_characters = 0
    overlap_characters = 0

    for query_result in query_results:
        results = query_result["results"]
        overlap_characters = overlap_characters + count_adjacent_overlap_characters(results)

        for result in results:
            result_count = result_count + 1

            article_id = str(result.get("article_id", "")).strip()
            if article_id:
                unique_articles[article_id] = True

            source = str(result.get("source", "")).strip()
            if source:
                unique_sources[source] = True

            published_at = str(result.get("published_at", "")).strip()
            if published_at:
                unique_dates[published_at[:10]] = True

            chunk_text = str(result.get("chunk_text", ""))
            total_returned_characters = total_returned_characters + len(chunk_text)
            normalized_text = normalize_text_for_comparison(chunk_text)
            if normalized_text in seen_texts:
                duplicate_text_count = duplicate_text_count + 1
            else:
                seen_texts[normalized_text] = True

    return {
        "unique_article_share": safe_rate(len(unique_articles), result_count),
        "unique_source_share": safe_rate(len(unique_sources), result_count),
        "unique_date_share": safe_rate(len(unique_dates), result_count),
        "duplicate_text_share": safe_rate(duplicate_text_count, result_count),
        "overlap_waste_rate": safe_rate(overlap_characters, total_returned_characters),
    }


def calculate_top_k_crowding(query_results):
    """
    Calculate top-k crowding metrics across ranked query results.

    PARAMETERS:
    - query_results: List of query/result dictionaries

    RETURNS:
    - Top-k crowding dictionary
    """
    max_same_article_shares = []
    unique_articles_top_5_counts = []
    unique_sources_top_5_counts = []
    unique_articles_top_10_counts = []
    unique_sources_top_10_counts = []
    adjacent_chunk_pair_count = 0

    for query_result in query_results:
        results = query_result["results"]
        max_same_article_shares.append(calculate_max_same_article_share(results))
        unique_articles_top_5_counts.append(count_unique_field(results[:5], "article_id"))
        unique_sources_top_5_counts.append(count_unique_field(results[:5], "source"))
        unique_articles_top_10_counts.append(count_unique_field(results[:10], "article_id"))
        unique_sources_top_10_counts.append(count_unique_field(results[:10], "source"))
        adjacent_chunk_pair_count = adjacent_chunk_pair_count + count_adjacent_chunk_pairs(results)

    return {
        "max_same_article_share": average_or_none(max_same_article_shares),
        "unique_articles_top_5": average_or_none(unique_articles_top_5_counts),
        "unique_sources_top_5": average_or_none(unique_sources_top_5_counts),
        "unique_articles_top_10": average_or_none(unique_articles_top_10_counts),
        "unique_sources_top_10": average_or_none(unique_sources_top_10_counts),
        "adjacent_chunk_pair_count": adjacent_chunk_pair_count,
    }


def calculate_max_same_article_share(results):
    """
    Calculate the largest same-article share for one ranked result list.

    PARAMETERS:
    - results: Ranked result dictionaries

    RETURNS:
    - Share, or 0.0 for an empty result list
    """
    if not results:
        return 0.0

    counts_by_article_id = {}
    for result in results:
        article_id = str(result.get("article_id", "")).strip()
        if article_id not in counts_by_article_id:
            counts_by_article_id[article_id] = 0
        counts_by_article_id[article_id] = counts_by_article_id[article_id] + 1

    max_count = 0
    for article_id in counts_by_article_id:
        if counts_by_article_id[article_id] > max_count:
            max_count = counts_by_article_id[article_id]

    return safe_rate(max_count, len(results))


def count_unique_field(results, field_name):
    """
    Count unique nonblank field values in one result slice.

    PARAMETERS:
    - results: Ranked result dictionaries
    - field_name: Field to count

    RETURNS:
    - Unique value count
    """
    unique_values = {}

    for result in results:
        value = str(result.get(field_name, "")).strip()
        if value:
            unique_values[value] = True

    return len(unique_values)


def count_adjacent_chunk_pairs(results):
    """
    Count adjacent ranked results from neighboring chunks of the same article.

    PARAMETERS:
    - results: Ranked result dictionaries

    RETURNS:
    - Integer pair count
    """
    adjacent_count = 0

    for position in range(1, len(results)):
        if results_are_neighboring_article_chunks(results[position - 1], results[position]):
            adjacent_count = adjacent_count + 1

    return adjacent_count


def count_adjacent_overlap_characters(results):
    """
    Count repeated overlap characters in adjacent same-article chunks.

    PARAMETERS:
    - results: Ranked result dictionaries

    RETURNS:
    - Overlap character count
    """
    overlap_characters = 0

    for position in range(1, len(results)):
        previous_result = results[position - 1]
        current_result = results[position]

        if not results_are_neighboring_article_chunks(previous_result, current_result):
            continue

        previous_text = str(previous_result.get("chunk_text", ""))
        current_text = str(current_result.get("chunk_text", ""))
        previous_index = safe_int(previous_result.get("chunk_index"))
        current_index = safe_int(current_result.get("chunk_index"))

        if previous_index is None or current_index is None:
            continue

        if previous_index < current_index:
            overlap_characters = overlap_characters + count_suffix_prefix_overlap(previous_text, current_text)
        else:
            overlap_characters = overlap_characters + count_suffix_prefix_overlap(current_text, previous_text)

    return overlap_characters


def results_are_neighboring_article_chunks(first_result, second_result):
    """
    Check whether two ranked results are neighboring chunks from one article.

    PARAMETERS:
    - first_result: Previous ranked result
    - second_result: Current ranked result

    RETURNS:
    - True when they are same-article neighboring chunks
    """
    first_article_id = str(first_result.get("article_id", "")).strip()
    second_article_id = str(second_result.get("article_id", "")).strip()

    if not first_article_id or first_article_id != second_article_id:
        return False

    first_index = safe_int(first_result.get("chunk_index"))
    second_index = safe_int(second_result.get("chunk_index"))
    if first_index is None or second_index is None:
        return False

    return abs(first_index - second_index) == 1


def make_empty_self_retrieval_metrics():
    """
    Create empty self-retrieval metrics.

    PARAMETERS:
    - None

    RETURNS:
    - Self-retrieval dictionary
    """
    return {
        "title_mrr": None,
        "summary_mrr": None,
        "combined_mrr": None,
        "combined_top_5_rate": None,
        "combined_top_10_rate": None,
    }


def make_empty_context_efficiency_metrics():
    """
    Create empty context efficiency metrics.

    PARAMETERS:
    - None

    RETURNS:
    - Context efficiency dictionary
    """
    return {
        "unique_article_share": None,
        "unique_source_share": None,
        "unique_date_share": None,
        "duplicate_text_share": None,
        "overlap_waste_rate": None,
    }


def make_empty_top_k_crowding_metrics():
    """
    Create empty top-k crowding metrics.

    PARAMETERS:
    - None

    RETURNS:
    - Top-k crowding dictionary
    """
    return {
        "max_same_article_share": None,
        "unique_articles_top_5": None,
        "unique_sources_top_5": None,
        "unique_articles_top_10": None,
        "unique_sources_top_10": None,
        "adjacent_chunk_pair_count": None,
    }
