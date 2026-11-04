"""
Tests for explorer command routing.
"""

import unittest
from unittest.mock import patch

from explorer import cli


class ExplorerCliTests(unittest.TestCase):
    def test_no_arguments_prints_explorer_overview(self):
        with patch("builtins.print") as fake_print:
            exit_code = cli.main([])

        self.assertEqual(exit_code, 0)
        printed_text = "\n".join(str(call.args[0]) for call in fake_print.call_args_list)
        self.assertIn("Explorer", printed_text)
        self.assertIn("corpus-inspector", printed_text)

    def test_corpus_inspector_index_dispatches(self):
        with patch("explorer.webapps.corpus_inspector.indexer.build_corpus_index") as fake_index:
            fake_index.return_value = {"article_count": 3, "index_path": "tmp/index.sqlite"}
            exit_code = cli.main(["corpus-inspector", "index"])

        self.assertEqual(exit_code, 0)
        fake_index.assert_called_once()
        self.assertEqual(fake_index.call_args.kwargs, {})

    def test_corpus_inspector_index_accepts_custom_paths(self):
        with patch("explorer.webapps.corpus_inspector.indexer.build_corpus_index") as fake_index:
            fake_index.return_value = {"article_count": 0, "index_path": "custom.sqlite"}
            exit_code = cli.main([
                "corpus-inspector",
                "index",
                "--raw-dir",
                "raw",
                "--clean-dir",
                "clean",
                "--index-path",
                "custom.sqlite",
                "--minimum-text-characters",
                "50",
            ])

        self.assertEqual(exit_code, 0)
        call_kwargs = fake_index.call_args.kwargs
        self.assertEqual(str(call_kwargs["raw_dir"]), "raw")
        self.assertEqual(str(call_kwargs["clean_dir"]), "clean")
        self.assertEqual(str(call_kwargs["index_path"]), "custom.sqlite")
        self.assertEqual(call_kwargs["minimum_text_characters"], 50)

    def test_corpus_inspector_status_dispatches(self):
        with patch("explorer.webapps.corpus_inspector.indexer.get_index_status") as fake_status:
            fake_status.return_value = {"exists": False, "index_path": "tmp/index.sqlite"}
            exit_code = cli.main(["corpus-inspector", "status"])

        self.assertEqual(exit_code, 0)
        fake_status.assert_called_once()

    def test_corpus_inspector_status_accepts_custom_index_path(self):
        with patch("explorer.webapps.corpus_inspector.indexer.get_index_status") as fake_status:
            fake_status.return_value = {"exists": True, "index_path": "custom.sqlite", "article_count": 7}
            exit_code = cli.main([
                "corpus-inspector",
                "status",
                "--index-path",
                "custom.sqlite",
            ])

        self.assertEqual(exit_code, 0)
        call_kwargs = fake_status.call_args.kwargs
        self.assertEqual(str(call_kwargs["index_path"]), "custom.sqlite")

    def test_corpus_inspector_serve_dispatches_without_kwargs(self):
        with patch("explorer.webapps.corpus_inspector.server.serve_corpus_inspector") as fake_serve:
            fake_serve.return_value = 0
            exit_code = cli.main(["corpus-inspector", "serve"])

        self.assertEqual(exit_code, 0)
        fake_serve.assert_called_once()
        self.assertEqual(fake_serve.call_args.kwargs, {})

    def test_corpus_inspector_serve_accepts_host_port_and_index_path(self):
        with patch("explorer.webapps.corpus_inspector.server.serve_corpus_inspector") as fake_serve:
            fake_serve.return_value = 0
            exit_code = cli.main([
                "corpus-inspector",
                "serve",
                "--index-path",
                "custom.sqlite",
                "--host",
                "0.0.0.0",
                "--port",
                "9999",
            ])

        self.assertEqual(exit_code, 0)
        call_kwargs = fake_serve.call_args.kwargs
        self.assertEqual(str(call_kwargs["index_path"]), "custom.sqlite")
        self.assertEqual(call_kwargs["host"], "0.0.0.0")
        self.assertEqual(call_kwargs["port"], 9999)

    def test_unknown_corpus_inspector_command_returns_error(self):
        with patch("builtins.print") as fake_print:
            exit_code = cli.main(["corpus-inspector", "unknown"])

        self.assertEqual(exit_code, 1)
        printed_text = "\n".join(str(call.args[0]) for call in fake_print.call_args_list)
        self.assertIn("[ERROR]", printed_text)


if __name__ == "__main__":
    unittest.main()
