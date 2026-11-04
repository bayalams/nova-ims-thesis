"""
Automatic report metrics.
"""

import math
import re
from collections import Counter

from reporting.context.daily_articles import parse_article_datetime
from reporting.context.daily_articles import parse_report_datetime
from reporting.context.source_registry import extract_cited_source_numbers


SOURCE_CITATION_RE = re.compile(r"\[Sources?\s+([^\]]+)\]", flags=re.IGNORECASE)
CANONICAL_SOURCE_CITATION_RE = re.compile(r"\d+(?:\s*,\s*\d+)*")


def count_citation_occurrences(report_text):
    """
    Count every [Source N] citation occurrence.
    """
    return len(SOURCE_CITATION_RE.findall(report_text or ""))


def count_nonstandard_citations(report_text):
    """
    Count citation brackets that are not clean numeric source lists.
    """
    count = 0

    for match in SOURCE_CITATION_RE.finditer(report_text or ""):
        payload = match.group(1).strip()
        if not CANONICAL_SOURCE_CITATION_RE.fullmatch(payload):
            count = count + 1

    return count


def count_tool_calls(tool_call_log, tool_name=None, successful_only=False):
    """
    Count tool calls by name and status.
    """
    count = 0

    for tool_call in tool_call_log or []:
        if tool_name is not None and tool_call.get("tool_name") != tool_name:
            continue
        if successful_only and tool_call.get("status") != "ok":
            continue
        count = count + 1

    return count


def calculate_entropy(values):
    """
    Calculate Shannon entropy for a list of values.
    """
    if not values:
        return 0.0

    counts = Counter(values)
    total = sum(counts.values())
    entropy = 0.0

    for count in counts.values():
        probability = count / total
        entropy = entropy - (probability * math.log(probability, 2))

    return round(entropy, 4)


def calculate_hhi(values):
    """
    Calculate Herfindahl-Hirschman concentration for a list of values.
    """
    if not values:
        return 0.0

    counts = Counter(values)
    total = sum(counts.values())
    hhi = 0.0

    for count in counts.values():
        probability = count / total
        hhi = hhi + (probability * probability)

    return round(hhi, 4)


def calculate_top_share(values):
    """
    Return the share held by the most common value.
    """
    if not values:
        return 0.0

    counts = Counter(values)
    total = sum(counts.values())
    return round(max(counts.values()) / total, 4)


def parse_window_datetime(value):
    """
    Parse an optional report window datetime.
    """
    if not value:
        return None

    try:
        return parse_report_datetime(value)
    except Exception:
        return None


def temporal_bucket_for_article(article, window_start=None, window_end=None):
    """
    Classify an article date relative to the report window.
    """
    if window_start is None or window_end is None:
        return "unknown"

    article_time = parse_article_datetime(article)
    if article_time is None:
        return "unknown"

    if article_time > window_end:
        return "future"
    if window_start <= article_time <= window_end:
        return "daily_window"
    if article_time < window_start:
        return "past"

    return "unknown"


def build_report_sources(registry, window_start=None, window_end=None):
    """
    Build compact source traceability rows for a report manifest.
    """
    parsed_window_start = parse_window_datetime(window_start)
    parsed_window_end = parse_window_datetime(window_end)
    report_sources = []

    for source_item in registry.get("source_articles", []):
        article = source_item.get("article", {}) or {}
        metadata = article.get("metadata", {}) or {}
        date_text = (
            article.get("published_at", "")
            or article.get("date", "")
            or metadata.get("published_at", "")
            or metadata.get("date", "")
            or metadata.get("published", "")
            or ""
        )
        url = metadata.get("link", metadata.get("url", "")) or article.get("url", "")
        report_sources.append({
            "source_number": source_item.get("source_number", ""),
            "article_id": source_item.get("article_id", ""),
            "source_type": source_item.get("source_type", ""),
            "title": metadata.get("title", "Untitled") or "Untitled",
            "source": metadata.get("source", "Unknown") or "Unknown",
            "date": date_text or "Unknown",
            "url": url or "",
            "temporal_bucket": temporal_bucket_for_article(
                article,
                parsed_window_start,
                parsed_window_end,
            ),
        })

    return report_sources


def count_temporal_buckets(source_rows, article_ids=None):
    """
    Count daily, past, future, and unknown evidence buckets.
    """
    allowed_ids = None
    if article_ids is not None:
        allowed_ids = set(article_ids)

    counts = {
        "daily_window": 0,
        "past": 0,
        "future": 0,
        "unknown": 0,
    }

    for source_row in source_rows:
        if allowed_ids is not None and source_row.get("article_id") not in allowed_ids:
            continue
        bucket = source_row.get("temporal_bucket", "unknown")
        if bucket not in counts:
            bucket = "unknown"
        counts[bucket] = counts[bucket] + 1

    return counts


def temporal_validity_rate(counts):
    """
    Return non-future share while ignoring unknown-date evidence.
    """
    known_count = counts.get("daily_window", 0) + counts.get("past", 0) + counts.get("future", 0)
    if known_count <= 0:
        return 1.0

    valid_count = counts.get("daily_window", 0) + counts.get("past", 0)
    return valid_count / known_count


