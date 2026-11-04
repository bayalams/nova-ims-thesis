"""
Create Delphi evaluation plots from the 10-participant questionnaire CSV.
"""

import csv
import re
import statistics
from pathlib import Path


DELPHI_CSV_PATH = Path(
    "/Users/beatrizsaraiva/Documents/Project/"
    "Painel Delphi: Avaliação de Relatórios de Inteligência Turística Gerados por IA 3.csv"
)

STRATEGIES = {
    1: "Simple",
    2: "ReAct Basic",
    3: "ReAct Map-Reduce",
    4: "ReAct Triage",
    5: "ReAct Hybrid",
    6: "ReAct Progressive",
}

CRITERION_LABELS = {
    "Relevância dos artigos": "Article relevance",
    "Clareza": "Clarity",
    "Tópicos acionáveis": "Actionable topics",
    "Capacidade de síntese/ ausência de repetição": "Synthesis",
    "Repetição da informação": "Synthesis",
    "Adequação do nível de detalhe": "Level of detail",
    "Relação custo/ benefício": "Cost-benefit",
}

CRITERIA = [
    "Article relevance",
    "Clarity",
    "Actionable topics",
    "Synthesis",
    "Level of detail",
    "Cost-benefit",
]

STRATEGY_COLORS = {
    "Simple": "#6b7280",
    "ReAct Basic": "#2f67d8",
    "ReAct Map-Reduce": "#7c3aed",
    "ReAct Triage": "#e11d48",
    "ReAct Hybrid": "#00897b",
    "ReAct Progressive": "#f59e0b",
}


def clean_criterion_name(column_name):
    """
    Extract and normalize one criterion name from a CSV column.
    """
    match = re.search(r"\[(.*?)\]", column_name, flags=re.DOTALL)
    if not match:
        return ""

    original = " ".join(match.group(1).split()).strip()
    return CRITERION_LABELS.get(original, original)


def build_score_columns(fieldnames):
    """
    Group CSV score columns by strategy and criterion.
    """
    score_columns = {}
    for strategy in STRATEGIES.values():
        score_columns[strategy] = {}
        for criterion in CRITERIA:
            score_columns[strategy][criterion] = []

    for column_name in fieldnames:
        report_match = re.search(r"Relatório\s+(\d+)\.", column_name or "")
        if not report_match:
            continue
        if "[" not in column_name:
            continue

        report_number = int(report_match.group(1))
        if report_number not in STRATEGIES:
            continue

        strategy = STRATEGIES[report_number]
        criterion = clean_criterion_name(column_name)
        if criterion not in CRITERIA:
            continue

        score_columns[strategy][criterion].append(column_name)

    return score_columns


def read_delphi_scores(csv_path):
    """
    Read raw criterion scores and participant-level means.
    """
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        score_columns = build_score_columns(reader.fieldnames)

        criterion_scores = {}
        participant_means = {}
        for strategy in STRATEGIES.values():
            criterion_scores[strategy] = {}
            participant_means[strategy] = []
            for criterion in CRITERIA:
                criterion_scores[strategy][criterion] = []

        for row in reader:
            for strategy in STRATEGIES.values():
                participant_values = []
                for criterion in CRITERIA:
                    for column_name in score_columns[strategy][criterion]:
                        raw_value = (row.get(column_name) or "").strip().replace(",", ".")
                        try:
                            value = float(raw_value)
                        except ValueError:
                            continue

                        criterion_scores[strategy][criterion].append(value)
                        participant_values.append(value)

                if participant_values:
                    participant_mean = sum(participant_values) / len(participant_values)
                    participant_means[strategy].append(participant_mean)

    return criterion_scores, participant_means


