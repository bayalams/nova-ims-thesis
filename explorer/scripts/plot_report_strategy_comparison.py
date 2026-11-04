"""
Open comparison plots for the fixed 100-article report experiment.
"""

import argparse
import json
from pathlib import Path


RUN_FOLDERS = [
    "2026-05-01_news_no_chunking_3large_100articles",
    "2026-05-02_news_no_chunking_3large_100articles",
    "2026-05-03_news_no_chunking_3large_100articles",
    "2026-05-04_news_no_chunking_3large_100articles",
    "2026-05-05_news_no_chunking_3large_100articles",
    "2026-05-06_news_no_chunking_3large_100articles",
    "2026-05-07_news_no_chunking_3large_100articles",
    "2026-05-08_news_no_chunking_3large_100articles",
    "2026-05-09_news_no_chunking_3large_100articles",
    "2026-05-10_news_no_chunking_3large_100articles",
    "2026-05-11_news_no_chunking_3large_100articles",
    "2026-05-12_news_no_chunking_3large_100articles",
    "2026-05-13_news_no_chunking_3large_100articles",
    "2026-05-14_news_no_chunking_3large_100articles",
    "2026-05-15_news_no_chunking_3large_100articles",
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

HEATMAP_METRICS = [
    "cited_daily_article_count",
    "cited_daily_article_rate",
    "distinct_cited_sources",
    "cited_rag_article_count",
    "cited_rag_article_rate",
    "runtime_seconds",
    "llm_total_tokens",
]

COST_METRICS = {"runtime_seconds", "llm_total_tokens"}

DISPLAY_METRIC_LABELS = {
    "cited_daily_article_count": "article coverage",
    "cited_daily_article_rate": "daily citation rate",
    "cited_line_ratio": "groundedness",
    "distinct_cited_sources": "source diversity",
    "cited_rag_article_count": "KB evidence count",
    "cited_rag_article_rate": "KB evidence rate",
    "runtime_seconds": "runtime efficiency",
    "llm_total_tokens": "token efficiency",
}

HEATMAP_STRATEGY_LABELS = [
    "Simple",
    "ReAct Basic",
    "ReAct Map-Reduce",
    "ReAct Triage",
    "ReAct Hybrid",
    "ReAct Progressive",
]

COVERAGE_DIVERSITY_STRATEGIES = [
    ("simple", "Simple"),
    ("react-basic", "ReAct Basic"),
    ("react-map-reduce", "ReAct Map-Reduce"),
    ("react-triage", "ReAct Triage"),
    ("react-progressive", "ReAct Progressive"),
    ("react-hybrid", "ReAct Hybrid"),
]

PLOT_KEYS = [
    "cost-coverage",
    "coverage-diversity",
    "evidence-composition",
    "runtime-bars",
    "runtime-per-article",
    "runtime-vs-coverage",
    "rag-bars",
    "rag-scatter",
    "rag-dumbbell",
    "core-bars",
    "heatmap",
    "variability",
]

OUTPUT_DPI = 300
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "shared_data"
    / "explorer"
    / "report_strategy_comparison_plots"
)


def parse_arguments(arguments):
    """
    Parse command-line arguments for report strategy plots.
    """
    parser = argparse.ArgumentParser(
        description="Open report strategy comparison plots.",
    )
    parser.add_argument(
        "--plot",
        default="all",
        choices=["all"] + PLOT_KEYS,
        help="Open one specific plot instead of every plot.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Folder where SVG plots should be saved.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Save plots without opening an interactive Matplotlib window.",
    )
    return parser.parse_args(arguments)


def build_selected_plot_keys(plot_name):
    """
    Return the plot keys that should be opened.
    """
    if plot_name == "all":
        return list(PLOT_KEYS)

    return [plot_name]


def configure_plot_text_style():
    """
    Use larger default text sizes for thesis-ready plots.
    """
    import matplotlib

    matplotlib.rcParams["font.size"] = 13
    matplotlib.rcParams["axes.titlesize"] = 16
    matplotlib.rcParams["axes.labelsize"] = 14
    matplotlib.rcParams["xtick.labelsize"] = 12
    matplotlib.rcParams["ytick.labelsize"] = 12
    matplotlib.rcParams["legend.fontsize"] = 12
    matplotlib.rcParams["legend.title_fontsize"] = 13
    matplotlib.rcParams["figure.titlesize"] = 17


