"""
Metric calculations for knowledge-base evaluation.
"""

from knowledge_bases.evaluation.articles import find_source_text
from knowledge_bases.evaluation.articles import get_first_paragraph
from knowledge_bases.evaluation.constants import BOILERPLATE_PHRASES
from knowledge_bases.evaluation.constants import REQUIRED_METADATA_FIELDS
from knowledge_bases.evaluation.database import count_rows_with_manifest_fallback
from knowledge_bases.evaluation.utils import average_or_none
from knowledge_bases.evaluation.utils import get_database_size_bytes
from knowledge_bases.evaluation.utils import is_missing_value
from knowledge_bases.evaluation.utils import make_number_summary
from knowledge_bases.evaluation.utils import normalize_text_for_comparison
from knowledge_bases.evaluation.utils import safe_int
from knowledge_bases.evaluation.utils import safe_rate


def make_missing_database_sanity_metrics(clean_articles, manifest):
    """
    Create sanity metrics for a recipe that has not been built yet.

    PARAMETERS:
    - clean_articles: Clean article lookup dictionary
    - manifest: Build manifest dictionary

    RETURNS:
    - Sanity metric dictionary
    """
    expected_article_count = get_expected_article_count(manifest, clean_articles["valid_count"])

    return {
        "input_clean_article_count": clean_articles["valid_count"],
        "input_invalid_article_count": clean_articles["invalid_count"],
        "expected_article_count": expected_article_count,
        "article_count": 0,
        "article_coverage_rate": safe_rate(0, expected_article_count),
        "chunk_count": 0,
        "vector_count": 0,
        "chunk_size_characters": make_number_summary([]),
        "chunks_per_article": make_number_summary([]),
        "metadata_missing_rates": make_empty_metadata_missing_rates(),
        "embedding_batch_count": 0,
        "failed_embedding_batch_count": 0,
        "embedding_failure_rate": None,
        "db_size_bytes": 0,
        "build_time_seconds": manifest.get("build_time_seconds"),
        "query_latency_ms": None,
        "failed_to_index_article_count": expected_article_count,
        "skipped_too_large_article_count": manifest.get("skipped_too_large_article_count", 0),
    }


def make_sanity_metrics(
    connection,
    table_names,
    article_columns,
    article_rows,
    chunk_rows,
    clean_articles,
    manifest,
    db_path,
):
    """
    Calculate required sanity metrics from one KB database.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_names: Existing table names
    - article_columns: Existing article table columns
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries
    - clean_articles: Clean article lookup dictionary
    - manifest: Build manifest dictionary
    - db_path: Path to kb.sqlite

    RETURNS:
    - Sanity metric dictionary
    """
    article_count = len(article_rows)
    chunk_count = len(chunk_rows)
    vector_count = count_rows_with_manifest_fallback(connection, table_names, "vec1_chunks", manifest, "vector_count")
    expected_article_count = get_expected_article_count(manifest, clean_articles["valid_count"])
    failed_to_index_article_count = expected_article_count - article_count
    if failed_to_index_article_count < 0:
        failed_to_index_article_count = 0

    chunk_lengths = []
    for chunk_row in chunk_rows:
        chunk_lengths.append(len(str(chunk_row["chunk_text"])))

    chunks_per_article = count_chunks_per_article(article_rows, chunk_rows)
    metadata_missing_rates = calculate_metadata_missing_rates(article_rows, article_columns)
    embedding_metrics = calculate_embedding_metrics(connection, table_names)

    return {
        "input_clean_article_count": clean_articles["valid_count"],
        "input_invalid_article_count": clean_articles["invalid_count"],
        "expected_article_count": expected_article_count,
        "article_count": article_count,
        "article_coverage_rate": safe_rate(article_count, expected_article_count),
        "chunk_count": chunk_count,
        "vector_count": vector_count,
        "chunk_size_characters": make_number_summary(chunk_lengths),
        "chunks_per_article": make_number_summary(chunks_per_article),
        "metadata_missing_rates": metadata_missing_rates,
        "embedding_batch_count": embedding_metrics["embedding_batch_count"],
        "failed_embedding_batch_count": embedding_metrics["failed_embedding_batch_count"],
        "embedding_failure_rate": embedding_metrics["embedding_failure_rate"],
        "db_size_bytes": get_database_size_bytes(db_path),
        "build_time_seconds": manifest.get("build_time_seconds"),
        "query_latency_ms": None,
        "failed_to_index_article_count": failed_to_index_article_count,
        "skipped_too_large_article_count": manifest.get("skipped_too_large_article_count", 0),
    }


