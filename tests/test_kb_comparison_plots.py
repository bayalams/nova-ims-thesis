"""
Tests for KB comparison plot helpers.
"""

import json
import tempfile
import unittest
from pathlib import Path

import matplotlib
from matplotlib import pyplot as plt

matplotlib.use("Agg")

from explorer.scripts.plot_kb_comparison import build_heatmap_values
from explorer.scripts.plot_kb_comparison import build_recipe_display_names
from explorer.scripts.plot_kb_comparison import build_metric_value_list
from explorer.scripts.plot_kb_comparison import build_plot_rows
from explorer.scripts.plot_kb_comparison import load_evaluation_report
from explorer.scripts.plot_kb_comparison import plot_grouped_metric_bars


class KnowledgeBaseComparisonPlotTests(unittest.TestCase):
    def test_load_evaluation_report_reads_recipe_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "evaluation.json"
            payload = {
                "recipes": [
                    {"recipe_name": "recipe-a", "status": "evaluated"},
                    {"recipe_name": "recipe-b", "status": "error"},
                ]
            }
            report_path.write_text(json.dumps(payload), encoding="utf-8")

            report = load_evaluation_report(report_path)

        self.assertEqual(len(report["recipes"]), 2)
        self.assertEqual(report["recipes"][0]["recipe_name"], "recipe-a")

    def test_build_plot_rows_flattens_recipe_metrics(self):
        report = {
            "recipes": [
                {
                    "recipe_name": "recipe-a",
                    "status": "evaluated",
                    "sanity_metrics": {
                        "article_coverage_rate": 1.0,
                        "chunk_count": 100,
                        "db_size_bytes": 1048576,
                        "query_latency_ms": 50.0,
                        "chunk_size_characters": {"average": 400.0},
                        "chunks_per_article": {"average": 2.0},
                    },
                    "thesis_metrics": {
                        "article_self_retrieval_top_5_rate": 0.9,
                        "story_level_top_k_diversity": 0.8,
                        "lead_paragraph_intact_rate": 0.7,
                        "boundary_break_rate": 0.1,
                        "boilerplate_contamination_rate": 0.05,
                        "entity_pair_preservation_rate": 0.95,
                    },
                    "diagnostic_metrics": {
                        "duplicate_chunk_rate": 0.02,
                    },
                    "retrieval_metrics": {
                        "self_retrieval": {
                            "title_mrr": 0.8,
                            "summary_mrr": 0.75,
                        },
                        "top_k_crowding": {
                            "unique_articles_top_10": 7.0,
                            "max_same_article_share": 0.3,
                        },
                    },
                },
                {
                    "recipe_name": "recipe-b",
                    "status": "error",
                },
            ]
        }

        rows = build_plot_rows(report)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recipe"], "recipe-a")
        self.assertEqual(rows[0]["chunks"], 100.0)
        self.assertEqual(rows[0]["db_size_mb"], 1.0)
        self.assertEqual(rows[0]["article_self_retrieval_top_5_rate"], 0.9)
        self.assertEqual(rows[0]["unique_articles_top_10"], 7.0)

    def test_build_heatmap_values_inverts_cost_metrics(self):
        rows = [
            {
                "recipe": "recipe-a",
                "article_coverage_rate": 0.9,
                "query_latency_ms": 50.0,
                "db_size_mb": 100.0,
            },
            {
                "recipe": "recipe-b",
                "article_coverage_rate": 1.0,
                "query_latency_ms": 200.0,
                "db_size_mb": 300.0,
            },
        ]

        values = build_heatmap_values(
            rows,
            ["recipe-a", "recipe-b"],
            ["article_coverage_rate", "query_latency_ms", "db_size_mb"],
        )

        self.assertEqual(values[0][0], 0.0)
        self.assertEqual(values[1][0], 1.0)
        self.assertEqual(values[0][1], 1.0)
        self.assertEqual(values[1][1], 0.0)
        self.assertEqual(values[0][2], 1.0)
        self.assertEqual(values[1][2], 0.0)

    def test_build_metric_value_list_returns_recipe_ordered_values(self):
        rows = [
            {"recipe": "recipe-a", "chunks": 100.0},
            {"recipe": "recipe-b", "chunks": 50.0},
        ]

        values = build_metric_value_list(rows, ["recipe-b", "recipe-a"], "chunks")

        self.assertEqual(values, [50.0, 100.0])

    def test_build_recipe_display_names_shortens_kb_recipe_ids(self):
        labels = build_recipe_display_names(
            [
                "news_fixed_2000_overlap_3large",
                "news_no_chunking_3small",
                "news_recursive_2000_overlap_3large",
            ]
        )

        self.assertEqual(
            labels,
            ["Fixed 2000 L", "No Chunk S", "Recursive 2000 L"],
        )

    def test_plot_grouped_metric_bars_accepts_multiple_metric_specs(self):
        rows = [
            {
                "recipe": "recipe-a",
                "chunks": 100.0,
                "average_chunk_characters": 400.0,
            },
            {
                "recipe": "recipe-b",
                "chunks": 50.0,
                "average_chunk_characters": 800.0,
            },
        ]

        plot_grouped_metric_bars(
            rows,
            ["recipe-a", "recipe-b"],
            [
                ("chunks", "Chunks", "Count"),
                ("average_chunk_characters", "Avg Chunk Chars", "Characters"),
            ],
            "Example",
        )

        plt.close("all")

    def test_plot_grouped_metric_bars_uses_two_by_two_layout_for_four_metrics(self):
        rows = [
            {
                "recipe": "news_fixed_2000_overlap_3large",
                "chunks": 100.0,
                "average_chunk_characters": 400.0,
                "average_chunks_per_article": 3.0,
                "db_size_mb": 10.0,
            },
            {
                "recipe": "news_no_chunking_3small",
                "chunks": 50.0,
                "average_chunk_characters": 800.0,
                "average_chunks_per_article": 1.0,
                "db_size_mb": 5.0,
            },
        ]

        plot_grouped_metric_bars(
            rows,
            ["news_fixed_2000_overlap_3large", "news_no_chunking_3small"],
            [
                ("chunks", "Chunks", "Count"),
                ("average_chunk_characters", "Avg Chunk Chars", "Characters"),
                ("average_chunks_per_article", "Avg Chunks/Article", "Count"),
                ("db_size_mb", "DB Size", "MiB"),
            ],
            "KB Size And Structure",
        )

        figure = plt.gcf()
        axes = figure.axes
        self.assertEqual(len(axes), 4)

        grid_positions = []
        for axis in axes:
            subplot_spec = axis.get_subplotspec()
            grid_positions.append((subplot_spec.rowspan.start, subplot_spec.colspan.start))

        self.assertEqual(
            grid_positions,
            [(0, 0), (0, 1), (1, 0), (1, 1)],
        )

        width, height = figure.get_size_inches()
        self.assertEqual((width, height), (12.0, 8.0))

        plt.close("all")

    def test_plot_grouped_metric_bars_uses_three_plus_two_layout_for_five_metrics(self):
        rows = [
            {
                "recipe": "news_fixed_2000_overlap_3large",
                "lead_paragraph_intact_rate": 0.8,
                "boundary_break_rate": 0.1,
                "boilerplate_contamination_rate": 0.05,
                "entity_pair_preservation_rate": 0.9,
                "duplicate_chunk_rate": 0.02,
            },
            {
                "recipe": "news_no_chunking_3small",
                "lead_paragraph_intact_rate": 0.6,
                "boundary_break_rate": 0.2,
                "boilerplate_contamination_rate": 0.1,
                "entity_pair_preservation_rate": 0.7,
                "duplicate_chunk_rate": 0.04,
            },
        ]

        plot_grouped_metric_bars(
            rows,
            ["news_fixed_2000_overlap_3large", "news_no_chunking_3small"],
            [
                ("lead_paragraph_intact_rate", "Lead Intact", "Rate"),
                ("boundary_break_rate", "Boundary Breaks", "Rate"),
                ("boilerplate_contamination_rate", "Boilerplate", "Rate"),
                ("entity_pair_preservation_rate", "Entity Pairs", "Rate"),
                ("duplicate_chunk_rate", "Duplicate Chunks", "Rate"),
            ],
            "Text Integrity",
        )

        figure = plt.gcf()
        axes = figure.axes
        self.assertEqual(len(axes), 6)

        grid_positions = []
        for axis in axes[:5]:
            subplot_spec = axis.get_subplotspec()
            grid_positions.append((subplot_spec.rowspan.start, subplot_spec.colspan.start))

        self.assertEqual(
            grid_positions,
            [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)],
        )
        self.assertFalse(axes[5].get_visible())

        width, height = figure.get_size_inches()
        self.assertEqual((width, height), (18.0, 8.0))

        plt.close("all")
