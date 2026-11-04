"""
Markdown and CSV comparison table helpers for KB evaluation reports.
"""

import csv
from pathlib import Path

from knowledge_bases.evaluation.constants import COMPARISON_TABLE_COLUMNS
from knowledge_bases.evaluation.utils import bytes_to_megabytes
from knowledge_bases.evaluation.utils import safe_int


def make_default_table_paths(output_path):
    """
    Build default Markdown and CSV table paths from the JSON report path.

    PARAMETERS:
    - output_path: JSON evaluation output path

    RETURNS:
    - Tuple of Markdown path and CSV path
    """
    output_path = Path(output_path)
    markdown_path = output_path.with_name(output_path.stem + "_table.md")
    csv_path = output_path.with_name(output_path.stem + "_table.csv")
    return markdown_path, csv_path


def write_comparison_tables(report, markdown_table_path, csv_table_path):
    """
    Write Markdown and CSV comparison tables.

    PARAMETERS:
    - report: Evaluation report dictionary
    - markdown_table_path: Markdown output path
    - csv_table_path: CSV output path

    RETURNS:
    - Dictionary with output paths
    """
    rows = make_comparison_table_rows(report)

    markdown_table_path = Path(markdown_table_path)
    csv_table_path = Path(csv_table_path)
    markdown_table_path.parent.mkdir(parents=True, exist_ok=True)
    csv_table_path.parent.mkdir(parents=True, exist_ok=True)

    markdown_text = make_markdown_comparison_table(rows)
    markdown_table_path.write_text(markdown_text, encoding="utf-8")

    with csv_table_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=get_comparison_table_keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(make_csv_row(row))

    return {
        "markdown_table_path": str(markdown_table_path),
        "csv_table_path": str(csv_table_path),
    }


def make_comparison_table_rows(report):
    """
    Flatten nested recipe metrics into comparison table rows.

    PARAMETERS:
    - report: Evaluation report dictionary

    RETURNS:
    - List of row dictionaries
    """
    rows = []

    for recipe_report in report.get("recipes", []):
        recipe_config = recipe_report.get("recipe_config", {})
        sanity = recipe_report.get("sanity_metrics", {})
        thesis = recipe_report.get("thesis_metrics", {})
        diagnostics = recipe_report.get("diagnostic_metrics", {})
        retrieval = recipe_report.get("retrieval_metrics", {})

        chunk_size_summary = sanity.get("chunk_size_characters", {})
        chunks_per_article_summary = sanity.get("chunks_per_article", {})
        metadata_missing_rates = sanity.get("metadata_missing_rates", {})
        self_retrieval = retrieval.get("self_retrieval", {})
        context_efficiency = retrieval.get("context_efficiency", {})
        top_k_crowding = retrieval.get("top_k_crowding", {})
        retrieval_config = retrieval.get("config", {})
        query_latency_ms = sanity.get("query_latency_ms")
        if query_latency_ms is None:
            query_latency_ms = retrieval_config.get("query_latency_ms")

        row = {
            "recipe": recipe_report.get("recipe_name"),
            "status": recipe_report.get("status"),
            "embedding_model": recipe_config.get("embedding_model"),
            "chunking_method": recipe_config.get("chunking_method"),
            "chunk_size_characters": recipe_config.get("chunk_size_characters"),
            "chunk_overlap_characters": recipe_config.get("chunk_overlap_characters"),
            "expected_articles": sanity.get("expected_article_count"),
            "indexed_articles": sanity.get("article_count"),
            "article_coverage_rate": sanity.get("article_coverage_rate"),
            "chunks": sanity.get("chunk_count"),
            "vectors": sanity.get("vector_count"),
            "average_chunk_characters": chunk_size_summary.get("average"),
            "median_chunk_characters": chunk_size_summary.get("median"),
            "average_chunks_per_article": chunks_per_article_summary.get("average"),
            "metadata_missing_rate": metadata_missing_rates.get("any_required"),
            "embedding_failure_rate": sanity.get("embedding_failure_rate"),
            "db_size_mb": bytes_to_megabytes(sanity.get("db_size_bytes")),
            "build_time_seconds": sanity.get("build_time_seconds"),
            "query_latency_ms": query_latency_ms,
            "failed_to_index_articles": sanity.get("failed_to_index_article_count"),
            "article_reconstruction_rate": thesis.get("article_reconstruction_accuracy"),
            "lead_paragraph_intact_rate": thesis.get("lead_paragraph_intact_rate"),
            "boundary_break_rate": thesis.get("boundary_break_rate"),
            "boilerplate_contamination_rate": thesis.get("boilerplate_contamination_rate"),
            "entity_pair_preservation_rate": thesis.get("entity_pair_preservation_rate"),
            "story_level_top_k_diversity": thesis.get("story_level_top_k_diversity"),
            "article_self_retrieval_top_5_rate": thesis.get("article_self_retrieval_top_5_rate"),
            "hard_negative_separation_margin": thesis.get("hard_negative_separation_margin"),
            "retrieval_hubness_rate": thesis.get("retrieval_hubness_rate"),
            "recency_aware_retrieval_score": thesis.get("recency_aware_retrieval_score"),
            "duplicate_chunk_rate": diagnostics.get("duplicate_chunk_rate"),
            "average_adjacent_overlap_rate": diagnostics.get("average_adjacent_overlap_rate"),
            "title_self_retrieval_mrr": self_retrieval.get("title_mrr"),
            "summary_self_retrieval_mrr": self_retrieval.get("summary_mrr"),
            "combined_self_retrieval_top_5_rate": self_retrieval.get("combined_top_5_rate"),
            "unique_articles_top_10": top_k_crowding.get("unique_articles_top_10"),
            "max_same_article_share": top_k_crowding.get("max_same_article_share"),
            "overlap_waste_rate": context_efficiency.get("overlap_waste_rate"),
        }
        rows.append(row)

    return rows


