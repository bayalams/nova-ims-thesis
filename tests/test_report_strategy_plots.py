"""
Tests for report strategy comparison plot helpers.
"""

import json
import tempfile
import unittest
from pathlib import Path

import matplotlib
from matplotlib import pyplot as plt

matplotlib.use("Agg")

from explorer.scripts.plot_report_strategy_comparison import build_heatmap_values
from explorer.scripts.plot_report_strategy_comparison import build_heatmap_metric_labels
from explorer.scripts.plot_report_strategy_comparison import build_metric_value_list
from explorer.scripts.plot_report_strategy_comparison import build_profile_values
from explorer.scripts.plot_report_strategy_comparison import build_selected_plot_keys
from explorer.scripts.plot_report_strategy_comparison import build_strategy_averages
from explorer.scripts.plot_report_strategy_comparison import build_strategy_metric_series
from explorer.scripts.plot_report_strategy_comparison import configure_plot_text_style
from explorer.scripts.plot_report_strategy_comparison import load_evaluation_rows
from explorer.scripts.plot_report_strategy_comparison import parse_arguments
from explorer.scripts.plot_report_strategy_comparison import plot_coverage_diversity_groundedness_bars
from explorer.scripts.plot_report_strategy_comparison import plot_coverage_diversity_scatter
from explorer.scripts.plot_report_strategy_comparison import plot_evidence_stack
from explorer.scripts.plot_report_strategy_comparison import plot_quality_cost_scatter
from explorer.scripts.plot_report_strategy_comparison import plot_rag_usage_bars
from explorer.scripts.plot_report_strategy_comparison import plot_rag_usage_dumbbell
from explorer.scripts.plot_report_strategy_comparison import plot_rag_usage_scatter
from explorer.scripts.plot_report_strategy_comparison import plot_runtime_bars
from explorer.scripts.plot_report_strategy_comparison import plot_runtime_per_article_bars
from explorer.scripts.plot_report_strategy_comparison import plot_runtime_vs_article_coverage_scatter
from explorer.scripts.plot_report_strategy_comparison import plot_strategy_heatmap
from explorer.scripts.plot_report_strategy_comparison import save_current_plot
from explorer.scripts.plot_report_strategy_comparison import OUTPUT_DPI
from explorer.scripts.plot_report_strategy_comparison import RUN_FOLDERS