def make_thesis_metrics(article_rows, chunk_rows, clean_articles):
    """
    Calculate deterministic main thesis metrics.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries
    - clean_articles: Clean article lookup dictionary

    RETURNS:
    - Thesis metric dictionary
    """
    metrics = {
        "article_reconstruction_accuracy": calculate_article_reconstruction_accuracy(
            article_rows,
            chunk_rows,
            clean_articles,
        ),
        "lead_paragraph_intact_rate": calculate_lead_paragraph_intact_rate(
            article_rows,
            chunk_rows,
            clean_articles,
        ),
        "boundary_break_rate": calculate_boundary_break_rate(article_rows, chunk_rows, clean_articles),
        # Entity and retrieval thesis metrics are filled by evaluator wiring later.
        "entity_pair_preservation_rate": None,
        "boilerplate_contamination_rate": calculate_boilerplate_contamination_rate(chunk_rows),
        "story_level_top_k_diversity": None,
        "article_self_retrieval_top_5_rate": None,
        "hard_negative_separation_margin": None,
        "retrieval_hubness_rate": None,
        "recency_aware_retrieval_score": None,
    }

    return metrics


def make_pending_thesis_metrics():
    """
    Create thesis metric placeholders when no DB exists.

    PARAMETERS:
    - None

    RETURNS:
    - Thesis metric dictionary
    """
    return {
        "article_reconstruction_accuracy": None,
        "lead_paragraph_intact_rate": None,
        "boundary_break_rate": None,
        "entity_pair_preservation_rate": None,
        "boilerplate_contamination_rate": None,
        "story_level_top_k_diversity": None,
        "article_self_retrieval_top_5_rate": None,
        "hard_negative_separation_margin": None,
        "retrieval_hubness_rate": None,
        "recency_aware_retrieval_score": None,
    }


def make_diagnostic_metrics(article_rows, chunk_rows):
    """
    Calculate supporting diagnostic metrics.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Diagnostic metric dictionary
    """
    return {
        "duplicate_chunk_rate": calculate_duplicate_chunk_rate(chunk_rows),
        "same_article_max_chunk_share": calculate_same_article_max_chunk_share(chunk_rows),
        "average_adjacent_overlap_rate": calculate_average_adjacent_overlap_rate(chunk_rows),
        "empty_chunk_rate": calculate_empty_chunk_rate(chunk_rows),
        "article_rows_with_zero_chunks": count_article_rows_with_zero_chunks(article_rows, chunk_rows),
    }


def make_empty_diagnostic_metrics():
    """
    Create empty diagnostics when no DB exists.

    PARAMETERS:
    - None

    RETURNS:
    - Diagnostic metric dictionary
    """
    return {
        "duplicate_chunk_rate": None,
        "same_article_max_chunk_share": None,
        "average_adjacent_overlap_rate": None,
        "empty_chunk_rate": None,
        "article_rows_with_zero_chunks": None,
    }


def get_expected_article_count(manifest, fallback_count):
    """
    Decide which article count should be used as the coverage denominator.

    PARAMETERS:
    - manifest: Build manifest dictionary
    - fallback_count: Clean article count from disk

    RETURNS:
    - Integer expected article count
    """
    for key in ["articles_after_filters", "articles_loaded"]:
        value = manifest.get(key)
        integer_value = safe_int(value)
        if integer_value is not None:
            return integer_value

    return fallback_count


