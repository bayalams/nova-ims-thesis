"""
Tests for the fixed chunking Pareto plot.
"""

import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import unittest

from explorer.scripts.plot_chunking_pareto import CHUNKING_ROWS
from explorer.scripts.plot_chunking_pareto import build_table_rows
from explorer.scripts.plot_chunking_pareto import plot_chunking_pareto
from explorer.scripts.plot_chunking_pareto import save_current_plot


class ChunkingParetoPlotTests(unittest.TestCase):
    def test_build_table_rows_returns_only_table_combinations(self):
        rows = build_table_rows()

        self.assertEqual(len(rows), 6)
        self.assertEqual(
            [row["label"] for row in rows],
            ["4000/400", "3000/300", "2500/250", "2000/200", "1500/150", "1000/100"],
        )
        self.assertEqual(rows[0]["total_chunks"], 42573)
        self.assertEqual(rows[-1]["two_plus_chunk_rate"], 92.4)

    def test_plot_chunking_pareto_matches_scatter_style(self):
        import matplotlib.pyplot as plt

        plot_chunking_pareto(CHUNKING_ROWS)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_title(), "")
        self.assertEqual(axis.get_xlabel(), "Total Chunks in Corpus")
        self.assertEqual(axis.get_ylabel(), "Articles Still in 2+ Chunks (%)")
        self.assertEqual(len(axis.texts), 0)
        self.assertEqual(len(axis.lines), 1)
        self.assertEqual(axis.lines[0].get_linestyle(), "--")
        self.assertEqual(axis.lines[0].get_color(), "#222222")
        legend = axis.get_legend()
        self.assertIsNotNone(legend)
        labels = []
        for text in legend.get_texts():
            labels.append(text.get_text())
        self.assertEqual(
            labels,
            ["4000/400", "3000/300", "2500/250", "2000/200", "1500/150", "1000/100"],
        )

        plt.close("all")

    def test_save_current_plot_writes_svg(self):
        import matplotlib.pyplot as plt

        with tempfile.TemporaryDirectory() as temp_dir:
            plot_chunking_pareto(CHUNKING_ROWS)
            output_path = save_current_plot(Path(temp_dir))

            self.assertEqual(output_path.name, "chunking_pareto.svg")
            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("<svg", content)

        plt.close("all")