def save_current_plot(output_dir, plot_key):
    """
    Save the current Matplotlib figure as a 300-DPI SVG.
    """
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{plot_key}.svg"
    plt.gcf().savefig(
        output_path,
        format="svg",
        dpi=OUTPUT_DPI,
        bbox_inches="tight",
    )
    return output_path


def format_strategy_labels():
    """
    Return compact horizontal labels for strategy axes.
    """
    labels = []
    for strategy in STRATEGIES:
        labels.append(strategy.replace("react-", "react\n"))
    return labels


def format_readable_strategy_labels():
    """
    Return thesis-ready strategy labels.
    """
    return [
        "Simple",
        "ReAct Basic",
        "ReAct Map-Reduce",
        "ReAct Triage",
        "ReAct Hybrid",
        "ReAct Progressive",
    ]


def format_run_label(run_folder):
    """
    Return a short horizontal label for one run folder.
    """
    date_text = run_folder.split("_")[0]
    parts = date_text.split("-")
    if len(parts) == 3 and parts[1] == "05":
        return f"May {int(parts[2])}"
    return date_text


def load_evaluation_rows(evaluation_path):
    """
    Load one evaluation file and add derived total-token values.
    """
    with open(evaluation_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    rows = payload
    if isinstance(payload, dict) and "strategies" in payload:
        rows = payload["strategies"]

    normalized_rows = []
    for row in rows:
        copied = dict(row)
        copied["llm_total_tokens"] = (
            copied["llm_prompt_tokens"] + copied["llm_completion_tokens"]
        )
        normalized_rows.append(copied)

    return normalized_rows


def load_all_rows():
    """
    Load every fixed 100-article evaluation file.
    """
    repo_root = Path(__file__).resolve().parents[2]
    report_root = repo_root / "shared_data" / "reports"
    all_rows = []

    for run_folder in RUN_FOLDERS:
        evaluation_path = report_root / run_folder / "evaluation.json"
        print(f"[INFO] Loading evaluation: {evaluation_path}")
        rows = load_evaluation_rows(evaluation_path)
        for row in rows:
            row["run_folder"] = run_folder
        all_rows.extend(rows)

    return all_rows


def build_strategy_averages(rows, metrics):
    """
    Compute simple averages per strategy for the requested metrics.
    """
    grouped = {}

    for strategy in STRATEGIES:
        grouped[strategy] = {metric: [] for metric in metrics}

    for row in rows:
        strategy = row["strategy"]
        if strategy not in grouped:
            continue

        for metric in metrics:
            grouped[strategy][metric].append(float(row[metric]))

    averages = {}
    for strategy in STRATEGIES:
        averages[strategy] = {}
        for metric in metrics:
            values = grouped[strategy][metric]
            if not values:
                averages[strategy][metric] = 0.0
            else:
                averages[strategy][metric] = sum(values) / len(values)

    return averages


def normalize_metric_values(values, invert=False):
    """
    Normalize one list of values to 0..1.
    """
    minimum = min(values)
    maximum = max(values)

    if maximum == minimum:
        return [1.0 for _ in values]

    normalized = []
    for value in values:
        scaled = (value - minimum) / (maximum - minimum)
        if invert:
            scaled = 1.0 - scaled
        normalized.append(scaled)

    return normalized


def build_heatmap_values(averages, strategies, metrics):
    """
    Build a normalized matrix for the heatmap.
    """
    column_lookup = {}
    for metric in metrics:
        column_values = []
        for strategy in strategies:
            column_values.append(float(averages[strategy][metric]))

        column_lookup[metric] = normalize_metric_values(
            column_values,
            invert=metric in COST_METRICS,
        )

    rows = []
    for strategy_index, strategy in enumerate(strategies):
        row = []
        for metric in metrics:
            row.append(column_lookup[metric][strategy_index])
        rows.append(row)

    return rows


def build_heatmap_metric_labels(metrics):
    """
    Convert raw metric keys into reader-friendly heatmap labels.
    """
    labels = []
    for metric in metrics:
        labels.append(DISPLAY_METRIC_LABELS.get(metric, metric.replace("_", " ")))
    return labels


def build_capitalized_metric_labels(metrics):
    """
    Convert metric keys into capitalized labels for figure axes.
    """
    labels = []
    for label in build_heatmap_metric_labels(metrics):
        words = []
        for word in label.split(" "):
            if word.upper() == "KB":
                words.append("KB")
            else:
                words.append(word.capitalize())
        labels.append(" ".join(words))
    return labels


def build_strategy_metric_series(rows, metric, run_folders):
    """
    Build one ordered metric series per strategy across run folders.
    """
    grouped = {}
    for strategy in STRATEGIES:
        grouped[strategy] = {}

    for row in rows:
        strategy = row.get("strategy")
        run_folder = row.get("run_folder")
        if strategy not in grouped:
            continue
        if run_folder not in run_folders:
            continue
        grouped[strategy][run_folder] = float(row[metric])

    run_labels = []
    for run_folder in run_folders:
        run_labels.append(format_run_label(run_folder))

    series = {}
    for strategy in STRATEGIES:
        strategy_series = []
        for run_folder in run_folders:
            strategy_series.append(grouped[strategy].get(run_folder, 0.0))
        series[strategy] = strategy_series

    return run_labels, series


def build_profile_values(averages, strategies, metrics):
    """
    Normalize selected metrics for a slope-style strategy profile.
    """
    labels = build_heatmap_metric_labels(metrics)
    column_lookup = {}

    for metric in metrics:
        values = []
        for strategy in strategies:
            values.append(float(averages[strategy][metric]))
        column_lookup[metric] = normalize_metric_values(
            values,
            invert=metric in COST_METRICS,
        )

    profile_values = {}
    for strategy_index, strategy in enumerate(strategies):
        row = []
        for metric in metrics:
            row.append(column_lookup[metric][strategy_index])
        profile_values[strategy] = row

    return labels, profile_values


def build_metric_value_list(averages, strategies, metric):
    """
    Return one metric list ordered by strategy.
    """
    values = []
    for strategy in strategies:
        values.append(float(averages[strategy][metric]))
    return values


def plot_quality_cost_scatter(averages):
    """
    Plot strategy cost against article coverage.
    """
    import matplotlib.pyplot as plt

    plt.figure(figsize=(9, 6))

    readable_labels = format_readable_strategy_labels()
    for index, strategy in enumerate(STRATEGIES):
        x_value = averages[strategy]["llm_total_tokens"]
        y_value = averages[strategy]["cited_daily_article_count"]
        plt.scatter(x_value, y_value, s=90)
        plt.annotate(
            readable_labels[index],
            (x_value, y_value),
            xytext=(9, 5),
            textcoords="offset points",
            fontsize=10,
        )

    plt.xlabel("Average LLM Total Tokens", fontsize=11, labelpad=12)
    plt.ylabel("Average Cited Daily Article Count", fontsize=11, labelpad=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()


def plot_coverage_diversity_scatter(averages):
    """
    Plot article coverage against source diversity with a side legend.
    """
    import matplotlib.pyplot as plt

    color_cycle = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"]
    figure, axis = plt.subplots(figsize=(9, 6))

    for index, strategy_and_label in enumerate(COVERAGE_DIVERSITY_STRATEGIES):
        strategy, display_label = strategy_and_label
        x_value = averages[strategy]["cited_daily_article_count"]
        y_value = averages[strategy]["distinct_cited_sources"]
        axis.scatter(
            x_value,
            y_value,
            s=90,
            color=color_cycle[index % len(color_cycle)],
            label=display_label,
        )

    axis.set_title("Strategy Trade-off: Article Coverage vs Source Diversity")
    axis.set_xlabel("Average Cited Daily Article Count", fontsize=11, labelpad=12)
    axis.set_ylabel("Average Distinct Cited Sources", fontsize=11, labelpad=12)
    axis.grid(True, alpha=0.3)
    axis.legend(
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        title="Strategy",
    )
    plt.tight_layout(rect=(0, 0, 0.82, 1))


def plot_evidence_stack(averages):
    """
    Plot daily and KB evidence composition by strategy with grouped bars.
    """
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6))
    x_positions = list(range(len(STRATEGIES)))
    bar_width = 0.38
    daily_values = []
    rag_values = []

    for strategy in STRATEGIES:
        daily_values.append(averages[strategy]["cited_daily_article_count"])
        rag_values.append(averages[strategy]["cited_rag_article_count"])

    daily_positions = []
    rag_positions = []
    for x_position in x_positions:
        daily_positions.append(x_position - (bar_width / 2))
        rag_positions.append(x_position + (bar_width / 2))

    plt.bar(daily_positions, daily_values, width=bar_width, label="Daily cited articles")
    plt.bar(rag_positions, rag_values, width=bar_width, label="KB cited articles")
    plt.xticks(x_positions, format_readable_strategy_labels(), rotation=0, ha="center")
    plt.ylabel("Average cited article count")
    plt.legend()
    plt.tight_layout()