def calculate_metadata_missing_rates(article_rows, article_columns):
    """
    Calculate missing metadata rates.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - article_columns: Existing article table columns

    RETURNS:
    - Dictionary of missing rates
    """
    if not article_rows:
        return make_empty_metadata_missing_rates()

    missing_counts = {}
    for field_name in REQUIRED_METADATA_FIELDS:
        missing_counts[field_name] = 0

    missing_any_count = 0

    for article_row in article_rows:
        missing_any = False

        for field_name in REQUIRED_METADATA_FIELDS:
            value = article_row.get(field_name)

            if field_name not in article_columns:
                value = None

            if is_missing_value(value):
                missing_counts[field_name] = missing_counts[field_name] + 1
                missing_any = True

        if missing_any:
            missing_any_count = missing_any_count + 1

    missing_rates = {}
    for field_name in REQUIRED_METADATA_FIELDS:
        missing_rates[field_name] = safe_rate(missing_counts[field_name], len(article_rows))

    missing_rates["any_required"] = safe_rate(missing_any_count, len(article_rows))
    return missing_rates


def make_empty_metadata_missing_rates():
    """
    Create empty metadata missing rates.

    PARAMETERS:
    - None

    RETURNS:
    - Dictionary with None rates
    """
    missing_rates = {}
    for field_name in REQUIRED_METADATA_FIELDS:
        missing_rates[field_name] = None

    missing_rates["any_required"] = None
    return missing_rates


def calculate_embedding_metrics(connection, table_names):
    """
    Calculate embedding batch failure metrics.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_names: Existing table names

    RETURNS:
    - Embedding metric dictionary
    """
    if "embedding_batches" not in table_names:
        return {
            "embedding_batch_count": 0,
            "failed_embedding_batch_count": 0,
            "embedding_failure_rate": None,
        }

    rows = connection.execute(
        """
        SELECT status
        FROM embedding_batches
        """
    ).fetchall()

    failed_count = 0
    for row in rows:
        status = str(row["status"]).strip().lower()
        if status != "success":
            failed_count = failed_count + 1

    return {
        "embedding_batch_count": len(rows),
        "failed_embedding_batch_count": failed_count,
        "embedding_failure_rate": safe_rate(failed_count, len(rows)),
    }


def count_chunks_per_article(article_rows, chunk_rows):
    """
    Count chunks for each article row.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - List of chunk counts
    """
    counts_by_article_id = {}
    for article_row in article_rows:
        counts_by_article_id[article_row["article_id"]] = 0

    for chunk_row in chunk_rows:
        article_id = chunk_row["article_id"]
        if article_id not in counts_by_article_id:
            counts_by_article_id[article_id] = 0
        counts_by_article_id[article_id] = counts_by_article_id[article_id] + 1

    counts = []
    for article_id in sorted(counts_by_article_id):
        counts.append(counts_by_article_id[article_id])

    return counts


def calculate_article_reconstruction_accuracy(article_rows, chunk_rows, clean_articles):
    """
    Estimate article reconstruction by measuring source text span coverage.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries
    - clean_articles: Clean article lookup dictionary

    RETURNS:
    - Average source span coverage across articles, or None
    """
    chunks_by_article_id = group_chunks_by_article_id(chunk_rows)
    article_scores = []

    for article_row in article_rows:
        source_text = find_source_text(article_row, clean_articles)
        if not source_text:
            continue

        article_chunks = chunks_by_article_id.get(article_row["article_id"], [])
        if not article_chunks:
            article_scores.append(0.0)
            continue

        intervals = []
        for chunk_row in article_chunks:
            start = safe_int(chunk_row["character_start"])
            end = safe_int(chunk_row["character_end"])
            if start is None or end is None:
                continue
            if start < 0:
                start = 0
            if end > len(source_text):
                end = len(source_text)
            if end > start:
                intervals.append([start, end])

        covered_characters = count_covered_characters(intervals)
        article_scores.append(safe_rate(covered_characters, len(source_text)))

    return average_or_none(article_scores)


