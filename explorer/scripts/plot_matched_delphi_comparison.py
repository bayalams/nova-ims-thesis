"""
Create Delphi comparison plots from the exact matched report batch.
"""

import json
from pathlib import Path


MATCHED_RUN_FOLDER = "2026-05-17_news_no_chunking_3large_100articles"

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

SHORT_LABELS = {
    "simple": "Simple",
    "react-basic": "R. Basic",
    "react-map-reduce": "R. Map-Reduce",
    "react-triage": "R. Triage",
    "react-hybrid": "R. Hybrid",
    "react-progressive": "R. Progressive",
}

STRATEGY_COLORS = {
    "simple": "#6b7280",
    "react-basic": "#2f67d8",
    "react-map-reduce": "#7c3aed",
    "react-triage": "#e11d48",
    "react-hybrid": "#00897b",
    "react-progressive": "#f59e0b",
}

DELPHI_MEAN_SCORES = {
    "simple": 3.97,
    "react-basic": 4.32,
    "react-map-reduce": 4.32,
    "react-triage": 4.68,
    "react-hybrid": 5.05,
    "react-progressive": 4.85,
}

EVIDENCE_INDEX_METRICS = [
    "cited_daily_article_count",
    "distinct_cited_sources",
    "cited_line_ratio",
    "cited_rag_article_count",
    "cited_rag_article_rate",
]


def load_matched_rows(repo_root):
    """
    Load the six unsupervised rows for the Delphi-matched report batch.
    """
    evaluation_path = (
        repo_root
        / "shared_data"
        / "reports"
        / MATCHED_RUN_FOLDER
        / "evaluation.json"
    )
    print(f"[INFO] Loading matched evaluation: {evaluation_path}")

    payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "strategies" in payload:
        rows = payload["strategies"]
    else:
        rows = payload

    rows_by_strategy = {}
    for row in rows:
        strategy = row.get("strategy", "")
        if strategy not in STRATEGIES:
            continue

        copied = dict(row)
        copied["llm_total_tokens"] = (
            float(copied.get("llm_prompt_tokens", 0) or 0)
            + float(copied.get("llm_completion_tokens", 0) or 0)
        )
        copied["delphi_mean_score"] = DELPHI_MEAN_SCORES[strategy]
        rows_by_strategy[strategy] = copied

    missing = []
    for strategy in STRATEGIES:
        if strategy not in rows_by_strategy:
            missing.append(strategy)

    if missing:
        raise RuntimeError(f"Missing matched rows for: {', '.join(missing)}")

    return rows_by_strategy


def normalize_values(values):
    """
    Normalize values to 0..1.
    """
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [1.0 for value in values]

    normalized = []
    for value in values:
        normalized.append((value - minimum) / (maximum - minimum))

    return normalized


def add_evidence_index(rows_by_strategy):
    """
    Add one matched technical evidence index to each strategy row.
    """
    normalized_by_metric = {}

    for metric in EVIDENCE_INDEX_METRICS:
        raw_values = []
        for strategy in STRATEGIES:
            raw_values.append(float(rows_by_strategy[strategy].get(metric, 0) or 0))
        normalized_by_metric[metric] = normalize_values(raw_values)

    for strategy_index, strategy in enumerate(STRATEGIES):
        values = []
        for metric in EVIDENCE_INDEX_METRICS:
            values.append(normalized_by_metric[metric][strategy_index])
        rows_by_strategy[strategy]["technical_evidence_index"] = sum(values) / len(values)


def rank_values(rows_by_strategy, metric):
    """
    Rank strategies by one metric, using average ranks for ties.
    """
    values = []
    for strategy in STRATEGIES:
        values.append((strategy, float(rows_by_strategy[strategy][metric])))

    sorted_values = sorted(values, key=lambda item: item[1], reverse=True)
    ranks = {}
    index = 0
    while index < len(sorted_values):
        same_value = [sorted_values[index]]
        next_index = index + 1
        while next_index < len(sorted_values):
            if sorted_values[next_index][1] != sorted_values[index][1]:
                break
            same_value.append(sorted_values[next_index])
            next_index = next_index + 1

        first_rank = index + 1
        last_rank = next_index
        average_rank = (first_rank + last_rank) / 2
        for strategy, value in same_value:
            ranks[strategy] = average_rank

        index = next_index

    return ranks