def plot_rag_usage_bars(averages):
    """
    Plot RAG usage as count and rate in two side-by-side bar charts.
    """
    import matplotlib.pyplot as plt

    metric_specs = [
        ("cited_rag_article_count", "Cited RAG Article Count", "Average Cited RAG Article Count"),
        ("cited_rag_article_rate", "Cited RAG Article Rate", "Average Cited RAG Article Rate"),
    ]
    x_positions = list(range(len(STRATEGIES)))
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))

    for axis, metric_name, title, y_label in [
        (axes[0], metric_specs[0][0], metric_specs[0][1], metric_specs[0][2]),
        (axes[1], metric_specs[1][0], metric_specs[1][1], metric_specs[1][2]),
    ]:
        values = build_metric_value_list(averages, STRATEGIES, metric_name)
        axis.bar(x_positions, values)
        axis.set_title(title)
        axis.set_ylabel(y_label)
        axis.set_xticks(x_positions, format_strategy_labels(), rotation=0, ha="center")
        axis.grid(True, axis="y", alpha=0.3)

    plt.suptitle("RAG Usage by Strategy")
    plt.tight_layout()


def plot_runtime_bars(averages):
    """
    Plot average runtime by strategy.
    """
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6))
    x_positions = list(range(len(STRATEGIES)))
    values = build_metric_value_list(averages, STRATEGIES, "runtime_seconds")

    plt.bar(x_positions, values)
    plt.xticks(x_positions, format_strategy_labels(), rotation=0, ha="center")
    plt.ylabel("Average Runtime (seconds)")
    plt.title("Runtime by Strategy")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()


