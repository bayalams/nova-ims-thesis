"""
Analyze strategy-level associations between Delphi scores and unsupervised metrics.
"""

import json
import math
from pathlib import Path


RUN_FOLDERS = [
    "2026-05-16_news_no_chunking_3large_100articles",
    "2026-05-17_news_no_chunking_3large_100articles",
    "2026-05-18_news_no_chunking_3large_100articles",
    "2026-05-19_news_no_chunking_3large_100articles",
    "2026-05-20_news_no_chunking_3large_100articles",
    "2026-05-21_news_no_chunking_3large_100articles",
    "2026-05-22_news_no_chunking_3large_100articles",
    "2026-05-23_news_no_chunking_3large_100articles",
]

STRATEGIES = [
    "simple",
    "react-basic",
    "react-map-reduce",
    "react-triage",
    "react-hybrid",
    "react-progressive",
]

STRATEGY_LABELS = {
    "simple": "Simple",
    "react-basic": "ReAct Basic",
    "react-map-reduce": "ReAct Map-Reduce",
    "react-triage": "ReAct Triage",
    "react-hybrid": "ReAct Hybrid",
    "react-progressive": "ReAct Progressive",
}

DELPHI_MEAN_SCORES = {
    "simple": 3.97,
    "react-basic": 4.32,
    "react-map-reduce": 4.32,
    "react-triage": 4.68,
    "react-hybrid": 5.05,
    "react-progressive": 4.85,
}

METRICS = [
    ("cited_daily_article_count", "Daily article coverage"),
    ("cited_daily_article_rate", "Daily article citation rate"),
    ("distinct_cited_sources", "Distinct cited sources"),
    ("cited_line_ratio", "Citation density"),
    ("cited_rag_article_count", "Cited KB article count"),
    ("cited_rag_article_rate", "Cited KB article rate"),
    ("llm_total_tokens", "Token use"),
    ("runtime_seconds", "Runtime"),
    ("report_word_count", "Report length"),
    ("citation_count", "Citation count"),
    ("cited_source_entropy", "Source citation entropy"),
    ("top_cited_source_share", "Top source concentration"),
]


def load_evaluation_rows(evaluation_path):
    """
    Load one evaluation JSON file.
    """
    payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "strategies" in payload:
        return payload["strategies"]
    return payload


def value_as_float(row, metric):
    """
    Read one metric value as a float.
    """
    if metric == "llm_total_tokens":
        prompt_tokens = float(row.get("llm_prompt_tokens", 0) or 0)
        completion_tokens = float(row.get("llm_completion_tokens", 0) or 0)
        return prompt_tokens + completion_tokens

    try:
        return float(row.get(metric, 0) or 0)
    except Exception:
        return 0.0


def build_unsupervised_strategy_means(repo_root):
    """
    Average unsupervised metrics by strategy across the fixed report runs.
    """
    grouped = {}
    for strategy in STRATEGIES:
        grouped[strategy] = {}
        for metric, label in METRICS:
            grouped[strategy][metric] = []

    for run_folder in RUN_FOLDERS:
        evaluation_path = repo_root / "shared_data" / "reports" / run_folder / "evaluation.json"
        print(f"[INFO] Loading evaluation: {evaluation_path}")
        rows = load_evaluation_rows(evaluation_path)

        for row in rows:
            strategy = row.get("strategy", "")
            if strategy not in grouped:
                continue

            for metric, label in METRICS:
                grouped[strategy][metric].append(value_as_float(row, metric))

    means = {}
    for strategy in STRATEGIES:
        means[strategy] = {}
        for metric, label in METRICS:
            values = grouped[strategy][metric]
            if values:
                means[strategy][metric] = sum(values) / len(values)
            else:
                means[strategy][metric] = 0.0

    return means


def pearson_correlation(x_values, y_values):
    """
    Calculate Pearson correlation for two lists.
    """
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)

    numerator = 0.0
    x_total = 0.0
    y_total = 0.0
    for index in range(len(x_values)):
        x_diff = x_values[index] - x_mean
        y_diff = y_values[index] - y_mean
        numerator = numerator + (x_diff * y_diff)
        x_total = x_total + (x_diff * x_diff)
        y_total = y_total + (y_diff * y_diff)

    denominator = math.sqrt(x_total) * math.sqrt(y_total)
    if denominator == 0:
        return 0.0

    return numerator / denominator


