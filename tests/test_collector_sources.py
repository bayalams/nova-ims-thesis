"""
Tests for RSS source configuration and source name selection.

These tests protect CLI behavior:
- source names are stored in uppercase
- users type lowercase names with underscores
- unknown names stop the command before work starts
"""

import unittest

from collector.feeds.sources import RSS_SOURCES
from collector.feeds.sources import get_enabled_sources
from collector.feeds.sources import select_sources


class CollectorSourceTests(unittest.TestCase):
    def test_sources_include_previous_repo_examples(self):
        source_names = []

        for source in RSS_SOURCES:
            source_names.append(source["name"])

        self.assertIn("PUBLICO", source_names)
        self.assertIn("BBC", source_names)
        self.assertIn("AL_JAZEERA", source_names)

    def test_all_selects_every_enabled_source(self):
        selected_sources = select_sources(["all"])
        enabled_sources = get_enabled_sources()

        self.assertEqual(len(selected_sources), len(enabled_sources))
        self.assertGreater(len(selected_sources), 50)

    def test_lowercase_names_select_canonical_sources(self):
        selected_sources = select_sources(["publico", "al_jazeera", "bbc_travel"])
        selected_names = []

        for source in selected_sources:
            selected_names.append(source["name"])

        self.assertEqual(selected_names, ["PUBLICO", "AL_JAZEERA", "BBC_TRAVEL"])

    def test_unknown_source_stops_with_clear_error(self):
        with self.assertRaises(ValueError) as error:
            select_sources(["not_a_source"])

        self.assertIn("Unknown source", str(error.exception))
        self.assertIn("not_a_source", str(error.exception))

    def test_all_cannot_be_mixed_with_specific_sources(self):
        with self.assertRaises(ValueError) as error:
            select_sources(["all", "publico"])

        self.assertIn("Use either 'all'", str(error.exception))


if __name__ == "__main__":
    unittest.main()