def extract_report_metrics(
    report_text,
    registry,
    retrieved_chunk_ids,
    window_start=None,
    window_end=None,
    tool_call_log=None,
    model_metrics=None,
):
    """
    Extract automatic report metrics.
    """
    cited_numbers = extract_cited_source_numbers(report_text)
    cited_number_set = set(cited_numbers)
    source_articles = registry.get("source_articles", [])
    daily_ids = set(registry.get("daily_article_ids", []))
    rag_ids = set(registry.get("rag_source_article_ids", []))
    valid_numbers = []
    cited_article_ids = []
    source_rows = build_report_sources(registry, window_start, window_end)

    for number in cited_numbers:
        if 1 <= number <= len(source_articles):
            valid_numbers.append(number)
            cited_article_ids.append(source_articles[number - 1]["article_id"])

    cited_daily_count = 0
    cited_rag_count = 0
    for article_id in cited_article_ids:
        if article_id in daily_ids:
            cited_daily_count = cited_daily_count + 1
        if article_id in rag_ids:
            cited_rag_count = cited_rag_count + 1

    source_names = []
    for number in valid_numbers:
        article = source_articles[number - 1]["article"]
        metadata = article.get("metadata", {}) or {}
        source_names.append(metadata.get("source", "Unknown") or "Unknown")

    citation_reference_validity_rate = 1.0
    if cited_number_set:
        citation_reference_validity_rate = len(valid_numbers) / len(cited_number_set)

    retrieved_chunk_count = len(retrieved_chunk_ids or [])
    retrieved_to_cited_rate = 0.0
    if retrieved_chunk_count > 0:
        retrieved_to_cited_rate = len(cited_article_ids) / retrieved_chunk_count

    report_lines = []
    cited_lines = []
    for line in (report_text or "").splitlines():
        if not line.strip():
            continue
        report_lines.append(line)
        if SOURCE_CITATION_RE.search(line):
            cited_lines.append(line)

    cited_temporal_counts = count_temporal_buckets(source_rows, cited_article_ids)
    source_temporal_counts = count_temporal_buckets(source_rows)
    rag_temporal_counts = count_temporal_buckets(source_rows, rag_ids)
    selected_model_metrics = model_metrics or {}

    return {
        "daily_article_count": len(daily_ids),
        "citation_count": count_citation_occurrences(report_text),
        "distinct_cited_sources": len(cited_number_set),
        "citation_reference_validity_rate": citation_reference_validity_rate,
        "citation_out_of_range_count": len(cited_number_set) - len(valid_numbers),
        "citation_nonstandard_count": count_nonstandard_citations(report_text),
        "cited_daily_article_count": cited_daily_count,
        "cited_daily_article_rate": cited_daily_count / max(1, len(daily_ids)),
        "cited_rag_article_count": cited_rag_count,
        "cited_rag_article_rate": cited_rag_count / max(1, len(rag_ids)),
        "rag_source_article_count": len(rag_ids),
        "retrieved_chunk_count": retrieved_chunk_count,
        "retrieved_to_cited_rate": retrieved_to_cited_rate,
        "cited_source_entropy": calculate_entropy(source_names),
        "cited_source_hhi": calculate_hhi(source_names),
        "top_cited_source_share": calculate_top_share(source_names),
        "report_word_count": len(re.findall(r"\b\w+\b", report_text or "")),
        "section_count": len(re.findall(r"^#+\s+", report_text or "", flags=re.MULTILINE)),
        "report_line_count": len(report_lines),
        "cited_line_count": len(cited_lines),
        "cited_line_ratio": len(cited_lines) / max(1, len(report_lines)),
        "kb_search_call_count": count_tool_calls(tool_call_log, "search_knowledge_base"),
        "successful_kb_search_call_count": count_tool_calls(
            tool_call_log,
            "search_knowledge_base",
            successful_only=True,
        ),
        "read_article_call_count": count_tool_calls(tool_call_log, "read_article"),
        "llm_prompt_tokens": int(selected_model_metrics.get("prompt_tokens", 0) or 0),
        "llm_completion_tokens": int(selected_model_metrics.get("completion_tokens", 0) or 0),
        "llm_call_count": int(selected_model_metrics.get("llm_calls", 0) or 0),
        "runtime_seconds": float(selected_model_metrics.get("runtime_seconds", 0.0) or 0.0),
        "cited_daily_window_article_count": cited_temporal_counts["daily_window"],
        "cited_past_article_count": cited_temporal_counts["past"],
        "cited_future_article_count": cited_temporal_counts["future"],
        "cited_unknown_date_article_count": cited_temporal_counts["unknown"],
        "cited_temporal_validity_rate": temporal_validity_rate(cited_temporal_counts),
        "source_daily_window_article_count": source_temporal_counts["daily_window"],
        "source_past_article_count": source_temporal_counts["past"],
        "source_future_article_count": source_temporal_counts["future"],
        "source_unknown_date_article_count": source_temporal_counts["unknown"],
        "source_temporal_validity_rate": temporal_validity_rate(source_temporal_counts),
        "rag_daily_window_article_count": rag_temporal_counts["daily_window"],
        "rag_past_article_count": rag_temporal_counts["past"],
        "rag_future_article_count": rag_temporal_counts["future"],
        "rag_unknown_date_article_count": rag_temporal_counts["unknown"],
        "rag_temporal_validity_rate": temporal_validity_rate(rag_temporal_counts),
    }