def plot_runtime_per_article_bars(averages):
    """
    Plot runtime per cited daily article by strategy.
    """
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6))
    x_positions = list(range(len(STRATEGIES)))
    values = []

    for strategy in STRATEGIES:
        runtime_seconds = float(averages[strategy]["runtime_seconds"])
        cited_daily_article_count = float(averages[strategy]["cited_daily_article_count"])
        values.append(runtime_seconds / max(1.0, cited_daily_article_count))

    plt.bar(x_positions, values)
    plt.xticks(x_positions, format_strategy_labels(), rotation=0, ha="center")
    plt.ylabel("Seconds per cited daily article")
    plt.title("Runtime Per Cited Daily Article")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()


def plot_runtime_vs_article_coverage_scatter(averages):
    """
    Plot runtime against cited daily article count with point labels.
    """
    import matplotlib.pyplot as plt

    plt.figure(figsize=(9, 6))

    readable_labels = format_readable_strategy_labels()
    for index, strategy in enumerate(STRATEGIES):
        x_value = averages[strategy]["runtime_seconds"]
        y_value = averages[strategy]["cited_daily_article_count"]
        plt.scatter(
            x_value,
            y_value,
            s=90,
        )
        plt.annotate(
            readable_labels[index],
            (x_value, y_value),
            xytext=(9, 5),
            textcoords="offset points",
            fontsize=10,
        )

    plt.xlabel("Average Runtime (seconds)", fontsize=11, labelpad=12)
    plt.ylabel("Average Cited Daily Article Count", fontsize=11, labelpad=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()


def plot_rag_usage_scatter(averages):
    """
    Plot RAG article count against RAG article rate with a side legend.
    """
    import matplotlib.pyplot as plt

    color_cycle = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown"]
    figure, axis = plt.subplots(figsize=(9, 6))

    for index, strategy in enumerate(STRATEGIES):
        x_value = averages[strategy]["cited_rag_article_count"]
        y_value = averages[strategy]["cited_rag_article_rate"]
        axis.scatter(
            x_value,
            y_value,
            s=90,
            color=color_cycle[index % len(color_cycle)],
            label=strategy,
        )

    axis.set_title("Strategy Trade-off: RAG Count vs RAG Rate")
    axis.set_xlabel("Average Cited RAG Article Count")
    axis.set_ylabel("Average Cited RAG Article Rate")
    axis.grid(True, alpha=0.3)
    axis.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), title="Strategy")
    plt.tight_layout(rect=(0, 0, 0.82, 1))


