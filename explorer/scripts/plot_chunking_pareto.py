"""
Plot the fixed chunking Pareto figure using only the table combinations.
"""

import argparse
from pathlib import Path


CHUNKING_ROWS = [
    {"label": "4000/400", "total_chunks": 42573, "two_plus_chunk_rate": 52.9},
    {"label": "3000/300", "total_chunks": 52726, "two_plus_chunk_rate": 65.6},
    {"label": "2500/250", "total_chunks": 60870, "two_plus_chunk_rate": 72.4},
    {"label": "2000/200", "total_chunks": 73350, "two_plus_chunk_rate": 79.6},
    {"label": "1500/150", "total_chunks": 94086, "two_plus_chunk_rate": 87.0},
    {"label": "1000/100", "total_chunks": 135300, "two_plus_chunk_rate": 92.4},
]

POINT_COLORS = ["tab:purple", "tab:cyan", "tab:green", "goldenrod", "tomato", "tab:blue"]
OUTPUT_DPI = 300
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "shared_data"
    / "explorer"
    / "chunking_pareto_plots"
)


def parse_arguments(arguments):
    """
    Parse command-line arguments for the chunking Pareto plot.
    """
    parser = argparse.ArgumentParser(
        description="Open and save the fixed chunking Pareto figure.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Folder where the SVG plot should be saved.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Save the SVG without opening an interactive Matplotlib window.",
    )
    return parser.parse_args(arguments)


def build_table_rows():
    """
    Return the fixed table combinations in plot order.
    """
    rows = []
    for row in CHUNKING_ROWS:
        rows.append(dict(row))
    return rows


def plot_chunking_pareto(rows):
    """
    Plot the fixed chunking trade-off with a side legend and a Pareto line.
    """
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(11, 6))

    x_values = []
    y_values = []
    for row in rows:
        x_values.append(row["total_chunks"])
        y_values.append(row["two_plus_chunk_rate"])

    for index, row in enumerate(rows):
        axis.scatter(
            row["total_chunks"],
            row["two_plus_chunk_rate"],
            s=90,
            color=POINT_COLORS[index % len(POINT_COLORS)],
            label=row["label"],
        )

    axis.plot(x_values, y_values, linestyle="--", color="#222222", linewidth=1.2)
    axis.set_xlabel("Total Chunks in Corpus", fontsize=11, labelpad=12)
    axis.set_ylabel("Articles Still in 2+ Chunks (%)", fontsize=11, labelpad=12)
    axis.grid(True, alpha=0.3)
    axis.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False, title=None)
    plt.tight_layout(rect=(0, 0, 0.86, 1))


def save_current_plot(output_dir):
    """
    Save the current Matplotlib figure as a 300-DPI SVG.
    """
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "chunking_pareto.svg"
    plt.gcf().savefig(
        output_path,
        format="svg",
        dpi=OUTPUT_DPI,
        bbox_inches="tight",
    )
    return output_path


def main(arguments=None):
    """
    Open and save the fixed chunking Pareto figure.
    """
    import matplotlib.pyplot as plt

    parsed_arguments = parse_arguments(arguments)

    print("[INFO] Opening fixed chunking Pareto figure")
    plot_chunking_pareto(build_table_rows())
    output_path = save_current_plot(parsed_arguments.output_dir)
    print(f"[INFO] Saved SVG plot: {output_path}")

    if not parsed_arguments.no_show:
        plt.show()


if __name__ == "__main__":
    main()
