"""
Tests for knowledge-base and reporting recipe helpers.
"""

import unittest
from unittest.mock import patch

from knowledge_bases.build_knowledge_base import explain_recipe_text
from knowledge_bases.build_knowledge_base import load_recipe
from reporting.create_report import explain_report_recipe_text
from reporting.create_report import load_prompt_text
from reporting.create_report import load_report_recipe
from reporting.create_report import run_report_recipe


class KnowledgeBaseRecipeTests(unittest.TestCase):
    def test_load_kb_recipe_reads_name(self):
        recipe = load_recipe("news_no_chunking_3small")

        self.assertEqual(recipe["name"], "news_no_chunking_3small")
        self.assertEqual(recipe["output_folder"], "shared_data/knowledge_bases/news_no_chunking_3small")

    def test_explain_kb_recipe_mentions_key_choices(self):
        text = explain_recipe_text("news_no_chunking_3small")

        self.assertIn("none", text)
        self.assertIn("shared_data/corpus/news/clean/articles", text)
        self.assertIn("shared_data/knowledge_bases/news_no_chunking_3small", text)


class ReportingRecipeTests(unittest.TestCase):
    def test_load_report_recipe_reads_name(self):
        recipe = load_report_recipe("daily_simple")

        self.assertEqual(recipe["name"], "daily_simple")
        self.assertEqual(recipe["output_folder"], "shared_data/reports")

    def test_explain_report_recipe_mentions_key_choices(self):
        text = explain_report_recipe_text("daily_simple")

        self.assertIn("daily_simple", text)
        self.assertIn("shared_data/corpus/news/clean/articles", text)
        self.assertIn("shared_data/reports", text)

    def test_load_daily_tourism_recipe_reads_context_strategy(self):
        recipe = load_report_recipe("daily_tourism_intelligence")

        self.assertEqual(recipe["name"], "daily_tourism_intelligence")
        self.assertEqual(recipe["context_strategy"], "simple")
        self.assertEqual(recipe["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
        self.assertEqual(recipe["candidate_selector"], "embedding_prototypes")
        self.assertEqual(recipe["input_corpus"], "shared_data/corpus/news/clean/articles")
        self.assertEqual(recipe["max_iterations"], 15)

    def test_explain_daily_tourism_recipe_mentions_context_strategy(self):
        text = explain_report_recipe_text("daily_tourism_intelligence")

        self.assertIn("daily_tourism_intelligence", text)
        self.assertIn("Context strategy: simple", text)
        self.assertIn("shared_data/reports", text)

    def test_load_prompt_text_reads_markdown_prompt(self):
        text = load_prompt_text("reporting/prompts/daily_tourism_system.md")

        self.assertIn("Daily Tourism Intelligence Report", text)
        self.assertIn("[Source N]", text)

    def test_run_daily_tourism_recipe_without_articles_fails_clearly(self):
        with patch("reporting.create_report.load_clean_articles", return_value=[]):
            with self.assertRaises(ValueError) as error:
                run_report_recipe("daily_tourism_intelligence")

        self.assertEqual(str(error.exception), "No clean articles found inside the report day")


if __name__ == "__main__":
    unittest.main()