def plot_rag_usage_dumbbell(averages):
    """
    Plot normalized RAG count and rate as a dumbbell chart per strategy.
    """
    import matplotlib.pyplot as plt

    count_values = build_metric_value_list(averages, STRATEGIES, "cited_rag_article_count")
    rate_values = build_metric_value_list(averages, STRATEGIES, "cited_rag_article_rate")
    normalized_counts = normalize_metric_values(count_values)
    normalized_rates = normalize_metric_values(rate_values)

    figure, axis = plt.subplots(figsize=(10, 5))
    y_positions = list(range(len(STRATEGIES)))

    for index, strategy in enumerate(STRATEGIES):
        axis.plot(
            [normalized_counts[index], normalized_rates[index]],
            [y_positions[index], y_positions[index]],
            color="lightgray",
            linewidth=2,
        )

    axis.scatter(normalized_counts, y_positions, color="tab:blue", s=70, label="Count")
    axis.scatter(normalized_rates, y_positions, color="tab:orange", s=70, label="Rate")
    axis.set_yticks(y_positions, STRATEGIES)
    axis.set_xlabel("Normalized RAG usage")
    axis.set_title("RAG Usage Profile by Strategy")
    axis.grid(True, axis="x", alpha=0.3)
    axis.legend()
    plt.tight_layout()


def plot_coverage_diversity_groundedness_bars(averages):
    """
    Plot horizontal bar charts for article coverage, source diversity, and groundedness.
    """
    import matplotlib.pyplot as plt

    metric_specs = [
        ("cited_daily_article_count", "Article Coverage", "Average Cited Daily Article Count"),
        ("distinct_cited_sources", "Source Diversity", "Average Distinct Cited Sources"),
        ("cited_line_ratio", "Groundedness", "Average Cited Line Ratio"),
    ]
    y_positions = list(range(len(STRATEGIES)))
    strategy_labels = HEATMAP_STRATEGY_LABELS
    figure, axes = plt.subplots(2, 2, figsize=(14, 10))
    flat_axes = [axes[0][0], axes[0][1], axes[1][0]]

    for axis, metric_name, title, y_label in [
        (flat_axes[0], metric_specs[0][0], metric_specs[0][1], metric_specs[0][2]),
        (flat_axes[1], metric_specs[1][0], metric_specs[1][1], metric_specs[1][2]),
        (flat_axes[2], metric_specs[2][0], metric_specs[2][1], metric_specs[2][2]),
    ]:
        values = build_metric_value_list(averages, STRATEGIES, metric_name)
        maximum_value = max(values)
        if maximum_value <= 0:
            label_offset = 0.1
            axis_limit = 1.0
        else:
            label_offset = maximum_value * 0.03
            axis_limit = maximum_value * 1.30
        axis.barh(y_positions, values)
        axis.set_title(title)
        axis.set_xlabel(y_label)
        axis.set_yticks(y_positions, strategy_labels)
        axis.set_xlim(0, axis_limit)
        axis.invert_yaxis()
        axis.grid(True, axis="x", alpha=0.3)

        for index, value in enumerate(values):
            if metric_name == "cited_line_ratio":
                label = f"{value * 100:.1f}%"
            else:
                label = f"{value:.1f}"
            axis.text(value + label_offset, index, label, va="center", fontsize=11)

    axes[1][1].set_visible(False)
    plt.suptitle("Strategy Comparison Across Core Evidence Metrics")
    plt.tight_layout()


