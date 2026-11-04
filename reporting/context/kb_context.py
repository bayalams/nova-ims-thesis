"""
Helpers for formatting knowledge-base search results as report context.
"""

from reporting.context.source_registry import register_rag_source


def format_kb_results_as_sources(registry, results, max_chars_per_result=1500):
    """
    Register KB search results and format them as numbered report sources.
    """
    parts = []
    retrieved_chunk_ids = []

    for result in results:
        chunk_id = result.get("chunk_id", "")
        if chunk_id:
            retrieved_chunk_ids.append(chunk_id)

        article_id = result.get("article_id", "")
        title = result.get("title", "Untitled") or "Untitled"
        source = result.get("source", "Unknown") or "Unknown"
        date = result.get("published_at", result.get("date", "Unknown")) or "Unknown"
        url = result.get("url", "") or ""
        content = result.get("chunk_text", "") or ""

        registered = register_rag_source(
            registry,
            article_id=article_id,
            title=title,
            source=source,
            date=date,
            url=url,
            text=content,
        )
        if not registered:
            continue

        if len(content) > max_chars_per_result:
            content = content[:max_chars_per_result].rstrip() + "...(truncated)"

        source_number = registered["source_number"]
        lines = [
            f"[Source {source_number}: {title}]",
            f"Outlet: {source}",
            f"Date: {date}",
            f"URL: {url}",
            "Source type: knowledge_base",
            "Content:",
            content,
        ]
        parts.append("\n".join(lines).strip())

    return {
        "context_text": "\n\n".join(parts),
        "retrieved_chunk_ids": retrieved_chunk_ids,
    }