def svg_text(x, y, text, size=12, weight="400", anchor="start", fill="#1f2933", extra=""):
    """
    Return one SVG text element.
    """
    return (
        f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{fill}"{extra}>{text}</text>'
    )


def scaled(value, minimum, maximum, start, end):
    """
    Scale a number into an SVG coordinate range.
    """
    if maximum == minimum:
        return (start + end) / 2
    return start + ((value - minimum) / (maximum - minimum)) * (end - start)


def write_scatter_plot(rows_by_strategy, metric, title, subtitle, x_label, output_path):
    """
    Write one matched technical metric vs Delphi mean SVG scatter plot.
    """
    width = 1040
    height = 640
    left = 115
    right = 930
    top = 88
    bottom = 550

    x_values = [float(rows_by_strategy[strategy][metric]) for strategy in STRATEGIES]
    y_values = [float(rows_by_strategy[strategy]["delphi_mean_score"]) for strategy in STRATEGIES]
    if metric == "llm_total_tokens":
        x_min = 30000
        x_max = 150000
        x_ticks = [30000, 60000, 90000, 120000, 150000]
    elif metric == "cited_daily_article_count":
        x_min = 10
        x_max = 40
        x_ticks = [10, 20, 30, 40]
    else:
        x_min = min(x_values)
        x_max = max(x_values)
        x_ticks = []
        for index in range(5):
            x_ticks.append(x_min + ((x_max - x_min) / 4) * index)
    y_min = 3.8
    y_max = 5.2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        svg_text(34, 40, title, size=23, weight="700"),
        svg_text(34, 64, subtitle, size=13, fill="#5f6b7a"),
    ]

    for tick in [4.0, 4.5, 5.0]:
        y = scaled(tick, y_min, y_max, bottom, top)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#d9dee7"/>')
        parts.append(svg_text(left - 12, y + 5, f"{tick:.1f}", anchor="end", fill="#5f6b7a"))

    for tick in x_ticks:
        x = scaled(tick, x_min, x_max, left, right)
        if metric == "llm_total_tokens":
            tick_label = str(int(round(tick)))
        else:
            tick_label = str(int(round(tick)))
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="#d9dee7"/>')
        parts.append(svg_text(x, bottom + 25, tick_label, anchor="middle", fill="#5f6b7a"))

    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#7b8491"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#7b8491"/>')

    for strategy in STRATEGIES:
        x = scaled(
            float(rows_by_strategy[strategy][metric]),
            x_min,
            x_max,
            left,
            right,
        )
        y = scaled(
            float(rows_by_strategy[strategy]["delphi_mean_score"]),
            y_min,
            y_max,
            bottom,
            top,
        )
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{STRATEGY_COLORS[strategy]}"/>')
        parts.append(
            svg_text(
                x + 16,
                y - 8,
                SHORT_LABELS[strategy],
                size=12,
                weight="700",
            )
        )

    parts.append(svg_text((left + right) / 2, 615, x_label, size=13, anchor="middle", fill="#5f6b7a"))
    parts.append(
        svg_text(
            35,
            319,
            "Delphi mean score",
            size=13,
            anchor="middle",
            fill="#5f6b7a",
            extra=' transform="rotate(-90 35 319)"',
        )
    )
    parts.append("</svg>")

    print(f"[INFO] Writing plot: {output_path}")
    output_path.write_text("".join(parts), encoding="utf-8")


