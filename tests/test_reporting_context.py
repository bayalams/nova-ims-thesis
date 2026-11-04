"""
Tests for reporting context helpers.
"""

import copy
import os
import tempfile
import unittest
from unittest.mock import patch

from reporting.create_report import make_hybrid_score_function
from reporting.create_report import parse_json_array_from_text
from reporting.context.daily_articles import get_article_id
from reporting.context.daily_articles import get_article_text
from reporting.context.daily_articles import parse_report_datetime
from reporting.context.daily_articles import select_articles_for_report_day
from reporting.context.daily_articles import select_articles_for_window
from reporting.context.kb_context import format_kb_results_as_sources
from reporting.context.source_registry import build_sources_section
from reporting.context.source_registry import extract_cited_source_numbers
from reporting.context.source_registry import finalize_report_text
from reporting.context.source_registry import make_source_registry
from reporting.context.source_registry import register_daily_articles
from reporting.context.source_registry import register_rag_source
from reporting.context.source_registry import sort_report_batch_markdown
from reporting.context.source_registry import strip_model_sources_section
from reporting.strategies.context_construction import build_map_reduce_context
from reporting.strategies.context_construction import build_progressive_context
from reporting.strategies.context_construction import build_hybrid_context
from reporting.strategies.context_construction import build_react_basic_context
from reporting.strategies.context_construction import build_context_from_selected_articles
from reporting.strategies.context_construction import build_simple_context
from reporting.strategies.context_construction import build_triage_context
from reporting.strategies.context_construction import split_batches


class DailyArticleContextTests(unittest.TestCase):
    def test_parse_report_datetime_uses_end_of_day_for_date(self):
        parsed = parse_report_datetime("2026-04-10")

        self.assertEqual(parsed.isoformat(), "2026-04-10T23:59:59+00:00")

    def test_select_articles_for_window_keeps_only_articles_inside_window(self):
        articles = [
            {
                "id": "inside",
                "published_at": "2026-04-10T12:00:00+00:00",
                "metadata": {"title": "Inside"},
                "text": "Inside text",
            },
            {
                "id": "old",
                "published_at": "2026-04-08T12:00:00+00:00",
                "metadata": {"title": "Old"},
                "text": "Old text",
            },
        ]

        selected = select_articles_for_window(articles, "2026-04-10", 24)

        self.assertEqual([article["id"] for article in selected], ["inside"])

    def test_select_articles_for_window_accepts_rss_published_metadata(self):
        articles = [
            {
                "id": "rss",
                "metadata": {"published": "Thu, 07 May 2026 12:00:00 GMT"},
                "text": "RSS text",
            }
        ]

        selected = select_articles_for_window(articles, "2026-05-07", 24)

        self.assertEqual([article["id"] for article in selected], ["rss"])

    def test_select_articles_for_window_does_not_mutate_articles(self):
        article = {
            "id": "inside",
            "published_at": "2026-04-10T12:00:00+00:00",
            "metadata": {"title": "Inside"},
            "text": "Inside text",
        }

        select_articles_for_window([article], "2026-04-10", 24)

        self.assertNotIn("_parsed_datetime", article)

    def test_select_articles_for_report_day_keeps_only_selected_calendar_day(self):
        articles = [
            {
                "id": "previous-day",
                "published_at": "2026-04-09T23:59:59+00:00",
                "metadata": {"title": "Previous"},
                "text": "Previous text",
            },
            {
                "id": "same-day",
                "published_at": "2026-04-10T08:00:00+00:00",
                "metadata": {"title": "Same"},
                "text": "Same text",
            },
            {
                "id": "next-day",
                "published_at": "2026-04-11T00:00:00+00:00",
                "metadata": {"title": "Next"},
                "text": "Next text",
            },
        ]

        selected = select_articles_for_report_day(articles, "2026-04-10")

        self.assertEqual([article["id"] for article in selected], ["same-day"])

    def test_get_article_text_prefers_top_level_text(self):
        article = {
            "text": "Top-level text",
            "clean_text": "Clean text",
            "content": "Raw content",
            "metadata": {"summary": "Summary"},
        }

        self.assertEqual(get_article_text(article), "Top-level text")

    def test_get_article_text_uses_clean_text_before_content_and_summary(self):
        article = {
            "text": "   ",
            "clean_text": "Clean text",
            "content": "Raw content",
            "metadata": {"summary": "Summary"},
        }

        self.assertEqual(get_article_text(article), "Clean text")

    def test_get_article_text_uses_clean_text_when_text_is_missing(self):
        article = {
            "clean_text": "Clean fallback",
            "content": "Raw content",
            "metadata": {"summary": "Summary"},
        }

        self.assertEqual(get_article_text(article), "Clean fallback")

    def test_get_article_id_uses_stable_fields(self):
        article = {"metadata": {"link": "https://example.com/item"}}

        self.assertEqual(get_article_id(article), "https://example.com/item")