class ReportStrategyPlotTests(unittest.TestCase):
    def test_run_folders_cover_may_1_through_23(self):
        expected = []
        for day in range(1, 24):
            expected.append(f"2026-05-{day:02d}_news_no_chunking_3large_100articles")

        self.assertEqual(RUN_FOLDERS, expected)

    def test_load_evaluation_rows_reads_strategy_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "evaluation.json"
            payload = [
                {"strategy": "simple", "llm_prompt_tokens": 10, "llm_completion_tokens": 5},
                {"strategy": "react-basic", "llm_prompt_tokens": 20, "llm_completion_tokens": 7},
            ]
            path.write_text(json.dumps(payload), encoding="utf-8")

            rows = load_evaluation_rows(path)

        self.assertEqual([row["strategy"] for row in rows], ["simple", "react-basic"])
        self.assertEqual(rows[0]["llm_total_tokens"], 15)
        self.assertEqual(rows[1]["llm_total_tokens"], 27)

    def test_build_strategy_averages_computes_means_for_each_strategy(self):
        all_rows = [
            {"strategy": "simple", "cited_daily_article_count": 10, "llm_total_tokens": 100},
            {"strategy": "simple", "cited_daily_article_count": 14, "llm_total_tokens": 140},
            {"strategy": "react-basic", "cited_daily_article_count": 20, "llm_total_tokens": 200},
            {"strategy": "react-basic", "cited_daily_article_count": 22, "llm_total_tokens": 260},
        ]

        averages = build_strategy_averages(
            all_rows,
            ["cited_daily_article_count", "llm_total_tokens"],
        )

        self.assertEqual(averages["simple"]["cited_daily_article_count"], 12.0)
        self.assertEqual(averages["simple"]["llm_total_tokens"], 120.0)
        self.assertEqual(averages["react-basic"]["cited_daily_article_count"], 21.0)
        self.assertEqual(averages["react-basic"]["llm_total_tokens"], 230.0)

    def test_build_heatmap_values_inverts_cost_metrics(self):
        averages = {
            "simple": {
                "cited_daily_article_count": 10.0,
                "runtime_seconds": 100.0,
                "llm_total_tokens": 500.0,
            },
            "react-map-reduce": {
                "cited_daily_article_count": 20.0,
                "runtime_seconds": 300.0,
                "llm_total_tokens": 900.0,
            },
        }

        values = build_heatmap_values(
            averages,
            ["simple", "react-map-reduce"],
            ["cited_daily_article_count", "runtime_seconds", "llm_total_tokens"],
        )

        self.assertEqual(values[0][1], 1.0)
        self.assertEqual(values[1][1], 0.0)
        self.assertEqual(values[0][2], 1.0)
        self.assertEqual(values[1][2], 0.0)

    def test_build_heatmap_metric_labels_renames_cost_metrics_as_efficiency(self):
        labels = build_heatmap_metric_labels(
            ["cited_daily_article_count", "runtime_seconds", "llm_total_tokens"]
        )

        self.assertEqual(
            labels,
            ["article coverage", "runtime efficiency", "token efficiency"],
        )

    def test_build_strategy_metric_series_groups_values_by_run_order(self):
        rows = [
            {
                "strategy": "simple",
                "run_folder": "run-b",
                "cited_daily_article_count": 12,
            },
            {
                "strategy": "simple",
                "run_folder": "run-a",
                "cited_daily_article_count": 10,
            },
            {
                "strategy": "react-basic",
                "run_folder": "run-a",
                "cited_daily_article_count": 20,
            },
            {
                "strategy": "react-basic",
                "run_folder": "run-b",
                "cited_daily_article_count": 22,
            },
        ]

        run_labels, series = build_strategy_metric_series(
            rows,
            "cited_daily_article_count",
            ["run-a", "run-b"],
        )

        self.assertEqual(run_labels, ["run-a", "run-b"])
        self.assertEqual(series["simple"], [10.0, 12.0])
        self.assertEqual(series["react-basic"], [20.0, 22.0])

    def test_build_profile_values_normalizes_benefit_and_cost_metrics(self):
        averages = {
            "simple": {
                "cited_daily_article_count": 10.0,
                "distinct_cited_sources": 3.0,
                "cited_line_ratio": 0.4,
                "llm_total_tokens": 500.0,
            },
            "react-basic": {
                "cited_daily_article_count": 20.0,
                "distinct_cited_sources": 5.0,
                "cited_line_ratio": 0.2,
                "llm_total_tokens": 900.0,
            },
        }

        labels, values = build_profile_values(
            averages,
            ["simple", "react-basic"],
            [
                "cited_daily_article_count",
                "distinct_cited_sources",
                "cited_line_ratio",
                "llm_total_tokens",
            ],
        )

        self.assertEqual(
            labels,
            ["article coverage", "source diversity", "groundedness", "token efficiency"],
        )
        self.assertEqual(values["simple"], [0.0, 0.0, 1.0, 1.0])
        self.assertEqual(values["react-basic"], [1.0, 1.0, 0.0, 0.0])

    def test_build_profile_values_for_parallel_plot_keeps_metric_order(self):
        averages = {
            "simple": {
                "cited_daily_article_count": 10.0,
                "distinct_cited_sources": 4.0,
                "cited_line_ratio": 0.5,
            },
            "react-basic": {
                "cited_daily_article_count": 20.0,
                "distinct_cited_sources": 6.0,
                "cited_line_ratio": 0.3,
            },
        }

        labels, values = build_profile_values(
            averages,
            ["simple", "react-basic"],
            [
                "cited_daily_article_count",
                "distinct_cited_sources",
                "cited_line_ratio",
            ],
        )

        self.assertEqual(
            labels,
            ["article coverage", "source diversity", "groundedness"],
        )
        self.assertEqual(len(values["simple"]), 3)

    def test_build_metric_value_list_returns_strategy_ordered_values(self):
        averages = {
            "simple": {"cited_daily_article_count": 10.0},
            "react-basic": {"cited_daily_article_count": 20.0},
        }

        values = build_metric_value_list(
            averages,
            ["simple", "react-basic"],
            "cited_daily_article_count",
        )

        self.assertEqual(values, [10.0, 20.0])

    def test_parse_arguments_defaults_to_all_plots(self):
        arguments = parse_arguments([])

        self.assertEqual(arguments.plot, "all")

    def test_parse_arguments_accepts_one_plot_name(self):
        arguments = parse_arguments(["--plot", "rag-bars"])

        self.assertEqual(arguments.plot, "rag-bars")

    def test_build_selected_plot_keys_returns_every_plot_for_all(self):
        plot_keys = build_selected_plot_keys("all")

        self.assertEqual(
            plot_keys,
            [
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
            ],
        )

    def test_build_selected_plot_keys_returns_one_plot_for_specific_name(self):
        plot_keys = build_selected_plot_keys("rag-scatter")

        self.assertEqual(plot_keys, ["rag-scatter"])

    def test_plot_quality_cost_scatter_uses_readable_labels_without_title(self):
        averages = {
            "simple": {"llm_total_tokens": 1000.0, "cited_daily_article_count": 29.0},
            "react-basic": {"llm_total_tokens": 2000.0, "cited_daily_article_count": 26.0},
            "react-map-reduce": {"llm_total_tokens": 3000.0, "cited_daily_article_count": 46.62},
            "react-triage": {"llm_total_tokens": 4000.0, "cited_daily_article_count": 18.0},
            "react-hybrid": {"llm_total_tokens": 5000.0, "cited_daily_article_count": 25.5},
            "react-progressive": {"llm_total_tokens": 6000.0, "cited_daily_article_count": 26.5},
        }

        plot_quality_cost_scatter(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_title(), "")
        self.assertLessEqual(axis.xaxis.label.get_fontsize(), 11)
        self.assertLessEqual(axis.yaxis.label.get_fontsize(), 11)
        self.assertGreaterEqual(axis.xaxis.labelpad, 12)
        self.assertGreaterEqual(axis.yaxis.labelpad, 12)
        labels = []
        for text in axis.texts:
            labels.append(text.get_text().strip())
            self.assertLessEqual(text.get_fontsize(), 10)
        self.assertEqual(
            labels,
            [
                "Simple",
                "ReAct Basic",
                "ReAct Map-Reduce",
                "ReAct Triage",
                "ReAct Hybrid",
                "ReAct Progressive",
            ],
        )

        plt.close("all")

    def test_configure_plot_text_style_uses_larger_fonts(self):
        configure_plot_text_style()

        self.assertGreaterEqual(matplotlib.rcParams["font.size"], 13)
        self.assertGreaterEqual(matplotlib.rcParams["axes.titlesize"], 16)
        self.assertGreaterEqual(matplotlib.rcParams["axes.labelsize"], 14)
        self.assertGreaterEqual(matplotlib.rcParams["xtick.labelsize"], 12)
        self.assertGreaterEqual(matplotlib.rcParams["ytick.labelsize"], 12)

    def test_save_current_plot_writes_svg_at_300_dpi(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plt.figure()
            plt.plot([1, 2], [3, 4])

            output_path = save_current_plot(Path(temp_dir), "heatmap")

            self.assertEqual(output_path.name, "heatmap.svg")
            self.assertEqual(OUTPUT_DPI, 300)
            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("<svg", content)

        plt.close("all")

    def test_plot_strategy_heatmap_uses_thesis_labels_without_extra_text(self):
        averages = {}
        for index, strategy in enumerate([
            "simple",
            "react-basic",
            "react-map-reduce",
            "react-triage",
            "react-hybrid",
            "react-progressive",
        ], start=1):
            averages[strategy] = {
                "cited_daily_article_count": index,
                "cited_daily_article_rate": index + 1,
                "distinct_cited_sources": index + 2,
                "cited_rag_article_count": index + 3,
                "cited_rag_article_rate": index + 4,
                "runtime_seconds": index + 5,
                "llm_total_tokens": index + 6,
            }

        plot_strategy_heatmap(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        colorbar_axis = figure.axes[1]

        self.assertEqual(axis.get_title(), "")
        self.assertEqual(len(figure.texts), 0)
        self.assertEqual(colorbar_axis.get_ylabel(), "")

        y_labels = []
        for label in axis.get_yticklabels():
            y_labels.append(label.get_text())

        self.assertEqual(
            y_labels,
            [
                "Simple",
                "ReAct Basic",
                "ReAct Map-Reduce",
                "ReAct Triage",
                "ReAct Hybrid",
                "ReAct Progressive",
            ],
        )

        x_labels = []
        for label in axis.get_xticklabels():
            x_labels.append(label.get_text().replace("\n", " "))

        self.assertEqual(
            x_labels,
            [
                "Article Coverage",
                "Daily Citation Rate",
                "Source Diversity",
                "KB Evidence Count",
                "KB Evidence Rate",
                "Runtime Efficiency",
                "Token Efficiency",
            ],
        )
        for label in axis.get_xticklabels() + axis.get_yticklabels():
            self.assertGreaterEqual(label.get_fontsize(), 14)

        plt.close("all")

    def test_plot_coverage_diversity_scatter_uses_side_legend(self):
        averages = {
            "simple": {
                "cited_daily_article_count": 29.0,
                "distinct_cited_sources": 29.0,
            },
            "react-basic": {
                "cited_daily_article_count": 26.0,
                "distinct_cited_sources": 29.0,
            },
            "react-map-reduce": {
                "cited_daily_article_count": 46.62,
                "distinct_cited_sources": 50.38,
            },
            "react-triage": {
                "cited_daily_article_count": 18.0,
                "distinct_cited_sources": 21.0,
            },
            "react-hybrid": {
                "cited_daily_article_count": 25.5,
                "distinct_cited_sources": 28.0,
            },
            "react-progressive": {
                "cited_daily_article_count": 26.5,
                "distinct_cited_sources": 29.0,
            },
        }

        plot_coverage_diversity_scatter(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(len(axis.texts), 0)
        self.assertLessEqual(axis.xaxis.label.get_fontsize(), 11)
        self.assertLessEqual(axis.yaxis.label.get_fontsize(), 11)
        self.assertGreaterEqual(axis.xaxis.labelpad, 12)
        self.assertGreaterEqual(axis.yaxis.labelpad, 12)

        legend = axis.get_legend()
        self.assertIsNotNone(legend)
        self.assertEqual(legend.get_title().get_text(), "Strategy")

        legend_labels = []
        for text in legend.get_texts():
            legend_labels.append(text.get_text())

        self.assertEqual(
            legend_labels,
            [
                "Simple",
                "ReAct Basic",
                "ReAct Map-Reduce",
                "ReAct Triage",
                "ReAct Progressive",
                "ReAct Hybrid",
            ],
        )
        self.assertLessEqual(legend.get_bbox_to_anchor()._bbox.x0, 1.03)

        plt.close("all")

    def test_plot_runtime_bars_creates_one_bar_chart(self):
        averages = {
            "simple": {"runtime_seconds": 109.27},
            "react-basic": {"runtime_seconds": 250.0},
            "react-map-reduce": {"runtime_seconds": 335.46},
            "react-triage": {"runtime_seconds": 280.0},
            "react-hybrid": {"runtime_seconds": 206.69},
            "react-progressive": {"runtime_seconds": 360.02},
        }

        plot_runtime_bars(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_title(), "Runtime by Strategy")
        self.assertEqual(axis.get_ylabel(), "Average Runtime (seconds)")
        self.assertEqual(len(axis.containers), 1)
        for label in axis.get_xticklabels():
            self.assertEqual(label.get_rotation(), 0.0)

        plt.close("all")

    def test_plot_runtime_per_article_bars_creates_one_bar_chart(self):
        averages = {
            "simple": {"runtime_seconds": 100.0, "cited_daily_article_count": 20.0},
            "react-basic": {"runtime_seconds": 240.0, "cited_daily_article_count": 24.0},
            "react-map-reduce": {"runtime_seconds": 300.0, "cited_daily_article_count": 50.0},
            "react-triage": {"runtime_seconds": 180.0, "cited_daily_article_count": 18.0},
            "react-hybrid": {"runtime_seconds": 210.0, "cited_daily_article_count": 30.0},
            "react-progressive": {"runtime_seconds": 330.0, "cited_daily_article_count": 33.0},
        }

        plot_runtime_per_article_bars(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_title(), "Runtime Per Cited Daily Article")
        self.assertEqual(axis.get_ylabel(), "Seconds per cited daily article")
        self.assertEqual(len(axis.containers), 1)

        plt.close("all")

    def test_plot_runtime_vs_article_coverage_scatter_uses_point_labels(self):
        averages = {
            "simple": {"runtime_seconds": 109.27, "cited_daily_article_count": 29.0},
            "react-basic": {"runtime_seconds": 250.0, "cited_daily_article_count": 26.0},
            "react-map-reduce": {"runtime_seconds": 335.46, "cited_daily_article_count": 46.62},
            "react-triage": {"runtime_seconds": 280.0, "cited_daily_article_count": 18.0},
            "react-hybrid": {"runtime_seconds": 206.69, "cited_daily_article_count": 25.5},
            "react-progressive": {"runtime_seconds": 360.02, "cited_daily_article_count": 26.5},
        }

        plot_runtime_vs_article_coverage_scatter(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_title(), "")
        self.assertEqual(axis.get_xlabel(), "Average Runtime (seconds)")
        self.assertEqual(axis.get_ylabel(), "Average Cited Daily Article Count")
        self.assertLessEqual(axis.xaxis.label.get_fontsize(), 11)
        self.assertLessEqual(axis.yaxis.label.get_fontsize(), 11)
        self.assertGreaterEqual(axis.xaxis.labelpad, 12)
        self.assertGreaterEqual(axis.yaxis.labelpad, 12)
        self.assertEqual(len(axis.texts), 6)
        labels = []
        for text in axis.texts:
            labels.append(text.get_text())
            self.assertLessEqual(text.get_fontsize(), 10)
        self.assertEqual(
            labels,
            [
                "Simple",
                "ReAct Basic",
                "ReAct Map-Reduce",
                "ReAct Triage",
                "ReAct Hybrid",
                "ReAct Progressive",
            ],
        )
        self.assertIsNone(axis.get_legend())

        plt.close("all")

    def test_plot_evidence_stack_uses_grouped_bars(self):
        averages = {
            "simple": {
                "cited_daily_article_count": 29.0,
                "cited_rag_article_count": 0.0,
            },
            "react-basic": {
                "cited_daily_article_count": 26.0,
                "cited_rag_article_count": 2.0,
            },
            "react-map-reduce": {
                "cited_daily_article_count": 46.62,
                "cited_rag_article_count": 3.75,
            },
            "react-triage": {
                "cited_daily_article_count": 18.0,
                "cited_rag_article_count": 3.2,
            },
            "react-hybrid": {
                "cited_daily_article_count": 25.5,
                "cited_rag_article_count": 2.4,
            },
            "react-progressive": {
                "cited_daily_article_count": 26.5,
                "cited_rag_article_count": 2.1,
            },
        }

        plot_evidence_stack(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_title(), "")
        self.assertEqual(len(axis.containers), 2)
        self.assertEqual(axis.containers[0].get_label(), "Daily cited articles")
        self.assertEqual(axis.containers[1].get_label(), "KB cited articles")
        tick_labels = []
        for label in axis.get_xticklabels():
            tick_labels.append(label.get_text().replace("\n", " "))
        self.assertEqual(
            tick_labels,
            [
                "Simple",
                "ReAct Basic",
                "ReAct Map-Reduce",
                "ReAct Triage",
                "ReAct Hybrid",
                "ReAct Progressive",
            ],
        )

        first_daily_bar_x = axis.containers[0][0].get_x()
        first_rag_bar_x = axis.containers[1][0].get_x()
        self.assertNotEqual(first_daily_bar_x, first_rag_bar_x)

        plt.close("all")

    def test_plot_rag_usage_bars_creates_two_panel_figure(self):
        averages = {
            "simple": {"cited_rag_article_count": 0.0, "cited_rag_article_rate": 0.0},
            "react-basic": {"cited_rag_article_count": 2.0, "cited_rag_article_rate": 0.22},
            "react-map-reduce": {"cited_rag_article_count": 3.75, "cited_rag_article_rate": 0.4864},
            "react-triage": {"cited_rag_article_count": 3.2, "cited_rag_article_rate": 0.44},
            "react-hybrid": {"cited_rag_article_count": 2.4, "cited_rag_article_rate": 0.31},
            "react-progressive": {"cited_rag_article_count": 2.1, "cited_rag_article_rate": 0.28},
        }

        plot_rag_usage_bars(averages)

        figure = plt.gcf()
        self.assertEqual(len(figure.axes), 2)
        self.assertEqual(figure.axes[0].get_title(), "Cited RAG Article Count")
        self.assertEqual(figure.axes[1].get_title(), "Cited RAG Article Rate")

        plt.close("all")

    def test_plot_rag_usage_scatter_uses_side_legend(self):
        averages = {
            "simple": {"cited_rag_article_count": 0.0, "cited_rag_article_rate": 0.0},
            "react-basic": {"cited_rag_article_count": 2.0, "cited_rag_article_rate": 0.22},
            "react-map-reduce": {"cited_rag_article_count": 3.75, "cited_rag_article_rate": 0.4864},
            "react-triage": {"cited_rag_article_count": 3.2, "cited_rag_article_rate": 0.44},
            "react-hybrid": {"cited_rag_article_count": 2.4, "cited_rag_article_rate": 0.31},
            "react-progressive": {"cited_rag_article_count": 2.1, "cited_rag_article_rate": 0.28},
        }

        plot_rag_usage_scatter(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(len(axis.texts), 0)
        legend = axis.get_legend()
        self.assertIsNotNone(legend)
        self.assertEqual(legend.get_title().get_text(), "Strategy")

        plt.close("all")

    def test_plot_rag_usage_dumbbell_creates_one_axis_with_two_labels(self):
        averages = {
            "simple": {"cited_rag_article_count": 0.0, "cited_rag_article_rate": 0.0},
            "react-basic": {"cited_rag_article_count": 2.0, "cited_rag_article_rate": 0.22},
            "react-map-reduce": {"cited_rag_article_count": 3.75, "cited_rag_article_rate": 0.4864},
            "react-triage": {"cited_rag_article_count": 3.2, "cited_rag_article_rate": 0.44},
            "react-hybrid": {"cited_rag_article_count": 2.4, "cited_rag_article_rate": 0.31},
            "react-progressive": {"cited_rag_article_count": 2.1, "cited_rag_article_rate": 0.28},
        }

        plot_rag_usage_dumbbell(averages)

        figure = plt.gcf()
        axis = figure.axes[0]
        self.assertEqual(axis.get_xlabel(), "Normalized RAG usage")

        legend = axis.get_legend()
        self.assertIsNotNone(legend)
        legend_labels = [text.get_text() for text in legend.get_texts()]
        self.assertEqual(legend_labels, ["Count", "Rate"])

        plt.close("all")

    def test_core_bars_leave_room_for_value_labels(self):
        averages = {
            "simple": {
                "cited_daily_article_count": 29.0,
                "distinct_cited_sources": 29.0,
                "cited_line_ratio": 0.28,
            },
            "react-basic": {
                "cited_daily_article_count": 26.0,
                "distinct_cited_sources": 29.0,
                "cited_line_ratio": 0.25,
            },
            "react-map-reduce": {
                "cited_daily_article_count": 46.62,
                "distinct_cited_sources": 49.9,
                "cited_line_ratio": 0.379,
            },
            "react-triage": {
                "cited_daily_article_count": 18.0,
                "distinct_cited_sources": 21.0,
                "cited_line_ratio": 0.18,
            },
            "react-hybrid": {
                "cited_daily_article_count": 25.5,
                "distinct_cited_sources": 28.0,
                "cited_line_ratio": 0.22,
            },
            "react-progressive": {
                "cited_daily_article_count": 26.5,
                "distinct_cited_sources": 29.0,
                "cited_line_ratio": 0.24,
            },
        }

        plot_coverage_diversity_groundedness_bars(averages)

        figure = plt.gcf()
        visible_axes = []
        for axis in figure.axes:
            if axis.get_visible():
                visible_axes.append(axis)

        max_values = [46.62, 49.9, 0.379]
        for axis, max_value in zip(visible_axes, max_values):
            self.assertGreaterEqual(axis.get_xlim()[1], max_value * 1.25)

        plt.close("all")