def plot_strategy_heatmap(averages):
    """
    Plot one normalized heatmap of selected strategy metrics.
    """
    import matplotlib.pyplot as plt

    heatmap_values = build_heatmap_values(averages, STRATEGIES, HEATMAP_METRICS)
    heatmap_labels = build_capitalized_metric_labels(HEATMAP_METRICS)
    plt.figure(figsize=(16, 7))
    image = plt.imshow(heatmap_values, aspect="auto", cmap="YlGn")
    plt.colorbar(image)
    plt.yticks(range(len(STRATEGIES)), HEATMAP_STRATEGY_LABELS, fontsize=15)
    wrapped_heatmap_labels = []
    for label in heatmap_labels:
        wrapped_heatmap_labels.append(label.replace(" ", "\n"))
    plt.xticks(
        range(len(HEATMAP_METRICS)),
        wrapped_heatmap_labels,
        rotation=0,
        ha="center",
        fontsize=14,
    )
    plt.tight_layout()


def plot_variability_across_days(rows):
    """
    Plot day-by-day strategy variability for core metrics.
    """
    import matplotlib.pyplot as plt

    metric_specs = [
        ("cited_daily_article_count", "Article coverage"),
        ("cited_line_ratio", "Groundedness"),
        ("llm_total_tokens", "Total tokens"),
    ]
    figure, axes = plt.subplots(3, 1, figsize=(18, 10), sharex=True)
    run_labels = []

    for axis, metric_spec in zip(axes, metric_specs):
        metric_name, axis_title = metric_spec
        run_labels, series = build_strategy_metric_series(rows, metric_name, RUN_FOLDERS)
        for strategy in STRATEGIES:
            axis.plot(run_labels, series[strategy], marker="o", linewidth=1.8, label=strategy)
        axis.set_title(axis_title)
        axis.grid(True, alpha=0.3)

    axes[0].legend(loc="upper left", ncols=2)
    axes[0].set_ylabel("Count")
    axes[1].set_ylabel("Ratio")
    axes[2].set_ylabel("Tokens")
    axes[2].set_xlabel("Run date")
    plt.suptitle("Across-Days Variability by Strategy")
    plt.xticks(rotation=0, ha="center")
    plt.tight_layout()


def main(arguments=None):
    """
    Open report comparison figures.
    """
    import matplotlib.pyplot as plt

    parsed_arguments = parse_arguments(arguments or [])
    selected_plot_keys = build_selected_plot_keys(parsed_arguments.plot)
    configure_plot_text_style()

    print("[INFO] Loading report evaluation data")
    rows = load_all_rows()
    metrics = [
        "cited_daily_article_count",
        "cited_rag_article_count",
        "llm_total_tokens",
        "cited_line_ratio",
        "distinct_cited_sources",
    ]
    metrics.extend(HEATMAP_METRICS)

    unique_metrics = []
    for metric in metrics:
        if metric not in unique_metrics:
            unique_metrics.append(metric)

    averages = build_strategy_averages(rows, unique_metrics)

    for plot_key in selected_plot_keys:
        if plot_key == "cost-coverage":
            print("[INFO] Opening cost vs article coverage scatter plot")
            plot_quality_cost_scatter(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "coverage-diversity":
            print("[INFO] Opening article coverage vs source diversity scatter plot")
            plot_coverage_diversity_scatter(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "evidence-composition":
            print("[INFO] Opening daily vs KB evidence grouped bars")
            plot_evidence_stack(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "runtime-bars":
            print("[INFO] Opening runtime bars")
            plot_runtime_bars(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "runtime-per-article":
            print("[INFO] Opening runtime per cited daily article bars")
            plot_runtime_per_article_bars(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "runtime-vs-coverage":
            print("[INFO] Opening runtime vs article coverage scatter plot")
            plot_runtime_vs_article_coverage_scatter(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "rag-bars":
            print("[INFO] Opening RAG usage bars")
            plot_rag_usage_bars(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "rag-scatter":
            print("[INFO] Opening RAG usage scatter")
            plot_rag_usage_scatter(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "rag-dumbbell":
            print("[INFO] Opening RAG usage dumbbell plot")
            plot_rag_usage_dumbbell(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "core-bars":
            print("[INFO] Opening article coverage, source diversity, and groundedness bars")
            plot_coverage_diversity_groundedness_bars(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "heatmap":
            print("[INFO] Opening heatmap")
            plot_strategy_heatmap(averages)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")
            continue

        if plot_key == "variability":
            print("[INFO] Opening across-days variability plot")
            plot_variability_across_days(rows)
            output_path = save_current_plot(parsed_arguments.output_dir, plot_key)
            print(f"[INFO] Saved SVG plot: {output_path}")

    if not parsed_arguments.no_show:
        plt.show()


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