class SourceRegistryTests(unittest.TestCase):
    def test_register_daily_articles_assigns_source_numbers(self):
        registry = make_source_registry()
        articles = [
            {"id": "a1", "metadata": {"title": "One", "source": "PUBLICO"}},
            {"id": "a2", "metadata": {"title": "Two", "source": "BBC"}},
        ]

        register_daily_articles(registry, articles)

        self.assertEqual(registry["daily_article_ids"], ["a1", "a2"])
        self.assertEqual(registry["source_articles"][0]["source_number"], 1)
        self.assertEqual(registry["source_articles"][1]["source_number"], 2)

    def test_register_rag_source_reuses_existing_article_number(self):
        registry = make_source_registry()
        register_daily_articles(registry, [{"id": "a1", "metadata": {"title": "One"}}])

        result = register_rag_source(
            registry,
            article_id="a1",
            title="One",
            source="PUBLICO",
            date="2026-04-10",
            url="https://example.com/one",
            text="Text",
        )

        self.assertEqual(result["source_number"], 1)
        self.assertEqual(registry["rag_source_article_ids"], [])

    def test_extract_cited_source_numbers_reads_standard_citations(self):
        numbers = extract_cited_source_numbers("Claim [Source 2]. Other [Source 1, 3].")

        self.assertEqual(numbers, [1, 2, 3])

    def test_strip_model_sources_section_removes_trailing_sources(self):
        report = "# Report\n\nClaim [Source 1].\n\n---\n\n## Sources\n\n1. Bad"

        stripped = strip_model_sources_section(report)

        self.assertNotIn("1. Bad", stripped)

    def test_strip_model_sources_section_removes_trailing_source_block(self):
        report = (
            "# Report\n\n"
            "Claim [Source 1].\n\n"
            "---\n\n"
            "## Sources\n\n"
            "1. Bad cited source\n\n"
            "## Source Pool\n\n"
            "1. Bad pool source"
        )

        stripped = strip_model_sources_section(report)

        self.assertIn("Claim [Source 1].", stripped)
        self.assertNotIn("Bad cited source", stripped)
        self.assertNotIn("Bad pool source", stripped)
        self.assertNotIn("## Sources", stripped)
        self.assertNotIn("## Source Pool", stripped)

    def test_strip_model_sources_section_preserves_non_trailing_sources(self):
        report = (
            "# Report\n\n"
            "Claim [Source 1].\n\n"
            "## Sources\n\n"
            "This is a real body section.\n\n"
            "## Analyst Notes\n\n"
            "This later section must remain."
        )

        stripped = strip_model_sources_section(report)

        self.assertIn("This is a real body section.", stripped)
        self.assertIn("## Analyst Notes", stripped)
        self.assertIn("This later section must remain.", stripped)

    def test_build_sources_section_lists_cited_and_pool_sources(self):
        registry = make_source_registry()
        articles = [
            {
                "id": "a1",
                "metadata": {
                    "title": "One",
                    "source": "PUBLICO",
                    "date": "2026-04-10",
                    "link": "https://example.com",
                },
            }
        ]
        register_daily_articles(registry, articles)

        section = build_sources_section(registry, [1])

        self.assertIn("## Sources Cited in Report", section)
        self.assertIn("## Source Pool", section)
        self.assertIn("One", section)

    def test_build_sources_section_lists_cited_daily_sources_first_in_pool(self):
        registry = make_source_registry()
        articles = [
            {"id": "a1", "metadata": {"title": "One", "source": "PUBLICO"}},
            {"id": "a2", "metadata": {"title": "Two", "source": "BBC"}},
            {"id": "a3", "metadata": {"title": "Three", "source": "CNN"}},
        ]

        register_daily_articles(registry, articles)

        section = build_sources_section(registry, [2])

        self.assertIn("## Sources Cited in Report", section)
        self.assertIn("## Source Pool", section)
        self.assertIn("2. **Two**", section)

        cited_section = section.split("## Source Pool")[0]
        pool_section = section.split("## Source Pool", 1)[1]

        self.assertIn("2. **Two**", cited_section)
        self.assertLess(pool_section.index("2. **Two**"), pool_section.index("1. **One**"))
        self.assertLess(pool_section.index("1. **One**"), pool_section.index("3. **Three**"))

    def test_build_sources_section_lists_cited_rag_sources_first_in_pool(self):
        registry = make_source_registry()
        articles = [
            {"id": "a1", "metadata": {"title": "One", "source": "PUBLICO"}},
            {"id": "a2", "metadata": {"title": "Two", "source": "BBC"}},
        ]

        register_daily_articles(registry, articles)
        register_rag_source(
            registry,
            article_id="rag-1",
            title="Rag Source",
            source="KB",
            date="2026-04-10",
            url="https://example.com/rag",
            text="RAG text",
        )

        section = build_sources_section(registry, [3])

        self.assertIn("## Sources Cited in Report", section)
        self.assertIn("## Source Pool", section)
        self.assertIn("3. **Rag Source**", section)

        cited_section = section.split("## Source Pool")[0]
        pool_section = section.split("## Source Pool", 1)[1]

        self.assertIn("3. **Rag Source**", cited_section)
        self.assertLess(pool_section.index("3. **Rag Source**"), pool_section.index("1. **One**"))
        self.assertLess(pool_section.index("1. **One**"), pool_section.index("2. **Two**"))

    def test_finalize_report_text_replaces_model_sources_with_registry_sources(self):
        registry = make_source_registry()
        register_daily_articles(registry, [{"id": "a1", "metadata": {"title": "One"}}])
        report = "# Report\n\nClaim [Source 1].\n\n---\n\n## Sources\n\n1. Bad"

        finalized = finalize_report_text(report, registry)

        self.assertIn("Claim [Source 1].", finalized)
        self.assertIn("## Sources Cited in Report", finalized)
        self.assertNotIn("1. Bad", finalized)

    def test_sort_report_batch_markdown_creates_sorted_copy(self):
        original_text = (
            "# Report\n\n"
            "Claim [Source 92].\n\n"
            "---\n\n"
            "## Sources Cited in Report\n\n"
            "92. **KB item** - KB, 2026-05-18 - [link](https://example.com/kb)\n\n"
            "## Source Pool\n\n"
            "92. **KB item** - KB, 2026-05-18 - [link](https://example.com/kb)\n"
            "93. **KB item 2** - KB, 2026-05-17 - [link](https://example.com/kb2)\n"
            "1. **Daily one** - PUBLICO, 2026-05-19 - [link](https://example.com/1)\n"
            "2. **Daily two** - BBC, 2026-05-19 - [link](https://example.com/2)\n"
        )

        with tempfile.TemporaryDirectory() as temp_folder:
            report_path = os.path.join(temp_folder, "react-progressive.md")
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write(original_text)

            summary = sort_report_batch_markdown(temp_folder)
            sorted_path = os.path.join(temp_folder, "react-progressive-sorted.md")

            self.assertEqual(summary["created_count"], 1)
            self.assertTrue(os.path.exists(sorted_path))

            with open(report_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), original_text)

            with open(sorted_path, "r", encoding="utf-8") as handle:
                sorted_text = handle.read()

        self.assertIn("92. **KB item**", sorted_text.split("## Source Pool")[0])

        pool_section = sorted_text.split("## Source Pool", 1)[1]
        self.assertLess(pool_section.index("1. **Daily one**"), pool_section.index("2. **Daily two**"))
        self.assertLess(pool_section.index("2. **Daily two**"), pool_section.index("92. **KB item**"))
        self.assertLess(pool_section.index("92. **KB item**"), pool_section.index("93. **KB item 2**"))

    def test_sort_report_batch_markdown_skips_files_without_source_pool(self):
        with tempfile.TemporaryDirectory() as temp_folder:
            report_path = os.path.join(temp_folder, "simple.md")
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write("# Report\n\nNo sources here.\n")

            summary = sort_report_batch_markdown(temp_folder)

            self.assertEqual(summary["created_count"], 0)
            self.assertFalse(os.path.exists(os.path.join(temp_folder, "simple-sorted.md")))