def calculate_lead_paragraph_intact_rate(article_rows, chunk_rows, clean_articles):
    """
    Calculate how often the first chunk preserves the article lead paragraph.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries
    - clean_articles: Clean article lookup dictionary

    RETURNS:
    - Rate, or None
    """
    chunks_by_article_id = group_chunks_by_article_id(chunk_rows)
    checked_count = 0
    intact_count = 0

    for article_row in article_rows:
        source_text = find_source_text(article_row, clean_articles)
        if not source_text:
            continue

        lead_paragraph = get_first_paragraph(source_text)
        if not lead_paragraph:
            continue

        article_chunks = chunks_by_article_id.get(article_row["article_id"], [])
        if not article_chunks:
            continue

        first_chunk = article_chunks[0]
        checked_count = checked_count + 1

        normalized_lead = normalize_text_for_comparison(lead_paragraph)
        normalized_chunk = normalize_text_for_comparison(first_chunk["chunk_text"])
        if normalized_chunk.startswith(normalized_lead):
            intact_count = intact_count + 1

    return safe_rate(intact_count, checked_count)


def calculate_boundary_break_rate(article_rows, chunk_rows, clean_articles):
    """
    Calculate how often a chunk starts or ends inside a word.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries
    - clean_articles: Clean article lookup dictionary

    RETURNS:
    - Rate, or None
    """
    article_rows_by_id = {}
    for article_row in article_rows:
        article_rows_by_id[article_row["article_id"]] = article_row

    checked_count = 0
    broken_count = 0

    for chunk_row in chunk_rows:
        article_row = article_rows_by_id.get(chunk_row["article_id"])
        if article_row is None:
            continue

        source_text = find_source_text(article_row, clean_articles)
        if not source_text:
            continue

        start = safe_int(chunk_row["character_start"])
        end = safe_int(chunk_row["character_end"])
        if start is None or end is None:
            continue

        checked_count = checked_count + 1
        if chunk_has_word_boundary_break(source_text, start, end):
            broken_count = broken_count + 1

    return safe_rate(broken_count, checked_count)


def calculate_boilerplate_contamination_rate(chunk_rows):
    """
    Calculate how often chunks contain common boilerplate phrases.

    PARAMETERS:
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Rate, or None
    """
    if not chunk_rows:
        return None

    contaminated_count = 0

    for chunk_row in chunk_rows:
        chunk_text = str(chunk_row["chunk_text"]).lower()
        found_phrase = False

        for phrase in BOILERPLATE_PHRASES:
            if phrase in chunk_text:
                found_phrase = True

        if found_phrase:
            contaminated_count = contaminated_count + 1

    return safe_rate(contaminated_count, len(chunk_rows))


def calculate_duplicate_chunk_rate(chunk_rows):
    """
    Calculate the share of chunks whose normalized text repeats.

    PARAMETERS:
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Rate, or None
    """
    if not chunk_rows:
        return None

    seen_texts = {}
    duplicate_count = 0

    for chunk_row in chunk_rows:
        normalized_text = normalize_text_for_comparison(chunk_row["chunk_text"])
        if normalized_text in seen_texts:
            duplicate_count = duplicate_count + 1
        else:
            seen_texts[normalized_text] = True

    return safe_rate(duplicate_count, len(chunk_rows))


def calculate_same_article_max_chunk_share(chunk_rows):
    """
    Calculate the largest single-article share of all chunks.

    PARAMETERS:
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Rate, or None
    """
    if not chunk_rows:
        return None

    counts_by_article_id = {}
    for chunk_row in chunk_rows:
        article_id = chunk_row["article_id"]
        if article_id not in counts_by_article_id:
            counts_by_article_id[article_id] = 0
        counts_by_article_id[article_id] = counts_by_article_id[article_id] + 1

    max_count = 0
    for article_id in counts_by_article_id:
        if counts_by_article_id[article_id] > max_count:
            max_count = counts_by_article_id[article_id]

    return safe_rate(max_count, len(chunk_rows))


def calculate_average_adjacent_overlap_rate(chunk_rows):
    """
    Calculate average suffix-prefix overlap for adjacent chunks from the same article.

    PARAMETERS:
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Average overlap rate, or None
    """
    chunks_by_article_id = group_chunks_by_article_id(chunk_rows)
    overlap_rates = []

    for article_id in chunks_by_article_id:
        article_chunks = chunks_by_article_id[article_id]

        for position in range(1, len(article_chunks)):
            previous_text = str(article_chunks[position - 1]["chunk_text"])
            current_text = str(article_chunks[position]["chunk_text"])
            overlap_length = count_suffix_prefix_overlap(previous_text, current_text)
            denominator = min(len(previous_text), len(current_text))
            overlap_rates.append(safe_rate(overlap_length, denominator))

    return average_or_none(overlap_rates)


