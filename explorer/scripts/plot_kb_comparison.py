"""
Open comparison plots for the fixed 500-article KB evaluation run.
"""

import json
from pathlib import Path

from knowledge_bases.evaluation.utils import bytes_to_megabytes


EVALUATION_PATH = Path(
    "shared_data/knowledge_bases/evaluation_metrics_all_ann_sampled_ner_500.json"
)

HEATMAP_METRICS = [
    "article_coverage_rate",
    "query_latency_ms",
    "article_self_retrieval_top_5_rate",
    "title_self_retrieval_mrr",
    "summary_self_retrieval_mrr",
    "unique_articles_top_10",
    "story_level_top_k_diversity",
    "lead_paragraph_intact_rate",
    "entity_pair_preservation_rate",
    "db_size_mb",
]

COST_METRICS = {"query_latency_ms", "db_size_mb"}

DISPLAY_METRIC_LABELS = {
    "article_coverage_rate": "coverage",
    "query_latency_ms": "latency efficiency",
    "article_self_retrieval_top_5_rate": "article self top 5",
    "title_self_retrieval_mrr": "title MRR",
    "summary_self_retrieval_mrr": "summary MRR",
    "unique_articles_top_10": "unique top 10",
    "story_level_top_k_diversity": "story diversity",
    "lead_paragraph_intact_rate": "lead intact",
    "entity_pair_preservation_rate": "entity pairs",
    "db_size_mb": "size efficiency",
    "chunks": "chunks",
    "average_chunk_characters": "avg chunk chars",
    "average_chunks_per_article": "avg chunks/article",
    "max_same_article_share": "max same article",
    "boundary_break_rate": "boundary breaks",
    "boilerplate_contamination_rate": "boilerplate",
    "duplicate_chunk_rate": "duplicate chunks",
}


def build_recipe_display_names(recipe_names):
    """
    Build short reader-friendly labels for KB recipe names.
    """
    labels = []

    for recipe_name in recipe_names:
        if recipe_name == "news_fixed_2000_overlap_3large":
            labels.append("Fixed 2000 L")
            continue

        if recipe_name == "news_fixed_2000_overlap_3small":
            labels.append("Fixed 2000 S")
            continue

        if recipe_name == "news_no_chunking_3large":
            labels.append("No Chunk L")
            continue

        if recipe_name == "news_no_chunking_3small":
            labels.append("No Chunk S")
            continue

        if recipe_name == "news_recursive_2000_overlap_3large":
            labels.append("Recursive 2000 L")
            continue

        if recipe_name == "news_recursive_2000_overlap_3small":
            labels.append("Recursive 2000 S")
            continue

        labels.append(recipe_name.replace("_", " "))

    return labels


