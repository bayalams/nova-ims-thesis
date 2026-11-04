"""
Context-construction strategies for daily reports.
"""

from reporting.context.daily_articles import get_article_id
from reporting.context.daily_articles import get_article_text
from reporting.context.kb_context import format_kb_results_as_sources
from reporting.context.source_registry import make_source_registry
from reporting.context.source_registry import register_daily_articles


CONTEXT_STRATEGIES = [
    "simple",
    "react-basic",
    "react-map-reduce",
    "react-triage",
    "react-hybrid",
    "react-progressive",
]


def validate_context_strategy(strategy_name):
    """
    Return a valid context strategy name or raise a clear error.
    """
    if strategy_name in CONTEXT_STRATEGIES:
        return strategy_name

    valid_names = ", ".join(CONTEXT_STRATEGIES)
    raise ValueError(f"Unknown context strategy: {strategy_name}. Valid names: {valid_names}")


def format_article_for_context(source_item, max_chars_per_article):
    """
    Format one numbered source article for report context.
    """
    article = source_item["article"]
    metadata = article.get("metadata", {}) or {}
    source_number = source_item["source_number"]
    title = metadata.get("title", "Untitled") or "Untitled"
    source = metadata.get("source", "Unknown") or "Unknown"
    date = metadata.get("date", article.get("published_at", "Unknown")) or "Unknown"
    url = metadata.get("link", metadata.get("url", "")) or ""
    text = get_article_text(article)

    if len(text) > max_chars_per_article:
        text = text[:max_chars_per_article].rstrip() + "..."

    lines = [
        f"[Source {source_number}: {title}]",
        f"Source: {source}",
        f"Date: {date}",
        f"URL: {url}",
        "",
        text,
    ]

    return "\n".join(lines).strip()


def build_simple_context(articles, max_chars_per_article=2000):
    """
    Build report context by listing daily articles in source-number order.
    """
    registry = make_source_registry()
    register_daily_articles(registry, articles)

    blocks = []
    for source_item in registry["source_articles"]:
        block = format_article_for_context(source_item, max_chars_per_article)
        blocks.append(block)

    return {
        "strategy": "simple",
        "context_text": "\n\n".join(blocks),
        "registry": registry,
        "retrieved_chunk_ids": [],
        "article_count": len(articles),
        "source_count": len(registry["source_articles"]),
    }


def build_context_from_selected_articles(articles, selected_article_ids, max_chars_per_article=2000):
    """
    Build simple numbered context from one chosen subset of daily articles.
    """
    article_by_id = {}
    for article in articles:
        article_id = get_article_id(article)
        article_by_id[article_id] = article

    chosen_articles = []
    for article_id in selected_article_ids:
        article = article_by_id.get(article_id)
        if article is not None:
            chosen_articles.append(article)

    if not chosen_articles:
        chosen_articles = list(articles)

    result = build_simple_context(chosen_articles, max_chars_per_article=max_chars_per_article)
    result["strategy"] = "react-triage"
    return result


def build_article_title_queries(articles, max_queries):
    """
    Build fixed KB search queries from selected article titles.
    """
    queries = []

    for article in articles:
        if len(queries) >= max_queries:
            break

        metadata = article.get("metadata", {}) or {}
        title = metadata.get("title", "") or ""
        title = title.strip()

        if title:
            queries.append(title)

    return queries


def build_react_basic_context(articles, search_function, max_queries=5):
    """
    Build simple daily article context plus KB sources from title queries.
    """
    simple_context = build_simple_context(articles)
    registry = simple_context["registry"]
    context_parts = [simple_context["context_text"]]
    retrieved_chunk_ids = []

    queries = build_article_title_queries(articles, max_queries)
    for query in queries:
        results = search_function(query)
        formatted = format_kb_results_as_sources(registry, results)

        context_text = formatted["context_text"]
        if context_text:
            context_parts.append(context_text)

        retrieved_chunk_ids.extend(formatted["retrieved_chunk_ids"])

    return {
        "strategy": "react-basic",
        "context_text": "\n\n".join(context_parts),
        "registry": registry,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "article_count": len(articles),
        "source_count": len(registry["source_articles"]),
    }