def rank_values(values):
    """
    Rank values with average ranks for ties.
    """
    indexed_values = []
    for index, value in enumerate(values):
        indexed_values.append((index, value))

    indexed_values.sort(key=lambda item: item[1])
    ranks = [0.0 for value in values]
    index = 0

    while index < len(indexed_values):
        next_index = index + 1
        while next_index < len(indexed_values):
            if indexed_values[next_index][1] != indexed_values[index][1]:
                break
            next_index = next_index + 1

        average_rank = ((index + 1) + next_index) / 2
        for rank_index in range(index, next_index):
            original_index = indexed_values[rank_index][0]
            ranks[original_index] = average_rank

        index = next_index

    return ranks


def spearman_correlation(x_values, y_values):
    """
    Calculate Spearman rank correlation for two lists.
    """
    return pearson_correlation(rank_values(x_values), rank_values(y_values))


def strength_label(value):
    """
    Give a simple descriptive strength label.
    """
    absolute_value = abs(value)
    if absolute_value >= 0.70:
        return "strong"
    if absolute_value >= 0.50:
        return "moderate"
    if absolute_value >= 0.30:
        return "weak"
    return "very weak"


def build_association_rows(unsupervised_means):
    """
    Build correlation rows for every unsupervised metric.
    """
    delphi_values = []
    for strategy in STRATEGIES:
        delphi_values.append(DELPHI_MEAN_SCORES[strategy])

    rows = []
    for metric, label in METRICS:
        metric_values = []
        for strategy in STRATEGIES:
            metric_values.append(unsupervised_means[strategy][metric])

        pearson = pearson_correlation(metric_values, delphi_values)
        spearman = spearman_correlation(metric_values, delphi_values)
        direction = "positive" if pearson >= 0 else "negative"
        rows.append({
            "metric": metric,
            "label": label,
            "pearson": pearson,
            "spearman": spearman,
            "direction": direction,
            "strength": strength_label(pearson),
        })

    rows.sort(key=lambda row: abs(row["pearson"]), reverse=True)
    return rows


def write_markdown_report(output_path, association_rows):
    """
    Write the association analysis as a Markdown table.
    """
    lines = [
        "# Delphi and Unsupervised Metric Association Analysis",
        "",
        "This table compares Delphi mean scores with broad unsupervised strategy means.",
        "The unsupervised values are averaged across the fixed 100-article report runs, then compared at strategy level with the Delphi mean score for each strategy.",
        "",
        "Because there are only six strategies, the correlations are descriptive indicators only. They should not be interpreted as statistical proof or as a predictive model.",
        "",
        "| Unsupervised Metric | Pearson r | Spearman rho | Direction | Descriptive Strength |",
        "|---|---:|---:|---|---|",
    ]

    for row in association_rows:
        lines.append(
            "| "
            + row["label"]
            + f" | {row['pearson']:.2f}"
            + f" | {row['spearman']:.2f}"
            + " | "
            + row["direction"]
            + " | "
            + row["strength"]
            + " |"
        )

    lines.extend([
        "",
        "The strongest descriptive associations are not necessarily intuitive quality proxies.",
        "Source citation entropy and report length show negative associations with Delphi mean score, while top source concentration and KB citation rate show positive associations.",
        "This suggests that expert preference was not driven by maximum evidence breadth alone. The Delphi scores appear more compatible with focused, selective, and synthesized reports than with reports that simply cite more sources or become longer.",
    ])

    print(f"[INFO] Writing analysis: {output_path}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    """
    Run the association analysis.
    """
    repo_root = Path(__file__).resolve().parents[2]
    unsupervised_means = build_unsupervised_strategy_means(repo_root)
    association_rows = build_association_rows(unsupervised_means)
    output_path = (
        repo_root
        / "shared_data"
        / "explorer"
        / "delphi_evaluation_analysis"
        / "delphi_unsupervised_metric_associations.md"
    )
    write_markdown_report(output_path, association_rows)


if __name__ == "__main__":
    main()