def load_evaluation_report(report_path):
    """
    Load a KB evaluation report from JSON.
    """
    with open(report_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_plot_rows(report):
    """
    Flatten evaluated recipe rows into a plotting-friendly structure.
    """
    rows = []

    for recipe_report in report.get("recipes", []):
        if recipe_report.get("status") != "evaluated":
            continue

        sanity = recipe_report.get("sanity_metrics", {})
        thesis = recipe_report.get("thesis_metrics", {})
        diagnostics = recipe_report.get("diagnostic_metrics", {})
        retrieval = recipe_report.get("retrieval_metrics", {})
        self_retrieval = retrieval.get("self_retrieval", {})
        top_k_crowding = retrieval.get("top_k_crowding", {})
        chunk_sizes = sanity.get("chunk_size_characters", {})
        chunks_per_article = sanity.get("chunks_per_article", {})
        query_latency_ms = sanity.get("query_latency_ms")
        if query_latency_ms is None:
            query_latency_ms = retrieval.get("config", {}).get("query_latency_ms")

        rows.append(
            {
                "recipe": recipe_report.get("recipe_name", ""),
                "article_coverage_rate": float(sanity.get("article_coverage_rate") or 0.0),
                "chunks": float(sanity.get("chunk_count") or 0.0),
                "average_chunk_characters": float(chunk_sizes.get("average") or 0.0),
                "average_chunks_per_article": float(chunks_per_article.get("average") or 0.0),
                "db_size_mb": float(bytes_to_megabytes(sanity.get("db_size_bytes")) or 0.0),
                "query_latency_ms": float(query_latency_ms or 0.0),
                "article_self_retrieval_top_5_rate": float(
                    thesis.get("article_self_retrieval_top_5_rate") or 0.0
                ),
                "title_self_retrieval_mrr": float(self_retrieval.get("title_mrr") or 0.0),
                "summary_self_retrieval_mrr": float(self_retrieval.get("summary_mrr") or 0.0),
                "unique_articles_top_10": float(
                    top_k_crowding.get("unique_articles_top_10") or 0.0
                ),
                "max_same_article_share": float(
                    top_k_crowding.get("max_same_article_share") or 0.0
                ),
                "story_level_top_k_diversity": float(
                    thesis.get("story_level_top_k_diversity") or 0.0
                ),
                "lead_paragraph_intact_rate": float(
                    thesis.get("lead_paragraph_intact_rate") or 0.0
                ),
                "boundary_break_rate": float(thesis.get("boundary_break_rate") or 0.0),
                "boilerplate_contamination_rate": float(
                    thesis.get("boilerplate_contamination_rate") or 0.0
                ),
                "entity_pair_preservation_rate": float(
                    thesis.get("entity_pair_preservation_rate") or 0.0
                ),
                "duplicate_chunk_rate": float(diagnostics.get("duplicate_chunk_rate") or 0.0),
            }
        )

    return rows


def build_metric_value_list(rows, recipe_names, metric):
    """
    Return one metric list ordered by recipe name.
    """
    row_lookup = {}
    for row in rows:
        row_lookup[row["recipe"]] = row

    values = []
    for recipe_name in recipe_names:
        values.append(float(row_lookup[recipe_name].get(metric, 0.0)))

    return values


def normalize_metric_values(values, invert=False):
    """
    Normalize one list of values to 0..1.
    """
    minimum = min(values)
    maximum = max(values)

    if minimum == maximum:
        return [1.0 for _ in values]

    normalized = []
    for value in values:
        scaled = (value - minimum) / (maximum - minimum)
        if invert:
            scaled = 1.0 - scaled
        normalized.append(scaled)

    return normalized


def build_heatmap_values(rows, recipe_names, metrics):
    """
    Build a normalized recipe-by-metric matrix.
    """
    column_lookup = {}
    for metric in metrics:
        values = build_metric_value_list(rows, recipe_names, metric)
        column_lookup[metric] = normalize_metric_values(
            values,
            invert=metric in COST_METRICS,
        )

    heatmap_values = []
    for recipe_index, recipe_name in enumerate(recipe_names):
        recipe_values = []
        for metric in metrics:
            recipe_values.append(column_lookup[metric][recipe_index])
        heatmap_values.append(recipe_values)

    return heatmap_values


def build_heatmap_metric_labels(metrics):
    """
    Convert metric keys into reader-friendly labels.
    """
    labels = []
    for metric in metrics:
        labels.append(DISPLAY_METRIC_LABELS.get(metric, metric.replace("_", " ")))
    return labels


def build_scatter_sizes(rows):
    """
    Build scatter marker sizes from DB size values.
    """
    db_sizes = []
    for row in rows:
        db_sizes.append(row["db_size_mb"])

    normalized_sizes = normalize_metric_values(db_sizes)
    scatter_sizes = []
    for value in normalized_sizes:
        scatter_sizes.append(180 + (value * 420))
    return scatter_sizes


def plot_tradeoff_scatter(rows, recipe_names):
    """
    Plot query latency vs article self-retrieval quality.
    """
    import matplotlib.pyplot as plt

    x_values = build_metric_value_list(rows, recipe_names, "query_latency_ms")
    y_values = build_metric_value_list(
        rows,
        recipe_names,
        "article_self_retrieval_top_5_rate",
    )
    scatter_sizes = build_scatter_sizes(rows)
    display_names = build_recipe_display_names(recipe_names)

    plt.figure(figsize=(10, 6))
    plt.scatter(x_values, y_values, s=scatter_sizes, alpha=0.75)

    for index, display_name in enumerate(display_names):
        plt.annotate(
            display_name,
            (x_values[index], y_values[index]),
            xytext=(6, 6),
            textcoords="offset points",
        )

    plt.xlabel("Query Latency (ms)")
    plt.ylabel("Article Self-Retrieval Top-5 Rate")
    plt.title("KB Trade-off: Retrieval Quality vs Query Latency")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()


def plot_grouped_metric_bars(rows, recipe_names, metric_specs, title):
    """
    Plot grouped metric bar charts with a readable subplot layout.
    """
    import matplotlib.pyplot as plt
    import math

    if len(metric_specs) == 4:
        column_count = 2
    elif len(metric_specs) == 5:
        column_count = 3
    else:
        column_count = len(metric_specs)

    row_count = math.ceil(len(metric_specs) / column_count)
    figure_width = 6 * column_count
    figure_height = 4 * row_count
    figure, axes = plt.subplots(row_count, column_count, figsize=(figure_width, figure_height))

    if row_count == 1 and column_count == 1:
        axes = [axes]
    elif row_count == 1 or column_count == 1:
        axes = list(axes)
    else:
        flattened_axes = []
        for axis_row in axes:
            for axis in axis_row:
                flattened_axes.append(axis)
        axes = flattened_axes

    x_positions = list(range(len(recipe_names)))
    display_names = build_recipe_display_names(recipe_names)

    for axis, metric_spec in zip(axes, metric_specs):
        metric_name, axis_title, y_label = metric_spec
        values = build_metric_value_list(rows, recipe_names, metric_name)
        axis.bar(x_positions, values)
        axis.set_title(axis_title)
        axis.set_ylabel(y_label)
        axis.set_xticks(x_positions, display_names, rotation=20, ha="right")
        axis.grid(True, axis="y", alpha=0.3)

    for axis in axes[len(metric_specs) :]:
        axis.set_visible(False)

    figure.suptitle(title)
    plt.tight_layout(rect=(0, 0, 1, 0.96))


def plot_strategy_heatmap(rows, recipe_names):
    """
    Plot one normalized heatmap of selected KB metrics.
    """
    import matplotlib.pyplot as plt

    heatmap_values = build_heatmap_values(rows, recipe_names, HEATMAP_METRICS)
    heatmap_labels = build_heatmap_metric_labels(HEATMAP_METRICS)
    display_names = build_recipe_display_names(recipe_names)

    plt.figure(figsize=(12, 5))
    image = plt.imshow(heatmap_values, aspect="auto", cmap="YlGn")
    plt.colorbar(image, label="Relative performance (higher = better)")
    plt.yticks(range(len(recipe_names)), display_names)
    plt.xticks(range(len(HEATMAP_METRICS)), heatmap_labels, rotation=30, ha="right")
    plt.title("Normalized KB Recipe Profile")
    plt.figtext(
        0.5,
        0.01,
        "Higher values indicate better relative performance. "
        "For latency and DB size, lower raw values score higher.",
        ha="center",
        fontsize=9,
    )
    plt.tight_layout()


def load_fixed_plot_rows():
    """
    Load rows from the fixed 500-article evaluation file.
    """
    repo_root = Path(__file__).resolve().parents[2]
    report_path = repo_root / EVALUATION_PATH
    print(f"[INFO] Loading evaluation report: {report_path}")
    report = load_evaluation_report(report_path)
    return build_plot_rows(report)


def main():
    """
    Open KB comparison figures for the fixed 500-article run.
    """
    import matplotlib.pyplot as plt

    rows = load_fixed_plot_rows()
    recipe_names = []
    for row in rows:
        recipe_names.append(row["recipe"])

    print("[INFO] Opening trade-off scatter plot")
    plot_tradeoff_scatter(rows, recipe_names)

    print("[INFO] Opening KB size and structure bars")
    plot_grouped_metric_bars(
        rows,
        recipe_names,
        [
            ("chunks", "Chunks", "Count"),
            ("average_chunk_characters", "Avg Chunk Chars", "Characters"),
            ("average_chunks_per_article", "Avg Chunks/Article", "Count"),
            ("db_size_mb", "DB Size", "MiB"),
        ],
        "KB Size And Structure",
    )

    print("[INFO] Opening retrieval diversity bars")
    plot_grouped_metric_bars(
        rows,
        recipe_names,
        [
            ("unique_articles_top_10", "Unique Articles Top 10", "Count"),
            ("max_same_article_share", "Max Same Article", "Rate"),
            ("story_level_top_k_diversity", "Story Diversity", "Rate"),
        ],
        "Retrieval Diversity",
    )

    print("[INFO] Opening text integrity bars")
    plot_grouped_metric_bars(
        rows,
        recipe_names,
        [
            ("lead_paragraph_intact_rate", "Lead Intact", "Rate"),
            ("boundary_break_rate", "Boundary Breaks", "Rate"),
            ("boilerplate_contamination_rate", "Boilerplate", "Rate"),
            ("entity_pair_preservation_rate", "Entity Pairs", "Rate"),
            ("duplicate_chunk_rate", "Duplicate Chunks", "Rate"),
        ],
        "Text Integrity",
    )

    print("[INFO] Opening heatmap")
    plot_strategy_heatmap(rows, recipe_names)
    plt.show()


if __name__ == "__main__":
    main()