def mean(values):
    """
    Return the arithmetic mean.
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


def standard_deviation(values):
    """
    Return sample standard deviation.
    """
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def plot_criterion_profile(criterion_scores, output_path):
    """
    Plot mean criterion scores for every strategy.
    """
    import matplotlib.pyplot as plt

    x_positions = list(range(len(CRITERIA)))

    plt.figure(figsize=(12, 6))
    for strategy in STRATEGIES.values():
        y_values = []
        for criterion in CRITERIA:
            y_values.append(mean(criterion_scores[strategy][criterion]))

        plt.plot(
            x_positions,
            y_values,
            marker="o",
            linewidth=2,
            label=strategy,
            color=STRATEGY_COLORS[strategy],
        )

    plt.title("Delphi Criterion Profile by Strategy")
    plt.ylabel("Mean Likert score")
    plt.ylim(1, 7)
    plt.xticks(x_positions, CRITERIA, rotation=20, ha="right")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), title="Strategy")
    plt.tight_layout(rect=(0, 0, 0.82, 1))
    print(f"[INFO] Writing plot: {output_path}")
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_overall_mean_barh(participant_means, output_path):
    """
    Plot overall mean score by strategy as a horizontal bar chart.
    """
    import matplotlib.pyplot as plt

    rows = []
    for strategy in STRATEGIES.values():
        rows.append(
            {
                "strategy": strategy,
                "mean": mean(participant_means[strategy]),
            }
        )

    rows = sorted(rows, key=lambda row: row["mean"], reverse=True)
    y_positions = list(range(len(rows)))

    plt.figure(figsize=(9.5, 5.6))
    for index, row in enumerate(rows):
        strategy = row["strategy"]
        strategy_mean = row["mean"]
        color = STRATEGY_COLORS[strategy]
        plt.barh(
            index,
            strategy_mean - 1,
            left=1,
            color=color,
            height=0.62,
        )
        plt.text(
            strategy_mean + 0.06,
            index,
            f"{strategy_mean:.2f}",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
            color="#1f2933",
        )

    plt.title("Mean Score by Report Strategy")
    plt.xlabel("Mean evaluation score")
    plt.ylabel("Strategy")
    plt.xlim(1, 7)
    plt.xticks([1, 2, 3, 4, 5, 6, 7])
    plt.yticks(y_positions, [row["strategy"] for row in rows])
    plt.gca().invert_yaxis()
    plt.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    print(f"[INFO] Writing plot: {output_path}")
    plt.savefig(output_path)
    plt.close()


def plot_strategy_dispersion(participant_means, output_path):
    """
    Plot participant-level mean score dispersion for every strategy.
    """
    import matplotlib.pyplot as plt

    strategies = list(STRATEGIES.values())
    y_positions = list(range(len(strategies)))

    plt.figure(figsize=(10, 6))
    for index, strategy in enumerate(strategies):
        values = participant_means[strategy]
        strategy_mean = mean(values)
        strategy_sd = standard_deviation(values)
        minimum = min(values)
        maximum = max(values)

        plt.hlines(
            y=index,
            xmin=minimum,
            xmax=maximum,
            color="#c7ccd4",
            linewidth=5,
            label="Min-max range" if index == 0 else None,
        )
        plt.errorbar(
            strategy_mean,
            index,
            xerr=strategy_sd,
            fmt="o",
            color=STRATEGY_COLORS[strategy],
            ecolor=STRATEGY_COLORS[strategy],
            capsize=5,
            markersize=8,
            label="Mean +/- SD" if index == 0 else None,
        )
        plt.text(
            maximum + 0.08,
            index + 0.08,
            f"M={strategy_mean:.2f}",
            fontsize=9,
            color="#4b5563",
        )

    plt.title("Delphi Participant-Score Dispersion by Strategy")
    plt.xlabel("Participant mean score across six criteria")
    plt.yticks(y_positions, strategies)
    plt.xlim(1, 7.4)
    plt.grid(True, axis="x", alpha=0.3)
    plt.legend(loc="upper left")
    plt.tight_layout()
    print(f"[INFO] Writing plot: {output_path}")
    plt.savefig(output_path, dpi=200)
    plt.close()


def clean_filename(text):
    """
    Convert a plot title into a simple file name.
    """
    clean_text = text.lower()
    clean_text = clean_text.replace("/", " ")
    clean_text = clean_text.replace("-", " ")
    clean_text = "_".join(clean_text.split())
    return clean_text


def plot_violin_by_criterion(criterion_scores, output_dir):
    """
    Create one violin plot per criterion.
    """
    import matplotlib.pyplot as plt

    strategies = list(STRATEGIES.values())
    x_positions = list(range(1, len(strategies) + 1))

    for criterion in CRITERIA:
        values_by_strategy = []
        for strategy in strategies:
            values_by_strategy.append(criterion_scores[strategy][criterion])

        plt.figure(figsize=(11, 6))
        violin_parts = plt.violinplot(
            values_by_strategy,
            positions=x_positions,
            widths=0.75,
            showmeans=True,
            showmedians=True,
            showextrema=True,
        )

        for index, body in enumerate(violin_parts["bodies"]):
            strategy = strategies[index]
            body.set_facecolor(STRATEGY_COLORS[strategy])
            body.set_edgecolor("#111827")
            body.set_alpha(0.35)

        for part_name in ["cmeans", "cmedians", "cmins", "cmaxes", "cbars"]:
            if part_name in violin_parts:
                violin_parts[part_name].set_color("#111827")
                violin_parts[part_name].set_linewidth(1.2)

        for strategy_index, strategy in enumerate(strategies):
            values = values_by_strategy[strategy_index]
            x_value = x_positions[strategy_index]
            for value_index, value in enumerate(values):
                jitter = ((value_index % 5) - 2) * 0.035
                plt.scatter(
                    x_value + jitter,
                    value,
                    color=STRATEGY_COLORS[strategy],
                    edgecolor="white",
                    linewidth=0.7,
                    s=34,
                    alpha=0.85,
                    zorder=3,
                )

        plt.title(f"Delphi Evaluation Distribution: {criterion}")
        plt.xlabel("Strategy")
        plt.ylabel("Evaluation score")
        plt.ylim(0.8, 7.2)
        plt.yticks([1, 2, 3, 4, 5, 6, 7])
        plt.xticks(x_positions, strategies, rotation=25, ha="right")
        plt.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()

        output_path = output_dir / f"delphi_violin_{clean_filename(criterion)}.png"
        print(f"[INFO] Writing plot: {output_path}")
        plt.savefig(output_path, dpi=200)
        plt.close()


def plot_boxplot_by_criterion(criterion_scores, output_dir):
    """
    Create one boxplot per criterion.
    """
    import matplotlib.pyplot as plt

    strategies = list(STRATEGIES.values())
    x_positions = list(range(1, len(strategies) + 1))

    for criterion in CRITERIA:
        values_by_strategy = []
        for strategy in strategies:
            values_by_strategy.append(criterion_scores[strategy][criterion])

        plt.figure(figsize=(11, 6))
        box_parts = plt.boxplot(
            values_by_strategy,
            positions=x_positions,
            widths=0.55,
            patch_artist=True,
            showmeans=True,
            showfliers=False,
            medianprops={"color": "#111827", "linewidth": 2},
            meanprops={
                "marker": "D",
                "markerfacecolor": "white",
                "markeredgecolor": "#111827",
                "markersize": 6,
            },
            boxprops={"edgecolor": "#111827", "linewidth": 1.2},
            whiskerprops={"color": "#111827", "linewidth": 1.2},
            capprops={"color": "#111827", "linewidth": 1.2},
        )

        for index, box in enumerate(box_parts["boxes"]):
            strategy = strategies[index]
            box.set_facecolor(STRATEGY_COLORS[strategy])
            box.set_alpha(0.35)

        for strategy_index, strategy in enumerate(strategies):
            values = values_by_strategy[strategy_index]
            x_value = x_positions[strategy_index]
            for value_index, value in enumerate(values):
                jitter = ((value_index % 5) - 2) * 0.035
                plt.scatter(
                    x_value + jitter,
                    value,
                    color=STRATEGY_COLORS[strategy],
                    edgecolor="white",
                    linewidth=0.7,
                    s=34,
                    alpha=0.8,
                    zorder=3,
                )

        plt.title(f"Delphi Evaluation Boxplot: {criterion}")
        plt.xlabel("Strategy")
        plt.ylabel("Evaluation score")
        plt.ylim(0.8, 7.2)
        plt.yticks([1, 2, 3, 4, 5, 6, 7])
        plt.xticks(x_positions, strategies, rotation=25, ha="right")
        plt.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()

        output_path = output_dir / f"delphi_boxplot_{clean_filename(criterion)}.png"
        print(f"[INFO] Writing plot: {output_path}")
        plt.savefig(output_path, dpi=200)
        plt.close()


def main():
    """
    Create the Delphi result plots.
    """
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "shared_data" / "explorer" / "delphi_evaluation_analysis" / "plots"
    criterion_scores, participant_means = read_delphi_scores(DELPHI_CSV_PATH)

    plot_overall_mean_barh(
        participant_means,
        output_dir / "overall_mean_by_strategy.svg",
    )
    plot_overall_mean_barh(
        participant_means,
        output_dir / "overall_mean_by_strategy.png",
    )
    plot_criterion_profile(
        criterion_scores,
        output_dir / "delphi_criterion_profile_by_strategy.png",
    )
    plot_strategy_dispersion(
        participant_means,
        output_dir / "delphi_participant_dispersion_by_strategy.png",
    )
    plot_violin_by_criterion(
        criterion_scores,
        output_dir,
    )
    plot_boxplot_by_criterion(
        criterion_scores,
        output_dir,
    )


if __name__ == "__main__":
    main()