def make_markdown_comparison_table(rows):
    """
    Create a Markdown comparison table.

    PARAMETERS:
    - rows: Flat comparison table rows

    RETURNS:
    - Markdown table text
    """
    headers = []
    separators = []

    for column in COMPARISON_TABLE_COLUMNS:
        headers.append(column["markdown_header"])
        separators.append("---")

    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(separators) + " |")

    for row in rows:
        cells = []
        for column in COMPARISON_TABLE_COLUMNS:
            cells.append(format_markdown_value(row.get(column["key"]), column["format"]))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"


def get_comparison_table_keys():
    """
    Get CSV column keys in stable order.

    PARAMETERS:
    - None

    RETURNS:
    - List of column keys
    """
    keys = []

    for column in COMPARISON_TABLE_COLUMNS:
        keys.append(column["key"])

    return keys


def make_csv_row(row):
    """
    Convert one table row into CSV-safe values.

    PARAMETERS:
    - row: Flat row dictionary

    RETURNS:
    - CSV row dictionary
    """
    csv_row = {}

    for key in get_comparison_table_keys():
        value = row.get(key)
        if value is None:
            csv_row[key] = ""
        else:
            csv_row[key] = value

    return csv_row


def format_markdown_value(value, value_format):
    """
    Format one value for Markdown table output.

    PARAMETERS:
    - value: Value to format
    - value_format: text, integer, number, or percent

    RETURNS:
    - Formatted string
    """
    if value is None:
        return "n/a"

    if value_format == "percent":
        return f"{value * 100:.1f}%"

    if value_format == "integer":
        integer_value = safe_int(value)
        if integer_value is None:
            return "n/a"
        return str(integer_value)

    if value_format == "number":
        try:
            return f"{float(value):.2f}"
        except Exception:
            return "n/a"

    return escape_markdown_cell(str(value))


def escape_markdown_cell(value):
    """
    Escape pipe characters in Markdown table cells.

    PARAMETERS:
    - value: Cell string

    RETURNS:
    - Escaped cell string
    """
    return value.replace("|", "\\|")