def calculate_empty_chunk_rate(chunk_rows):
    """
    Calculate the share of chunks with empty text.

    PARAMETERS:
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Rate, or None
    """
    if not chunk_rows:
        return None

    empty_count = 0
    for chunk_row in chunk_rows:
        if str(chunk_row["chunk_text"]).strip() == "":
            empty_count = empty_count + 1

    return safe_rate(empty_count, len(chunk_rows))


def count_article_rows_with_zero_chunks(article_rows, chunk_rows):
    """
    Count indexed article rows that have no chunk rows.

    PARAMETERS:
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Count
    """
    chunk_counts = count_chunks_per_article(article_rows, chunk_rows)
    zero_count = 0

    for chunk_count in chunk_counts:
        if chunk_count == 0:
            zero_count = zero_count + 1

    return zero_count


def group_chunks_by_article_id(chunk_rows):
    """
    Group chunks by article id.

    PARAMETERS:
    - chunk_rows: Chunk rows as dictionaries

    RETURNS:
    - Dictionary mapping article id to chunk rows
    """
    chunks_by_article_id = {}

    for chunk_row in chunk_rows:
        article_id = chunk_row["article_id"]
        if article_id not in chunks_by_article_id:
            chunks_by_article_id[article_id] = []
        chunks_by_article_id[article_id].append(chunk_row)

    for article_id in chunks_by_article_id:
        chunks_by_article_id[article_id].sort(key=get_chunk_index)

    return chunks_by_article_id


def get_chunk_index(chunk_row):
    """
    Return a chunk index for sorting.

    PARAMETERS:
    - chunk_row: Chunk row dictionary

    RETURNS:
    - Integer chunk index
    """
    chunk_index = safe_int(chunk_row.get("chunk_index"))
    if chunk_index is None:
        return 0
    return chunk_index


def chunk_has_word_boundary_break(source_text, start, end):
    """
    Check whether a chunk boundary cuts through a word.

    PARAMETERS:
    - source_text: Full article text
    - start: Chunk start offset
    - end: Chunk end offset

    RETURNS:
    - True if the chunk starts or ends inside a word
    """
    if start > 0 and start < len(source_text):
        previous_character = source_text[start - 1]
        current_character = source_text[start]
        if previous_character.isalnum() and current_character.isalnum():
            return True

    if end > 0 and end < len(source_text):
        previous_character = source_text[end - 1]
        current_character = source_text[end]
        if previous_character.isalnum() and current_character.isalnum():
            return True

    return False


def count_covered_characters(intervals):
    """
    Count covered characters from possibly overlapping intervals.

    PARAMETERS:
    - intervals: List of [start, end] pairs

    RETURNS:
    - Covered character count
    """
    if not intervals:
        return 0

    intervals.sort()
    covered_count = 0
    current_start = intervals[0][0]
    current_end = intervals[0][1]

    for position in range(1, len(intervals)):
        next_start = intervals[position][0]
        next_end = intervals[position][1]

        if next_start <= current_end:
            if next_end > current_end:
                current_end = next_end
        else:
            covered_count = covered_count + (current_end - current_start)
            current_start = next_start
            current_end = next_end

    covered_count = covered_count + (current_end - current_start)
    return covered_count


def count_suffix_prefix_overlap(first_text, second_text):
    """
    Count the longest suffix-prefix overlap between two strings.

    PARAMETERS:
    - first_text: Previous chunk text
    - second_text: Current chunk text

    RETURNS:
    - Overlap length
    """
    max_overlap = min(len(first_text), len(second_text))

    for overlap_length in range(max_overlap, 0, -1):
        if first_text[-overlap_length:] == second_text[:overlap_length]:
            return overlap_length

    return 0