def split_batches(items, batch_size):
    """
    Split a list into simple fixed-size batches.
    """
    if batch_size <= 0:
        raise ValueError("Batch size must be a positive integer")

    batches = []
    start = 0

    while start < len(items):
        end = start + batch_size
        batches.append(items[start:end])
        start = end

    return batches


def build_map_reduce_context(articles, summarize_function, batch_size=30):
    """
    Build context by summarizing article batches with preserved source numbers.
    """
    registry = make_source_registry()
    register_daily_articles(registry, articles)

    summaries = []
    batches = split_batches(registry["source_articles"], batch_size)

    for batch in batches:
        batch_blocks = []
        for source_item in batch:
            block = format_article_for_context(source_item, 1500)
            batch_blocks.append(block)

        batch_text = "\n\n".join(batch_blocks)
        summary = summarize_function(batch_text)
        summary = (summary or "").strip()

        if summary:
            summaries.append(summary)

    return {
        "strategy": "react-map-reduce",
        "context_text": "\n\n".join(summaries),
        "registry": registry,
        "retrieved_chunk_ids": [],
        "article_count": len(articles),
        "source_count": len(registry["source_articles"]),
    }


def build_progressive_context(articles, update_function, batch_size=30):
    """
    Build context by updating one running draft from article batches.
    """
    registry = make_source_registry()
    register_daily_articles(registry, articles)

    running_draft = ""
    batches = split_batches(registry["source_articles"], batch_size)

    for batch in batches:
        batch_blocks = []
        for source_item in batch:
            block = format_article_for_context(source_item, 1500)
            batch_blocks.append(block)

        batch_text = "\n\n".join(batch_blocks)
        updated_draft = update_function(running_draft, batch_text)
        running_draft = (updated_draft or "").strip()

    return {
        "strategy": "react-progressive",
        "context_text": running_draft,
        "registry": registry,
        "retrieved_chunk_ids": [],
        "article_count": len(articles),
        "source_count": len(registry["source_articles"]),
    }


def format_article_titles(articles):
    """
    Format article titles with 1-based indexes for model selection.
    """
    lines = []

    for index, article in enumerate(articles, start=1):
        metadata = article.get("metadata", {}) or {}
        title = metadata.get("title", "Untitled") or "Untitled"
        source = metadata.get("source", "Unknown") or "Unknown"
        date = metadata.get("date", article.get("published_at", "Unknown")) or "Unknown"
        lines.append(f"{index}. [{source}] ({date}) {title}")

    return "\n".join(lines)


def normalize_max_selected(max_selected):
    """
    Convert max_selected to a positive integer or raise a clear error.
    """
    try:
        selected_count = int(max_selected)
    except Exception:
        raise ValueError("max_selected must be a positive integer")

    if selected_count <= 0:
        raise ValueError("max_selected must be a positive integer")

    return selected_count


def build_triage_context(articles, select_function, max_selected=20):
    """
    Build context from articles selected after title triage.
    """
    max_selected = normalize_max_selected(max_selected)
    title_lines = format_article_titles(articles)
    selected_indexes = select_function(title_lines)
    selected_articles = []
    seen_indexes = []

    for index in selected_indexes:
        if 1 <= index <= len(articles) and index not in seen_indexes:
            selected_articles.append(articles[index - 1])
            seen_indexes.append(index)

        if len(selected_articles) >= max_selected:
            break

    if not selected_articles:
        selected_articles = articles[:max_selected]

    result = build_simple_context(selected_articles)
    result["strategy"] = "react-triage"
    return result


def build_hybrid_context(articles, score_function, score_threshold=3, max_selected=50):
    """
    Score titles, filter by score, then build daily context from selected articles.
    """
    max_selected = normalize_max_selected(max_selected)
    title_lines = format_article_titles(articles)
    scores = score_function(title_lines)
    selected_articles = []

    for index, article in enumerate(articles, start=1):
        score = scores.get(index, 0)
        if score >= score_threshold:
            selected_articles.append(article)

        if len(selected_articles) >= max_selected:
            break

    if not selected_articles:
        fallback_count = min(30, len(articles), max_selected)
        selected_articles = articles[:fallback_count]

    result = build_simple_context(selected_articles)
    result["strategy"] = "react-hybrid"
    return result
