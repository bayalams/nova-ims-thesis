"""
Tests for the reporting CLI.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from reporting import cli
from reporting.strategies.context_construction import validate_context_strategy


class ReportingCliTests(unittest.TestCase):
    def test_help_mentions_context_strategy(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli.main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("--context-strategy", output.getvalue())

    def test_status_defaults_missing_context_strategy_to_simple(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli.main(["status"])

        self.assertEqual(exit_code, 0)
        lines = output.getvalue().splitlines()
        self.assertIn("[1/2] daily_simple: context_strategy=simple", lines)
        self.assertIn("[2/2] daily_tourism_intelligence: context_strategy=simple", lines)

    def test_validate_context_strategy_accepts_known_name(self):
        self.assertEqual(validate_context_strategy("react-basic"), "react-basic")

    def test_validate_context_strategy_rejects_unknown_name(self):
        with self.assertRaises(ValueError) as error:
            validate_context_strategy("not-a-strategy")

        self.assertIn("Unknown context strategy", str(error.exception))

    def test_run_passes_context_strategy_and_yes_flag(self):
        with patch("reporting.cli.run_report_recipe") as fake_run:
            exit_code = cli.main([
                "run",
                "daily_tourism_intelligence",
                "--context-strategy",
                "simple",
                "--article-date",
                "2026-04-10",
                "--yes",
            ])

        self.assertEqual(exit_code, 0)
        fake_run.assert_called_once_with(
            "daily_tourism_intelligence",
            context_strategy="simple",
            article_date="2026-04-10",
            report_datetime=None,
            hours=None,
            knowledge_base_recipe=None,
            max_iterations=None,
            candidate_limit=None,
            yes=True,
        )

    def test_run_unknown_flag_returns_error(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli.main(["run", "daily_tourism_intelligence", "--bad-flag"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Unknown report run option", output.getvalue())

    def test_run_command_dispatches_with_flags(self):
        with patch("reporting.cli.run_report_recipe") as fake_run:
            exit_code = cli.main([
                "run",
                "daily_tourism_intelligence",
                "--context-strategy",
                "simple",
                "--yes",
            ])

        self.assertEqual(exit_code, 0)
        fake_run.assert_called_once_with(
            "daily_tourism_intelligence",
            context_strategy="simple",
            article_date=None,
            report_datetime=None,
            hours=None,
            knowledge_base_recipe=None,
            max_iterations=None,
            candidate_limit=None,
            yes=True,
        )

    def test_run_batch_dispatches_with_run_name_and_flags(self):
        with patch("reporting.cli.run_report_batch") as fake_batch:
            exit_code = cli.main([
                "run-batch",
                "daily_tourism_intelligence",
                "--article-date",
                "2026-05-13",
                "--run-name",
                "may13_context_check",
                "--yes",
            ])

        self.assertEqual(exit_code, 0)
        fake_batch.assert_called_once_with(
            "daily_tourism_intelligence",
            article_date="2026-05-13",
            report_datetime=None,
            hours=None,
            knowledge_base_recipe=None,
            max_iterations=None,
            candidate_limit=None,
            run_name="may13_context_check",
            strategy_delay_seconds=None,
            yes=True,
        )

    def test_run_batch_dispatches_with_strategy_delay_seconds(self):
        with patch("reporting.cli.run_report_batch") as fake_batch:
            exit_code = cli.main([
                "run-batch",
                "daily_tourism_intelligence",
                "--article-date",
                "2026-05-13",
                "--strategy-delay-seconds",
                "60",
                "--yes",
            ])

        self.assertEqual(exit_code, 0)
        fake_batch.assert_called_once_with(
            "daily_tourism_intelligence",
            article_date="2026-05-13",
            report_datetime=None,
            hours=None,
            knowledge_base_recipe=None,
            max_iterations=None,
            candidate_limit=None,
            run_name=None,
            strategy_delay_seconds=60,
            yes=True,
        )

    def test_render_viewer_dispatches_with_run_folder(self):
        with patch("reporting.cli.write_report_batch_viewer") as fake_viewer:
            exit_code = cli.main([
                "render-viewer",
                "shared_data/reports/may13_context_check",
            ])

        self.assertEqual(exit_code, 0)
        fake_viewer.assert_called_once_with("shared_data/reports/may13_context_check")

    def test_evaluate_run_dispatches_with_run_folder(self):
        with patch("reporting.cli.evaluate_report_run_folder") as fake_evaluate:
            exit_code = cli.main([
                "evaluate-run",
                "shared_data/reports/may13_context_check",
            ])

        self.assertEqual(exit_code, 0)
        fake_evaluate.assert_called_once_with("shared_data/reports/may13_context_check")

    def test_sort_batch_dispatches_with_run_folder(self):
        with patch("reporting.cli.sort_report_batch_markdown") as fake_sort:
            exit_code = cli.main([
                "sort-batch",
                "shared_data/reports/may13_context_check",
            ])

        self.assertEqual(exit_code, 0)
        fake_sort.assert_called_once_with("shared_data/reports/may13_context_check")