class KbContextTests(unittest.TestCase):
    def test_format_kb_results_as_sources_registers_retrieved_articles(self):
        registry = make_source_registry()
        register_daily_articles(registry, [{"id": "daily-1", "metadata": {"title": "Daily"}}])
        results = [
            {
                "chunk_id": "chunk-1",
                "article_id": "kb-1",
                "title": "Historical context",
                "source": "SKIFT",
                "published_at": "2026-04-01",
                "url": "https://example.com/kb",
                "chunk_text": "Historical context text.",
            }
        ]

        formatted = format_kb_results_as_sources(registry, results)

        self.assertIn("[Source 2: Historical context]", formatted["context_text"])
        self.assertEqual(formatted["retrieved_chunk_ids"], ["chunk-1"])
        self.assertEqual(registry["rag_source_article_ids"], ["kb-1"])


class ContextConstructionStrategyTests(unittest.TestCase):
    def test_parse_json_array_from_text_returns_empty_list_for_invalid_model_text(self):
        self.assertEqual(parse_json_array_from_text("The answer is probably 1 and 2."), [])
        self.assertEqual(parse_json_array_from_text("Before [not valid json] after"), [])
        self.assertEqual(parse_json_array_from_text('{"index": 1}'), [])

    def test_make_hybrid_score_function_ignores_malformed_model_items(self):
        model_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_calls": 0,
        }
        model_result = {
            "content": (
                '[{"index": 1, "score": 5}, '
                '{"index": "bad", "score": 4}, '
                '{"index": 2, "score": "bad"}, '
                '"bad item", '
                '{"score": 3}]'
            ),
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }

        with patch("reporting.create_report.call_chat_model", return_value=model_result):
            score_function = make_hybrid_score_function(
                client=object(),
                model_name="fake-model",
                prompt_text="Score these titles.",
                model_usage=model_usage,
            )
            scores = score_function("1. [PUBLICO] (2026-04-10) One")

        self.assertEqual(scores, {1: 5})
        self.assertEqual(model_usage["llm_calls"], 1)

    def test_split_batches_rejects_zero_batch_size(self):
        with self.assertRaises(ValueError) as error:
            split_batches(["one"], 0)

        self.assertEqual(str(error.exception), "Batch size must be a positive integer")

    def test_split_batches_rejects_negative_batch_size(self):
        with self.assertRaises(ValueError) as error:
            split_batches(["one"], -1)

        self.assertEqual(str(error.exception), "Batch size must be a positive integer")

    def test_build_simple_context_formats_articles_with_source_numbers(self):
        articles = [
            {
                "id": "a1",
                "text": "Clean article text.",
                "metadata": {
                    "title": "Tourism rises",
                    "source": "PUBLICO",
                    "date": "2026-04-10",
                    "link": "https://example.com/a1",
                },
            }
        ]

        result = build_simple_context(articles)

        self.assertIn("[Source 1: Tourism rises]", result["context_text"])
        self.assertIn("Clean article text.", result["context_text"])
        self.assertEqual(result["registry"]["daily_article_ids"], ["a1"])
        self.assertEqual(result["retrieved_chunk_ids"], [])

    def test_build_simple_context_from_selected_articles_keeps_only_chosen_ids(self):
        articles = [
            {
                "id": "a1",
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {"title": "Airport strike", "source": "PUBLICO", "date": "2026-05-16"},
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {"title": "Hotel demand rises", "source": "ECO", "date": "2026-05-16"},
            },
        ]

        context_result = build_context_from_selected_articles(articles, ["a2"])

        self.assertEqual(context_result["strategy"], "react-triage")
        self.assertEqual(context_result["article_count"], 1)
        self.assertEqual(context_result["registry"]["daily_article_ids"], ["a2"])
        self.assertIn("Hotel demand rises", context_result["context_text"])
        self.assertNotIn("Airport strike", context_result["context_text"])

    def test_build_context_from_selected_articles_uses_metadata_derived_article_id(self):
        articles = [
            {
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {
                    "title": "Airport strike",
                    "source": "PUBLICO",
                    "date": "2026-05-16",
                    "link": "https://example.com/airport-strike",
                },
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {"title": "Hotel demand rises", "source": "ECO", "date": "2026-05-16"},
            },
        ]

        context_result = build_context_from_selected_articles(
            articles,
            ["https://example.com/airport-strike"],
        )

        self.assertEqual(context_result["registry"]["daily_article_ids"], ["https://example.com/airport-strike"])
        self.assertIn("Airport strike", context_result["context_text"])
        self.assertNotIn("Hotel demand rises", context_result["context_text"])

    def test_build_context_from_selected_articles_falls_back_to_full_list_when_ids_do_not_match(self):
        articles = [
            {
                "id": "a1",
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {"title": "Airport strike", "source": "PUBLICO", "date": "2026-05-16"},
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {"title": "Hotel demand rises", "source": "ECO", "date": "2026-05-16"},
            },
        ]

        context_result = build_context_from_selected_articles(articles, ["missing-id"])

        self.assertEqual(context_result["strategy"], "react-triage")
        self.assertEqual(context_result["article_count"], 2)
        self.assertEqual(context_result["registry"]["daily_article_ids"], ["a1", "a2"])
        self.assertIn("Airport strike", context_result["context_text"])
        self.assertIn("Hotel demand rises", context_result["context_text"])

    def test_build_react_basic_context_adds_kb_results_from_fixed_queries(self):
        articles = [
            {
                "id": "a1",
                "text": "Portugal airport demand increased.",
                "metadata": {"title": "Airport demand", "source": "PUBLICO", "date": "2026-04-10"},
            }
        ]

        def fake_search(query):
            return [
                {
                    "chunk_id": "chunk-1",
                    "article_id": "kb-1",
                    "title": "Airport history",
                    "source": "SKIFT",
                    "published_at": "2026-04-01",
                    "url": "https://example.com/kb",
                    "chunk_text": "Earlier airport trend.",
                }
            ]

        result = build_react_basic_context(articles, fake_search, max_queries=1)

        self.assertIn("Airport demand", result["context_text"])
        self.assertIn("Airport history", result["context_text"])
        self.assertEqual(result["retrieved_chunk_ids"], ["chunk-1"])

    def test_build_triage_context_keeps_requested_article_indexes(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]

        def fake_select(title_lines):
            return [2]

        result = build_triage_context(articles, fake_select)

        self.assertEqual(result["strategy"], "react-triage")
        self.assertIn("[Source 1: Two]", result["context_text"])
        self.assertEqual(result["registry"]["daily_article_ids"], ["a2"])

    def test_build_triage_context_falls_back_when_model_selects_nothing(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]

        def fake_select(title_lines):
            return []

        result = build_triage_context(articles, fake_select, max_selected=1)

        self.assertEqual(result["registry"]["daily_article_ids"], ["a1"])

    def test_build_triage_context_ignores_duplicate_and_out_of_range_indexes(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]

        def fake_select(title_lines):
            return [2, 99, 2, 0, -1]

        result = build_triage_context(articles, fake_select)

        self.assertEqual(result["registry"]["daily_article_ids"], ["a2"])

    def test_build_triage_context_does_not_mutate_input_articles(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]
        original_articles = copy.deepcopy(articles)

        def fake_select(title_lines):
            return [2]

        build_triage_context(articles, fake_select)

        self.assertEqual(articles, original_articles)

    def test_build_triage_context_rejects_non_positive_max_selected(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
        ]

        def fake_select(title_lines):
            return [1]

        with self.assertRaises(ValueError) as zero_error:
            build_triage_context(articles, fake_select, max_selected=0)
        self.assertEqual(str(zero_error.exception), "max_selected must be a positive integer")

        with self.assertRaises(ValueError) as negative_error:
            build_triage_context(articles, fake_select, max_selected=-1)
        self.assertEqual(str(negative_error.exception), "max_selected must be a positive integer")

    def test_build_hybrid_context_filters_score_three_and_above(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]

        def fake_score(title_lines):
            return {1: 2, 2: 4}

        result = build_hybrid_context(articles, fake_score)

        self.assertEqual(result["strategy"], "react-hybrid")
        self.assertIn("[Source 1: Two]", result["context_text"])
        self.assertEqual(result["registry"]["daily_article_ids"], ["a2"])

    def test_build_hybrid_context_falls_back_when_no_scores_pass_threshold(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]

        def fake_score(title_lines):
            return {1: 1, 2: 2}

        result = build_hybrid_context(articles, fake_score)

        self.assertEqual(result["registry"]["daily_article_ids"], ["a1", "a2"])

    def test_build_hybrid_context_fallback_respects_max_selected(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
            {"id": "a3", "text": "Three", "metadata": {"title": "Three"}},
            {"id": "a4", "text": "Four", "metadata": {"title": "Four"}},
            {"id": "a5", "text": "Five", "metadata": {"title": "Five"}},
        ]

        def fake_score(title_lines):
            return {}

        result = build_hybrid_context(articles, fake_score, max_selected=2)

        self.assertEqual(result["registry"]["daily_article_ids"], ["a1", "a2"])

    def test_build_hybrid_context_does_not_mutate_input_articles(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two"}},
        ]
        original_articles = copy.deepcopy(articles)

        def fake_score(title_lines):
            return {2: 4}

        build_hybrid_context(articles, fake_score)

        self.assertEqual(articles, original_articles)

    def test_build_hybrid_context_rejects_non_positive_max_selected(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One"}},
        ]

        def fake_score(title_lines):
            return {1: 4}

        with self.assertRaises(ValueError) as zero_error:
            build_hybrid_context(articles, fake_score, max_selected=0)
        self.assertEqual(str(zero_error.exception), "max_selected must be a positive integer")

        with self.assertRaises(ValueError) as negative_error:
            build_hybrid_context(articles, fake_score, max_selected=-1)
        self.assertEqual(str(negative_error.exception), "max_selected must be a positive integer")

    def test_build_map_reduce_context_batches_articles_and_preserves_sources(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One", "source": "PUBLICO"}},
            {"id": "a2", "text": "Two", "metadata": {"title": "Two", "source": "BBC"}},
        ]

        def fake_summarize(batch_text):
            return "Batch summary [Source 1]."

        result = build_map_reduce_context(articles, fake_summarize, batch_size=1)

        self.assertIn("Batch summary", result["context_text"])
        self.assertEqual(result["registry"]["daily_article_ids"], ["a1", "a2"])

    def test_build_map_reduce_context_handles_empty_articles(self):
        def fake_summarize(batch_text):
            return "Should not be called"

        result = build_map_reduce_context([], fake_summarize, batch_size=1)

        self.assertEqual(result["context_text"], "")
        self.assertEqual(result["registry"]["daily_article_ids"], [])
        self.assertEqual(result["retrieved_chunk_ids"], [])

    def test_build_map_reduce_context_skips_empty_summaries(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One", "source": "PUBLICO"}},
        ]

        def fake_summarize(batch_text):
            return "   "

        result = build_map_reduce_context(articles, fake_summarize, batch_size=1)

        self.assertEqual(result["context_text"], "")
        self.assertEqual(result["registry"]["daily_article_ids"], ["a1"])
        self.assertEqual(result["retrieved_chunk_ids"], [])

    def test_build_progressive_context_updates_running_draft(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One", "source": "PUBLICO"}},
        ]

        def fake_update(current_draft, batch_text):
            return current_draft + "\nUpdated [Source 1]."

        result = build_progressive_context(articles, fake_update, batch_size=1)

        self.assertIn("Updated [Source 1]", result["context_text"])

    def test_build_progressive_context_handles_empty_articles(self):
        def fake_update(current_draft, batch_text):
            return "Should not be called"

        result = build_progressive_context([], fake_update, batch_size=1)

        self.assertEqual(result["context_text"], "")
        self.assertEqual(result["registry"]["daily_article_ids"], [])
        self.assertEqual(result["retrieved_chunk_ids"], [])

    def test_build_progressive_context_allows_empty_updates(self):
        articles = [
            {"id": "a1", "text": "One", "metadata": {"title": "One", "source": "PUBLICO"}},
        ]

        def fake_update(current_draft, batch_text):
            return ""

        result = build_progressive_context(articles, fake_update, batch_size=1)

        self.assertEqual(result["context_text"], "")
        self.assertEqual(result["registry"]["daily_article_ids"], ["a1"])
        self.assertEqual(result["retrieved_chunk_ids"], [])