def write_evidence_index_plot(rows_by_strategy, output_path):
    """
    Write matched technical index versus normalized Delphi preference bars.
    """
    delphi_values = [DELPHI_MEAN_SCORES[strategy] for strategy in STRATEGIES]
    normalized_delphi = normalize_values(delphi_values)

    width = 1080
    height = 610
    left = 245
    bar_width = 330
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        svg_text(34, 40, "Matched technical profile vs Delphi preference", size=23, weight="700"),
        svg_text(
            34,
            64,
            "Both bars use the same six report instances: one technical row and one Delphi mean per strategy.",
            size=13,
            fill="#5f6b7a",
        ),
    ]

    for index, strategy in enumerate(STRATEGIES):
        y = 88 + (index * 64)
        evidence_value = float(rows_by_strategy[strategy]["technical_evidence_index"])
        delphi_value = normalized_delphi[index]
        parts.append(svg_text(227, y + 19, STRATEGY_LABELS[strategy], size=13, weight="700", anchor="end"))
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_width}" height="18" fill="#e8edf3" rx="3"/>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_width * evidence_value:.1f}" height="18" fill="#7c3aed" rx="3"/>')
        parts.append(f'<rect x="{left}" y="{y + 25}" width="{bar_width}" height="18" fill="#e8edf3" rx="3"/>')
        parts.append(f'<rect x="{left}" y="{y + 25}" width="{bar_width * delphi_value:.1f}" height="18" fill="#00897b" rx="3"/>')
        parts.append(svg_text(587, y + 14, f"Evidence {evidence_value:.2f}", fill="#5f6b7a"))
        parts.append(svg_text(587, y + 39, f"Delphi {DELPHI_MEAN_SCORES[strategy]:.2f}", fill="#5f6b7a"))

    parts.append(f'<rect x="{left}" y="572" width="14" height="14" fill="#7c3aed"/>')
    parts.append(svg_text(267, 584, "Matched technical evidence index", size=12))
    parts.append('<rect x="485" y="572" width="14" height="14" fill="#00897b"/>')
    parts.append(svg_text(507, 584, "Normalized Delphi preference", size=12))
    parts.append("</svg>")

    print(f"[INFO] Writing plot: {output_path}")
    output_path.write_text("".join(parts), encoding="utf-8")


def write_rank_plot(rows_by_strategy, output_path):
    """
    Write a matched rank comparison plot.
    """
    technical_ranks = rank_values(rows_by_strategy, "technical_evidence_index")
    delphi_ranks = rank_values(rows_by_strategy, "delphi_mean_score")

    width = 1040
    height = 560
    left = 240
    right = 760
    top = 95
    row_gap = 58
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        svg_text(34, 42, "Matched technical rank vs Delphi rank", size=23, weight="700"),
        svg_text(
            34,
            66,
            "Technical ranks use only the same six report instances evaluated by the Delphi panel.",
            size=13,
            fill="#5f6b7a",
        ),
        svg_text(left, 110, "Technical evidence rank", size=13, weight="700", anchor="middle"),
        svg_text(right, 110, "Delphi preference rank", size=13, weight="700", anchor="middle"),
    ]

    for index, strategy in enumerate(STRATEGIES):
        y = top + 55 + (index * row_gap)
        parts.append(f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="#d9dee7"/>')
        parts.append(f'<circle cx="{left}" cy="{y}" r="10" fill="{STRATEGY_COLORS[strategy]}"/>')
        parts.append(f'<circle cx="{right}" cy="{y}" r="10" fill="{STRATEGY_COLORS[strategy]}"/>')
        parts.append(svg_text(34, y + 5, STRATEGY_LABELS[strategy], size=13, weight="700"))
        parts.append(svg_text(left - 22, y + 5, f"{technical_ranks[strategy]:.1f}", anchor="end", fill="#5f6b7a"))
        parts.append(svg_text(right + 22, y + 5, f"{delphi_ranks[strategy]:.1f}", fill="#5f6b7a"))

    parts.append("</svg>")

    print(f"[INFO] Writing plot: {output_path}")
    output_path.write_text("".join(parts), encoding="utf-8")


def main():
    """
    Regenerate matched Delphi comparison plots.
    """
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "shared_data" / "explorer" / "delphi_evaluation_analysis" / "plots"
    rows_by_strategy = load_matched_rows(repo_root)
    add_evidence_index(rows_by_strategy)

    write_rank_plot(
        rows_by_strategy,
        output_dir / "unsupervised_vs_delphi_rank_comparison.svg",
    )
    write_scatter_plot(
        rows_by_strategy,
        "cited_daily_article_count",
        "Matched evidence coverage vs Delphi mean score",
        "Compares the cited daily article count of the exact Delphi report instance with expert-perceived quality.",
        "Cited daily article count in matched report",
        output_dir / "unsupervised_coverage_vs_delphi_score.svg",
    )
    write_scatter_plot(
        rows_by_strategy,
        "llm_total_tokens",
        "Matched token cost vs Delphi mean score",
        "Compares token use of the exact Delphi report instance with expert-perceived quality.",
        "Total tokens in matched report",
        output_dir / "unsupervised_cost_vs_delphi_score.svg",
    )
    write_evidence_index_plot(
        rows_by_strategy,
        output_dir / "unsupervised_evidence_index_vs_delphi_preference.svg",
    )


if __name__ == "__main__":
    main()
