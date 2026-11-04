"""
Tests for report generation orchestration helpers.
"""

import json
import tempfile
import unittest
from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reporting.create_report import build_report_manifest
from reporting.create_report import execute_read_article_tool
from reporting.create_report import extract_selected_article_ids_from_tool_log
from reporting.create_report import generate_triage_report
from reporting.create_report import prepare_candidate_pool
from reporting.create_report import run_report_from_context
from reporting.create_report import run_report_batch
from reporting.create_report import run_report_recipe
from reporting.create_report import save_report_artifacts
from reporting.context.source_registry import make_source_registry
from reporting.metrics import extract_report_metrics
from reporting.model_calls import build_openai_chat_messages
from reporting.model_calls import build_model_client
from reporting.model_calls import call_chat_model
from reporting.model_calls import confirm_paid_call
from reporting.model_calls import get_chat_request_model
from reporting.model_calls import make_model_usage_tracker
from reporting.model_calls import record_model_usage
from reporting.model_calls import require_model_credentials


def make_test_article():
    return {
        "id": "a1",
        "published_at": "2026-04-10T12:00:00+00:00",
        "text": "Tourism demand rose.",
        "metadata": {
            "title": "Tourism rises",
            "source": "PUBLICO",
            "date": "2026-04-10",
            "link": "https://example.com/a1",
        },
    }


def make_test_recipe(tmp, context_strategy):
    return {
        "name": "daily_tourism_intelligence",
        "input_corpus": str(Path(tmp) / "articles"),
        "output_folder": str(Path(tmp) / "reports"),
        "report_window_hours": 24,
        "system_prompt": "reporting/prompts/daily_tourism_system.md",
        "user_prompt": "reporting/prompts/daily_tourism_user.md",
        "context_strategy": context_strategy,
        "knowledge_base_recipe": "",
        "max_iterations": 3,
        "candidate_limit": 30,
        "model_provider": "openai",
        "model_name": "fake-model",
    }


def write_test_article(recipe):
    article_dir = Path(recipe["input_corpus"])
    article_dir.mkdir(parents=True)
    article = make_test_article()
    (article_dir / "a1.json").write_text(json.dumps(article), encoding="utf-8")


def make_fake_chat_client(model_results):
    calls = []
    remaining_results = list(model_results)

    def create(model, messages, tools=None):
        calls.append({
            "model": model,
            "messages": messages,
            "tools": tools,
        })
        model_result = remaining_results.pop(0)
        tool_calls = []

        for tool_call in model_result.get("tool_calls", []):
            arguments_text = json.dumps(tool_call.get("arguments", {}))
            tool_calls.append(SimpleNamespace(
                id=tool_call.get("id", ""),
                function=SimpleNamespace(
                    name=tool_call.get("name", ""),
                    arguments=arguments_text,
                ),
            ))

        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=model_result.get("content", ""),
                        tool_calls=tool_calls,
                    ),
                ),
            ],
            usage=SimpleNamespace(
                prompt_tokens=model_result.get("prompt_tokens", 0),
                completion_tokens=model_result.get("completion_tokens", 0),
            ),
        )
        return response

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=create,
            ),
        ),
    )
    client.calls = calls
    return client


class ReportingModelCallTests(unittest.TestCase):
    def test_build_openai_chat_messages_combines_prompts_and_context(self):
        messages = build_openai_chat_messages(
            system_prompt="System {date}",
            user_prompt="User {context_text} {date}",
            context_text="Context block",
            report_date="2026-04-10",
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("2026-04-10", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Context block", messages[1]["content"])

    def test_build_openai_chat_messages_fills_daily_tourism_prompt_variables(self):
        messages = build_openai_chat_messages(
            system_prompt="System {date}",
            user_prompt="Articles:\n{articles_text}\nToday: {today}",
            context_text="Selected article context",
            report_date="2026-04-10",
        )

        self.assertIn("Selected article context", messages[1]["content"])
        self.assertIn("Today: 2026-04-10", messages[1]["content"])
        self.assertNotIn("{articles_text}", messages[1]["content"])
        self.assertNotIn("{today}", messages[1]["content"])

    def test_confirm_paid_call_returns_true_when_yes_flag_is_set(self):
        self.assertEqual(confirm_paid_call("daily_tourism_intelligence", "simple", yes=True), True)

    def test_require_model_credentials_reads_openai_key(self):
        recipe = {"model_provider": "openai", "model_name": "gpt-4o-mini"}

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
            credentials = require_model_credentials(recipe)

        self.assertEqual(credentials["api_key"], "sk-test")

    def test_require_model_credentials_reads_azure_fields(self):
        recipe = {
            "model_provider": "azure_openai",
            "model_name": "gpt-5",
            "model_deployment": "azure-gpt5",
        }

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "azure-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_API_VERSION": "2024-02-01",
            },
            clear=True,
        ):
            credentials = require_model_credentials(recipe)

        self.assertEqual(credentials["api_key"], "azure-key")
        self.assertEqual(credentials["azure_endpoint"], "https://example.openai.azure.com")
        self.assertEqual(credentials["api_version"], "2024-02-01")
        self.assertEqual(credentials["model_deployment"], "azure-gpt5")

    def test_get_chat_request_model_uses_deployment_for_azure(self):
        recipe = {
            "model_provider": "azure_openai",
            "model_name": "gpt-5",
            "model_deployment": "azure-gpt5",
        }

        self.assertEqual(get_chat_request_model(recipe), "azure-gpt5")

    def test_build_model_client_uses_azure_client(self):
        recipe = {
            "model_provider": "azure_openai",
            "model_name": "gpt-5",
            "model_deployment": "azure-gpt5",
        }

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "azure-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_API_VERSION": "2024-02-01",
            },
            clear=True,
        ):
            with patch("openai.AzureOpenAI") as fake_azure_openai:
                build_model_client(recipe)

        fake_azure_openai.assert_called_once_with(
            api_key="azure-key",
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-02-01",
        )

    def test_record_model_usage_accumulates_tokens_and_calls(self):
        tracker = make_model_usage_tracker()

        record_model_usage(tracker, {"prompt_tokens": 10, "completion_tokens": 20})
        record_model_usage(tracker, {"prompt_tokens": 5, "completion_tokens": 7})

        self.assertEqual(tracker["prompt_tokens"], 15)
        self.assertEqual(tracker["completion_tokens"], 27)
        self.assertEqual(tracker["llm_calls"], 2)

    def test_call_chat_model_returns_tool_call_arguments(self):
        client = make_fake_chat_client([
            {
                "content": "",
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "search_knowledge_base",
                        "arguments": {"query": "airport demand Portugal"},
                    },
                ],
            },
        ])
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Search the selected knowledge base.",
                },
            },
        ]

        result = call_chat_model(
            client,
            "fake-model",
            [{"role": "user", "content": "Search before reporting."}],
            tools=tools,
        )

        self.assertEqual(result["content"], "")
        self.assertEqual(result["prompt_tokens"], 11)
        self.assertEqual(result["tool_calls"][0]["tool_call_id"], "call-1")
        self.assertEqual(result["tool_calls"][0]["tool_name"], "search_knowledge_base")
        self.assertEqual(result["tool_calls"][0]["arguments"], {"query": "airport demand Portugal"})
        self.assertEqual(client.calls[0]["tools"], tools)

    def test_extract_report_metrics_counts_citations_and_words(self):
        report_text = "# Report\n\nClaim one [Source 1]. Claim two [Source 2]."
        registry = {
            "daily_article_ids": ["a1", "a2"],
            "rag_source_article_ids": [],
            "source_articles": [
                {"source_number": 1, "article_id": "a1", "article": {}, "source_type": "daily"},
                {"source_number": 2, "article_id": "a2", "article": {}, "source_type": "daily"},
            ],
        }

        metrics = extract_report_metrics(report_text, registry, retrieved_chunk_ids=[])

        self.assertEqual(metrics["citation_count"], 2)
        self.assertEqual(metrics["distinct_cited_sources"], 2)
        self.assertEqual(metrics["citation_reference_validity_rate"], 1.0)
        self.assertEqual(metrics["cited_daily_article_count"], 2)

    def test_extract_report_metrics_treats_empty_citations_as_valid(self):
        empty_registry = {
            "daily_article_ids": [],
            "rag_source_article_ids": [],
            "source_articles": [],
        }

        metrics = extract_report_metrics("", empty_registry, retrieved_chunk_ids=[])

        self.assertEqual(metrics["citation_reference_validity_rate"], 1.0)
        self.assertEqual(metrics["retrieved_to_cited_rate"], 0.0)
        self.assertEqual(metrics["retrieved_chunk_count"], 0)

    def test_extract_report_metrics_zero_retrieved_chunks_have_zero_retrieved_to_cited_rate(self):
        report_text = "Claim one [Source 1]. Claim two [Source 2]."
        registry = {
            "daily_article_ids": ["a1", "a2"],
            "rag_source_article_ids": [],
            "source_articles": [
                {"source_number": 1, "article_id": "a1", "article": {}, "source_type": "daily"},
                {"source_number": 2, "article_id": "a2", "article": {}, "source_type": "daily"},
            ],
        }

        metrics = extract_report_metrics(report_text, registry, retrieved_chunk_ids=[])

        self.assertEqual(metrics["retrieved_to_cited_rate"], 0.0)

    def test_extract_report_metrics_adds_temporal_source_and_tool_diagnostics(self):
        report_text = (
            "# Report\n\n"
            "Daily signal [Source 1].\n"
            "Past context [Source 2, historical articles].\n"
            "Future leak [Source 3].\n"
            "Unknown date [Source 4]."
        )
        registry = {
            "daily_article_ids": ["daily-1"],
            "rag_source_article_ids": ["past-1", "future-1", "unknown-1"],
            "source_articles": [
                {
                    "source_number": 1,
                    "article_id": "daily-1",
                    "source_type": "daily",
                    "article": {
                        "published_at": "2026-05-13T09:00:00+00:00",
                        "metadata": {"title": "Daily", "source": "PUBLICO"},
                    },
                },
                {
                    "source_number": 2,
                    "article_id": "past-1",
                    "source_type": "knowledge_base",
                    "article": {
                        "published_at": "2026-05-10T09:00:00+00:00",
                        "metadata": {"title": "Past", "source": "SKIFT"},
                    },
                },
                {
                    "source_number": 3,
                    "article_id": "future-1",
                    "source_type": "knowledge_base",
                    "article": {
                        "published_at": "2026-05-14T09:00:00+00:00",
                        "metadata": {"title": "Future", "source": "SKIFT"},
                    },
                },
                {
                    "source_number": 4,
                    "article_id": "unknown-1",
                    "source_type": "knowledge_base",
                    "article": {
                        "metadata": {"title": "Unknown", "source": "BBC"},
                    },
                },
            ],
        }
        tool_call_log = [
            {"tool_name": "search_knowledge_base", "status": "ok"},
            {"tool_name": "search_knowledge_base", "status": "error"},
            {"tool_name": "read_article", "status": "ok"},
        ]

        metrics = extract_report_metrics(
            report_text,
            registry,
            retrieved_chunk_ids=["c1", "c2", "c3"],
            window_start="2026-05-13T00:00:00+00:00",
            window_end="2026-05-13T23:59:59+00:00",
            tool_call_log=tool_call_log,
            model_metrics={
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "llm_calls": 2,
                "runtime_seconds": 12.5,
            },
        )

        self.assertEqual(metrics["citation_count"], 4)
        self.assertEqual(metrics["citation_nonstandard_count"], 1)
        self.assertEqual(metrics["report_line_count"], 5)
        self.assertEqual(metrics["cited_line_count"], 4)
        self.assertAlmostEqual(metrics["cited_line_ratio"], 0.8)
        self.assertEqual(metrics["daily_article_count"], 1)
        self.assertEqual(metrics["rag_source_article_count"], 3)
        self.assertAlmostEqual(metrics["cited_source_hhi"], 0.375)
        self.assertAlmostEqual(metrics["top_cited_source_share"], 0.5)
        self.assertEqual(metrics["kb_search_call_count"], 2)
        self.assertEqual(metrics["successful_kb_search_call_count"], 1)
        self.assertEqual(metrics["read_article_call_count"], 1)
        self.assertEqual(metrics["llm_prompt_tokens"], 100)
        self.assertEqual(metrics["llm_completion_tokens"], 40)
        self.assertEqual(metrics["llm_call_count"], 2)
        self.assertEqual(metrics["runtime_seconds"], 12.5)
        self.assertEqual(metrics["cited_daily_window_article_count"], 1)
        self.assertEqual(metrics["cited_past_article_count"], 1)
        self.assertEqual(metrics["cited_future_article_count"], 1)
        self.assertEqual(metrics["cited_unknown_date_article_count"], 1)
        self.assertAlmostEqual(metrics["cited_temporal_validity_rate"], 2 / 3)
        self.assertEqual(metrics["source_future_article_count"], 1)
        self.assertEqual(metrics["rag_future_article_count"], 1)


class ReportingArtifactTests(unittest.TestCase):
    def test_save_report_artifacts_writes_markdown_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp)
            registry = {
                "daily_article_ids": ["a1"],
                "rag_source_article_ids": [],
                "source_articles": [
                    {"source_number": 1, "article_id": "a1", "article": {}, "source_type": "daily"},
                ],
            }
            manifest = build_report_manifest(
                recipe={"name": "daily_tourism_intelligence", "knowledge_base_recipe": ""},
                context_strategy="simple",
                report_datetime="2026-04-10T23:59:59+00:00",
                window_start="2026-04-09T23:59:59+00:00",
                window_end="2026-04-10T23:59:59+00:00",
                registry=registry,
                prompt_files=["system.md", "user.md"],
                retrieved_chunk_ids=[],
                metrics={"citation_count": 1},
                model_metrics={"prompt_tokens": 10, "completion_tokens": 20},
                tool_call_log=[
                    {
                        "strategy": "react-basic",
                        "phase": "final_report",
                        "iteration": 1,
                        "tool_call_id": "call-1",
                        "tool_name": "search_knowledge_base",
                        "arguments": {"query": "airport demand"},
                        "status": "ok",
                        "result_count": 1,
                        "retrieved_chunk_ids": ["chunk-1"],
                        "rag_source_article_ids": ["kb-1"],
                        "error": "",
                    },
                ],
            )

            self.assertEqual(manifest["report_sources"][0]["article_id"], "a1")
            self.assertEqual(manifest["report_sources"][0]["temporal_bucket"], "unknown")
            self.assertEqual(manifest["successful_kb_search_call_count"], 1)

            result = save_report_artifacts(
                output_folder,
                "daily_tourism_intelligence",
                "simple",
                "2026-04-10",
                "Report body",
                manifest,
            )

            self.assertTrue(result["report_path"].exists())
            self.assertTrue(result["manifest_path"].exists())
            loaded_manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(loaded_manifest["context_strategy"], "simple")
            self.assertEqual(
                loaded_manifest["tool_call_log"][0]["arguments"],
                {"query": "airport demand"},
            )

    def test_save_report_artifacts_keeps_two_reports_from_same_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp)
            manifest = {"context_strategy": "simple"}

            with patch("reporting.create_report.datetime") as patched_datetime:
                patched_datetime.now.side_effect = [
                    datetime(2026, 4, 10, 12, 30, 45, 111111, tzinfo=timezone.utc),
                    datetime(2026, 4, 10, 12, 30, 45, 222222, tzinfo=timezone.utc),
                ]

                first_result = save_report_artifacts(
                    output_folder,
                    "daily_tourism_intelligence",
                    "simple",
                    "2026-04-10",
                    "First report",
                    manifest,
                )
                second_result = save_report_artifacts(
                    output_folder,
                    "daily_tourism_intelligence",
                    "simple",
                    "2026-04-10",
                    "Second report",
                    manifest,
                )

            self.assertNotEqual(first_result["report_path"], second_result["report_path"])
            self.assertTrue(first_result["report_path"].exists())
            self.assertTrue(second_result["report_path"].exists())
            self.assertEqual(first_result["report_path"].read_text(encoding="utf-8"), "First report")
            self.assertEqual(second_result["report_path"].read_text(encoding="utf-8"), "Second report")


class ReportingRunTests(unittest.TestCase):
    def test_run_report_from_context_react_basic_still_raises_when_required_kb_search_is_missing(self):
        client = make_fake_chat_client([
            {
                "content": "Premature report [Source 1].",
                "prompt_tokens": 10,
                "completion_tokens": 5,
            },
            {
                "content": "Still no KB search [Source 1].",
                "prompt_tokens": 20,
                "completion_tokens": 6,
            },
        ])
        model_usage = make_model_usage_tracker()
        context_result = {
            "context_text": "Selected context [Source 1]",
            "registry": {
                "daily_article_ids": ["a1"],
                "rag_source_article_ids": [],
                "source_articles": [
                    {
                        "source_number": 1,
                        "article_id": "a1",
                        "article": make_test_article(),
                        "source_type": "daily",
                    },
                ],
            },
            "retrieved_chunk_ids": [],
        }
        search_queries = []

        def fake_search(query):
            search_queries.append(query)
            return []

        with self.assertRaises(ValueError) as error:
            run_report_from_context(
                "react-basic",
                "final_report",
                context_result,
                client,
                "fake-model",
                "System prompt",
                "User prompt",
                "2026-04-10",
                fake_search,
                model_usage,
                max_iterations=3,
            )

        redirected_message = "\n".join(
            message.get("content", "")
            for message in client.calls[1]["messages"]
        )

        self.assertIn("must call search_knowledge_base", redirected_message)
        self.assertEqual(
            str(error.exception),
            "search_knowledge_base is required before final report generation",
        )
        self.assertEqual(search_queries, [])

    def test_execute_read_article_tool_logs_canonical_article_id_for_extractor(self):
        article = make_test_article()
        registry = make_source_registry()
        tool_result = execute_read_article_tool(
            registry,
            [article],
            "react-triage",
            "triage",
            1,
            {
                "tool_call_id": "call-read-1",
                "tool_name": "read_article",
                "arguments": {"article_index": 1},
            },
        )

        log_entry = tool_result["log_entry"]

        self.assertEqual(log_entry["article_id"], "a1")
        self.assertEqual(
            extract_selected_article_ids_from_tool_log([log_entry]),
            ["a1"],
        )

    def test_extract_selected_article_ids_from_read_article_tool_log(self):
        tool_call_log = [
            {
                "tool_name": "read_article",
                "status": "ok",
                "arguments": {"article_index": 2},
                "article_id": "a2",
            },
            {
                "tool_name": "read_article",
                "status": "ok",
                "arguments": {"article_index": 1},
                "article_id": "a1",
            },
            {
                "tool_name": "read_article",
                "status": "ok",
                "arguments": {"article_index": 2},
                "article_id": "a2",
            },
            {
                "tool_name": "read_article",
                "status": "error",
                "arguments": {"article_index": 3},
                "article_id": "a3",
            },
            {
                "tool_name": "search_knowledge_base",
                "status": "ok",
                "arguments": {"query": "hotel demand lisbon"},
                "rag_source_article_ids": ["kb-1"],
            },
        ]

        selected_ids = extract_selected_article_ids_from_tool_log(tool_call_log)

        self.assertEqual(selected_ids, ["a2", "a1"])

    def test_generate_triage_report_builds_context_from_read_articles_before_final_report(self):
        articles = [
            {
                "id": "a1",
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {
                    "title": "Airport strike",
                    "source": "PUBLICO",
                    "date": "2026-05-16",
                },
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {
                    "title": "Hotel demand rises",
                    "source": "ECO",
                    "date": "2026-05-16",
                },
            },
        ]
        client = make_fake_chat_client([
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tool-1",
                        "name": "read_article",
                        "arguments": {"article_index": 2},
                    },
                ],
            },
            {
                "content": "Triage selection complete.",
                "tool_calls": [],
            },
        ])
        model_usage = make_model_usage_tracker()
        observed = {}

        def fake_build_context(passed_articles, selected_article_ids, max_chars_per_article=2000):
            observed["build_context_articles"] = passed_articles
            observed["selected_article_ids"] = selected_article_ids
            observed["max_chars_per_article"] = max_chars_per_article
            return {
                "strategy": "react-triage",
                "context_text": "Selected context [Source 1]",
                "registry": {
                    "daily_article_ids": ["a2"],
                    "source_articles": [
                        {
                            "article_id": "a2",
                            "source_number": 1,
                            "article": articles[1],
                        },
                    ],
                    "rag_source_article_ids": [],
                },
                "retrieved_chunk_ids": [],
                "article_count": 1,
                "source_count": 1,
            }

        def fake_run_report_from_context(
            strategy,
            phase,
            context_result,
            report_client,
            model_name,
            system_prompt,
            user_prompt,
            report_date,
            search_function,
            report_model_usage,
            max_iterations,
        ):
            observed["run_report_args"] = {
                "strategy": strategy,
                "phase": phase,
                "context_result": context_result,
                "client": report_client,
                "model_name": model_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "report_date": report_date,
                "search_function": search_function,
                "model_usage": report_model_usage,
                "max_iterations": max_iterations,
            }
            return {
                "report_text": "Final report text [Source 1]",
                "registry": context_result["registry"],
                "retrieved_chunk_ids": ["chunk-1"],
                "tool_call_log": [
                    {
                        "tool_name": "search_knowledge_base",
                        "status": "ok",
                        "arguments": {"query": "Hotel demand rises in Lisbon"},
                        "retrieved_chunk_ids": ["chunk-1"],
                    },
                ],
            }

        with patch(
            "reporting.create_report.build_context_from_selected_articles",
            side_effect=fake_build_context,
        ) as fake_context_builder, patch(
            "reporting.create_report.run_report_from_context",
            side_effect=fake_run_report_from_context,
        ) as fake_final_stage:
            result = generate_triage_report(
                articles,
                client,
                "fake-model",
                "System prompt",
                "User prompt",
                "2026-05-16",
                lambda query: [],
                model_usage,
                max_iterations=3,
            )

        fake_context_builder.assert_called_once()
        fake_final_stage.assert_called_once()
        self.assertEqual(observed["build_context_articles"], articles)
        self.assertEqual(observed["selected_article_ids"], ["a2"])
        self.assertEqual(observed["run_report_args"]["strategy"], "react-triage")
        self.assertEqual(observed["run_report_args"]["phase"], "final_report")
        self.assertEqual(
            observed["run_report_args"]["context_result"]["registry"]["daily_article_ids"],
            ["a2"],
        )
        self.assertEqual(result["report_text"], "Final report text [Source 1]")
        self.assertEqual(result["retrieved_chunk_ids"], ["chunk-1"])
        self.assertEqual(
            [entry["tool_name"] for entry in result["tool_call_log"]],
            ["read_article", "search_knowledge_base"],
        )

    def test_generate_triage_report_fails_if_triage_never_reads_an_article(self):
        articles = [
            {
                "id": "a1",
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {
                    "title": "Airport strike",
                    "source": "PUBLICO",
                    "date": "2026-05-16",
                },
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {
                    "title": "Hotel demand rises",
                    "source": "ECO",
                    "date": "2026-05-16",
                },
            },
        ]
        client = make_fake_chat_client([
            {
                "content": "I can decide from the titles alone.",
                "tool_calls": [],
            },
            {
                "content": "Still no read_article call.",
                "tool_calls": [],
            },
        ])
        model_usage = make_model_usage_tracker()

        with patch(
            "reporting.create_report.build_context_from_selected_articles",
            side_effect=AssertionError("context rebuild should not run"),
        ), patch(
            "reporting.create_report.run_report_from_context",
            side_effect=AssertionError("final report stage should not run"),
        ):
            with self.assertRaises(ValueError) as error:
                generate_triage_report(
                    articles,
                    client,
                    "fake-model",
                    "System prompt",
                    "User prompt",
                    "2026-05-16",
                    lambda query: [],
                    model_usage,
                    max_iterations=3,
                )

        redirected_message = "\n".join(
            message.get("content", "")
            for message in client.calls[1]["messages"]
        )

        self.assertIn("must call read_article", redirected_message)
        self.assertEqual(
            str(error.exception),
            "react-triage must read at least one article before building final context",
        )

    def test_generate_triage_report_runs_one_fallback_kb_search_when_final_phase_skips_search(self):
        articles = [
            {
                "id": "a1",
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {
                    "title": "Airport strike",
                    "source": "PUBLICO",
                    "date": "2026-05-16",
                },
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {
                    "title": "Hotel demand rises in Lisbon",
                    "source": "ECO",
                    "date": "2026-05-16",
                },
            },
        ]
        client = make_fake_chat_client([
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tool-1",
                        "name": "read_article",
                        "arguments": {"article_index": 2},
                    },
                ],
            },
            {
                "content": "Triage selection complete.",
                "tool_calls": [],
            },
            {
                "content": "Draft report without KB search [Source 1].",
                "tool_calls": [],
            },
            {
                "content": "Still skipping KB search [Source 1].",
                "tool_calls": [],
            },
            {
                "content": "Final report with fallback KB context [Sources 1-2].",
                "tool_calls": [],
            },
        ])
        model_usage = make_model_usage_tracker()
        search_queries = []

        def fake_search(query):
            search_queries.append(query)
            return [
                {
                    "chunk_id": "chunk-fallback-1",
                    "article_id": "kb-1",
                    "title": "Lisbon hotel demand history",
                    "source": "SKIFT",
                    "published_at": "2026-05-01",
                    "url": "https://example.com/kb-1",
                    "chunk_text": "Older Lisbon hotel demand context.",
                }
            ]

        result = generate_triage_report(
            articles,
            client,
            "fake-model",
            "System prompt",
            "User prompt",
            "2026-05-16",
            fake_search,
            model_usage,
            max_iterations=3,
        )

        self.assertEqual(search_queries, ["Hotel demand rises in Lisbon"])
        self.assertEqual(result["report_text"], "Final report with fallback KB context [Sources 1-2].")
        self.assertEqual(result["retrieved_chunk_ids"], ["chunk-fallback-1"])
        self.assertEqual(
            [entry["tool_name"] for entry in result["tool_call_log"]],
            ["read_article", "search_knowledge_base"],
        )
        self.assertEqual(result["tool_call_log"][1]["arguments"], {"query": "Hotel demand rises in Lisbon"})
        self.assertEqual(result["tool_call_log"][1]["status"], "ok")
        self.assertEqual(result["tool_call_log"][1]["retrieved_chunk_ids"], ["chunk-fallback-1"])
        self.assertEqual(result["tool_call_log"][1]["rag_source_article_ids"], ["kb-1"])
        self.assertEqual(model_usage["llm_calls"], 5)

    def test_generate_triage_report_fallback_uses_first_chosen_article_title_when_reads_are_reversed(self):
        articles = [
            {
                "id": "a1",
                "published_at": "2026-05-16T08:00:00+00:00",
                "text": "Airport strike affects flights.",
                "metadata": {
                    "title": "Airport strike",
                    "source": "PUBLICO",
                    "date": "2026-05-16",
                },
            },
            {
                "id": "a2",
                "published_at": "2026-05-16T09:00:00+00:00",
                "text": "Hotel demand rises in Lisbon.",
                "metadata": {
                    "title": "Hotel demand rises in Lisbon",
                    "source": "ECO",
                    "date": "2026-05-16",
                },
            },
        ]
        client = make_fake_chat_client([
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tool-1",
                        "name": "read_article",
                        "arguments": {"article_index": 2},
                    },
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tool-2",
                        "name": "read_article",
                        "arguments": {"article_index": 1},
                    },
                ],
            },
            {
                "content": "Triage selection complete.",
                "tool_calls": [],
            },
            {
                "content": "Draft report without KB search [Source 1].",
                "tool_calls": [],
            },
            {
                "content": "Still skipping KB search [Source 1].",
                "tool_calls": [],
            },
            {
                "content": "Final report with fallback KB context [Sources 1-3].",
                "tool_calls": [],
            },
        ])
        model_usage = make_model_usage_tracker()
        search_queries = []

        def fake_search(query):
            search_queries.append(query)
            return [
                {
                    "chunk_id": "chunk-fallback-2",
                    "article_id": "kb-2",
                    "title": "Lisbon hotel demand history",
                    "source": "SKIFT",
                    "published_at": "2026-05-01",
                    "url": "https://example.com/kb-2",
                    "chunk_text": "Older Lisbon hotel demand context.",
                }
            ]

        result = generate_triage_report(
            articles,
            client,
            "fake-model",
            "System prompt",
            "User prompt",
            "2026-05-16",
            fake_search,
            model_usage,
            max_iterations=4,
        )

        self.assertEqual(search_queries, ["Hotel demand rises in Lisbon"])
        self.assertEqual(result["tool_call_log"][0]["article_id"], "a2")
        self.assertEqual(result["tool_call_log"][1]["article_id"], "a1")
        self.assertEqual(result["tool_call_log"][2]["arguments"], {"query": "Hotel demand rises in Lisbon"})

    def test_run_report_batch_creates_one_folder_and_continues_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp) / "reports"
            recipe = make_test_recipe(tmp, "simple")
            recipe["output_folder"] = str(output_folder)
            write_test_article(recipe)
            run_calls = []

            def fake_run_report_recipe(
                recipe_name,
                context_strategy=None,
                article_date=None,
                report_datetime=None,
                hours=None,
                knowledge_base_recipe=None,
                max_iterations=None,
                candidate_limit=None,
                yes=False,
                output_folder_override=None,
                artifact_stem=None,
                precomputed_daily_articles=None,
                precomputed_selected_articles=None,
                precomputed_candidate_selection=None,
            ):
                run_calls.append(context_strategy)
                if context_strategy == "react-basic":
                    raise ValueError("KB unavailable")

                report_path = Path(output_folder_override) / f"{artifact_stem}.md"
                manifest_path = Path(output_folder_override) / f"{artifact_stem}_manifest.json"
                report_path.write_text(f"{context_strategy} report", encoding="utf-8")
                manifest_path.write_text("{}", encoding="utf-8")
                return {
                    "report_path": report_path,
                    "manifest_path": manifest_path,
                }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.load_clean_articles", return_value=[make_test_article()]), \
                 patch("reporting.create_report.select_articles_for_report_day", return_value=[make_test_article()]), \
                 patch("reporting.create_report.prepare_candidate_pool", return_value={
                     "selected_articles": [make_test_article()],
                     "candidate_selection": {
                         "method": "none",
                         "raw_count": 1,
                         "kept_count": 1,
                         "excluded_count": 0,
                     },
                 }), \
                 patch("reporting.create_report.run_report_recipe", side_effect=fake_run_report_recipe), \
                 patch("reporting.create_report.write_report_batch_viewer", return_value=output_folder / "may13_context_check" / "index.html") as fake_viewer:
                result = run_report_batch(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    run_name="may13_context_check",
                    yes=True,
                )

            run_folder = output_folder / "may13_context_check"
            run_manifest = json.loads((run_folder / "run_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(result["run_folder"], run_folder)
            self.assertTrue((run_folder / "simple.md").exists())
            self.assertTrue((run_folder / "react-map-reduce.md").exists())
            self.assertFalse((run_folder / "react-basic.md").exists())
            self.assertEqual(run_calls, [
                "simple",
                "react-basic",
                "react-map-reduce",
                "react-triage",
                "react-hybrid",
                "react-progressive",
            ])
            self.assertEqual(run_manifest["run_name"], "may13_context_check")
            self.assertEqual(run_manifest["status"], "completed_with_errors")
            self.assertEqual(run_manifest["candidate_selection"]["kept_count"], 1)
            self.assertEqual(run_manifest["strategies"][0]["status"], "ok")
            self.assertEqual(run_manifest["strategies"][1]["status"], "error")
            self.assertEqual(run_manifest["strategies"][1]["error"], "KB unavailable")
            self.assertEqual(result["viewer_path"], run_folder / "index.html")
            fake_viewer.assert_called_once_with(run_folder)

    def test_run_report_batch_rejects_existing_run_folder_with_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp) / "reports"
            existing_folder = output_folder / "may13_context_check"
            existing_folder.mkdir(parents=True)
            (existing_folder / "simple.md").write_text("existing", encoding="utf-8")
            recipe = make_test_recipe(tmp, "simple")
            recipe["output_folder"] = str(output_folder)

            with patch("reporting.create_report.load_report_recipe", return_value=recipe):
                with self.assertRaises(ValueError) as error:
                    run_report_batch(
                        "daily_tourism_intelligence",
                        article_date="2026-04-10",
                        run_name="may13_context_check",
                        yes=True,
                    )

            self.assertIn("Run folder already exists", str(error.exception))

    def test_run_report_batch_waits_between_strategies_including_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp) / "reports"
            recipe = make_test_recipe(tmp, "simple")
            recipe["output_folder"] = str(output_folder)
            write_test_article(recipe)
            run_calls = []

            def fake_run_report_recipe(
                recipe_name,
                context_strategy=None,
                article_date=None,
                report_datetime=None,
                hours=None,
                knowledge_base_recipe=None,
                max_iterations=None,
                candidate_limit=None,
                yes=False,
                output_folder_override=None,
                artifact_stem=None,
                precomputed_daily_articles=None,
                precomputed_selected_articles=None,
                precomputed_candidate_selection=None,
            ):
                run_calls.append(context_strategy)
                if context_strategy == "react-basic":
                    raise ValueError("KB unavailable")

                report_path = Path(output_folder_override) / f"{artifact_stem}.md"
                manifest_path = Path(output_folder_override) / f"{artifact_stem}_manifest.json"
                report_path.write_text(f"{context_strategy} report", encoding="utf-8")
                manifest_path.write_text("{}", encoding="utf-8")
                return {
                    "report_path": report_path,
                    "manifest_path": manifest_path,
                }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.load_clean_articles", return_value=[make_test_article()]), \
                 patch("reporting.create_report.select_articles_for_report_day", return_value=[make_test_article()]), \
                 patch("reporting.create_report.prepare_candidate_pool", return_value={
                     "selected_articles": [make_test_article()],
                     "candidate_selection": {
                         "method": "none",
                         "raw_count": 1,
                         "kept_count": 1,
                         "excluded_count": 0,
                     },
                 }), \
                 patch("reporting.create_report.run_report_recipe", side_effect=fake_run_report_recipe), \
                 patch("reporting.create_report.write_report_batch_viewer", return_value=output_folder / "may13_context_check" / "index.html"), \
                 patch("reporting.create_report.time.sleep") as fake_sleep:
                run_report_batch(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    run_name="may13_context_check",
                    strategy_delay_seconds=60,
                    yes=True,
                )

            self.assertEqual(run_calls, [
                "simple",
                "react-basic",
                "react-map-reduce",
                "react-triage",
                "react-hybrid",
                "react-progressive",
            ])
            self.assertEqual(fake_sleep.call_count, 5)
            fake_sleep.assert_any_call(60)

    def test_run_report_batch_does_not_wait_after_last_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp) / "reports"
            recipe = make_test_recipe(tmp, "simple")
            recipe["output_folder"] = str(output_folder)
            write_test_article(recipe)

            def fake_run_report_recipe(
                recipe_name,
                context_strategy=None,
                article_date=None,
                report_datetime=None,
                hours=None,
                knowledge_base_recipe=None,
                max_iterations=None,
                candidate_limit=None,
                yes=False,
                output_folder_override=None,
                artifact_stem=None,
                precomputed_daily_articles=None,
                precomputed_selected_articles=None,
                precomputed_candidate_selection=None,
            ):
                report_path = Path(output_folder_override) / f"{artifact_stem}.md"
                manifest_path = Path(output_folder_override) / f"{artifact_stem}_manifest.json"
                report_path.write_text(f"{context_strategy} report", encoding="utf-8")
                manifest_path.write_text("{}", encoding="utf-8")
                return {
                    "report_path": report_path,
                    "manifest_path": manifest_path,
                }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.load_clean_articles", return_value=[make_test_article()]), \
                 patch("reporting.create_report.select_articles_for_report_day", return_value=[make_test_article()]), \
                 patch("reporting.create_report.prepare_candidate_pool", return_value={
                     "selected_articles": [make_test_article()],
                     "candidate_selection": {
                         "method": "none",
                         "raw_count": 1,
                         "kept_count": 1,
                         "excluded_count": 0,
                     },
                 }), \
                 patch("reporting.create_report.run_report_recipe", side_effect=fake_run_report_recipe), \
                 patch("reporting.create_report.write_report_batch_viewer", return_value=output_folder / "may13_context_check" / "index.html"), \
                 patch("reporting.create_report.time.sleep") as fake_sleep:
                run_report_batch(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    run_name="may13_context_check",
                    strategy_delay_seconds=60,
                    yes=True,
                )

            self.assertEqual(fake_sleep.call_count, 5)

    def test_run_report_batch_prepares_candidate_pool_once_and_shares_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp) / "reports"
            recipe = make_test_recipe(tmp, "simple")
            recipe["output_folder"] = str(output_folder)

            raw_articles = [make_test_article(), dict(make_test_article(), id="a2")]
            daily_articles = [raw_articles[0]]
            selected_articles = [raw_articles[0]]
            candidate_selection = {
                "method": "embedding_prototypes_v2",
                "raw_count": 1,
                "kept_count": 1,
                "excluded_count": 0,
            }
            shared_pool_calls = []

            def fake_run_report_recipe(
                recipe_name,
                context_strategy=None,
                article_date=None,
                report_datetime=None,
                hours=None,
                knowledge_base_recipe=None,
                max_iterations=None,
                candidate_limit=None,
                yes=False,
                output_folder_override=None,
                artifact_stem=None,
                precomputed_daily_articles=None,
                precomputed_selected_articles=None,
                precomputed_candidate_selection=None,
            ):
                shared_pool_calls.append({
                    "strategy": context_strategy,
                    "daily_articles": precomputed_daily_articles,
                    "selected_articles": precomputed_selected_articles,
                    "candidate_selection": precomputed_candidate_selection,
                })
                report_path = Path(output_folder_override) / f"{artifact_stem}.md"
                manifest_path = Path(output_folder_override) / f"{artifact_stem}_manifest.json"
                report_path.write_text(f"{context_strategy} report", encoding="utf-8")
                manifest_path.write_text("{}", encoding="utf-8")
                return {
                    "report_path": report_path,
                    "manifest_path": manifest_path,
                }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.load_clean_articles", return_value=raw_articles) as fake_load_articles, \
                 patch("reporting.create_report.select_articles_for_report_day", return_value=daily_articles) as fake_select_day, \
                 patch("reporting.create_report.prepare_candidate_pool", return_value={
                     "selected_articles": selected_articles,
                     "candidate_selection": candidate_selection,
                     "candidate_limit": 30,
                 }) as fake_prepare_pool, \
                 patch("reporting.create_report.run_report_recipe", side_effect=fake_run_report_recipe), \
                 patch("reporting.create_report.write_report_batch_viewer", return_value=output_folder / "shared_pool" / "index.html"):
                run_report_batch(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    run_name="shared_pool",
                    yes=True,
                )

            fake_load_articles.assert_called_once_with(recipe["input_corpus"])
            fake_select_day.assert_called_once()
            fake_prepare_pool.assert_called_once_with(recipe, daily_articles, candidate_limit=None)
            self.assertEqual(len(shared_pool_calls), len([
                "simple",
                "react-basic",
                "react-map-reduce",
                "react-triage",
                "react-hybrid",
                "react-progressive",
            ]))
            for call in shared_pool_calls:
                self.assertIs(call["daily_articles"], daily_articles)
                self.assertIs(call["selected_articles"], selected_articles)
                self.assertIs(call["candidate_selection"], candidate_selection)

    def test_run_report_recipe_single_run_still_prepares_candidate_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "simple")
            write_test_article(recipe)
            candidate_pool = {
                "selected_articles": [make_test_article()],
                "candidate_selection": {
                    "method": "none",
                    "raw_count": 1,
                    "kept_count": 1,
                    "excluded_count": 0,
                    "candidate_limit": 30,
                    "excluded_examples": [],
                },
                "candidate_limit": 30,
            }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.prepare_candidate_pool", return_value=candidate_pool) as fake_prepare_pool, \
                 patch("reporting.create_report.call_chat_model", return_value={
                     "content": "Report claim [Source 1].",
                     "prompt_tokens": 10,
                     "completion_tokens": 20,
                 }):
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            self.assertTrue(result["report_path"].exists())
            fake_prepare_pool.assert_called_once()

    def test_run_report_batch_rejects_negative_strategy_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_folder = Path(tmp) / "reports"
            recipe = make_test_recipe(tmp, "simple")
            recipe["output_folder"] = str(output_folder)

            with patch("reporting.create_report.load_report_recipe", return_value=recipe):
                with self.assertRaises(ValueError) as error:
                    run_report_batch(
                        "daily_tourism_intelligence",
                        article_date="2026-04-10",
                        strategy_delay_seconds=-1,
                        yes=True,
                    )

            self.assertEqual(
                str(error.exception),
                "Strategy delay seconds must be zero or greater",
            )

    def test_run_report_recipe_accepts_string_numbers_and_uses_default_model(self):
        article = {
            "id": "a1",
            "published_at": "2026-04-10T12:00:00+00:00",
            "text": "Tourism demand rose.",
            "metadata": {
                "title": "Tourism rises",
                "source": "PUBLICO",
                "date": "2026-04-10",
                "link": "https://example.com/a1",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            recipe = {
                "name": "daily_tourism_intelligence",
                "input_corpus": str(Path(tmp) / "articles"),
                "output_folder": str(Path(tmp) / "reports"),
                "report_window_hours": "24",
                "system_prompt": "reporting/prompts/daily_tourism_system.md",
                "user_prompt": "reporting/prompts/daily_tourism_user.md",
                "context_strategy": "simple",
                "knowledge_base_recipe": "",
                "max_iterations": 3,
                "candidate_limit": "30",
            }
            article_dir = Path(recipe["input_corpus"])
            article_dir.mkdir(parents=True)
            (article_dir / "a1.json").write_text(json.dumps(article), encoding="utf-8")

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.call_chat_model", return_value={
                     "content": "Report claim [Source 1].",
                     "prompt_tokens": 10,
                     "completion_tokens": 20,
                 }) as fake_call:
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    hours="24",
                    candidate_limit="30",
                    yes=True,
                )

            self.assertTrue(result["report_path"].exists())
            self.assertEqual(fake_call.call_args[0][1], "gpt-4o-mini")

    def test_run_report_recipe_rejects_invalid_numeric_options(self):
        recipe = {
            "name": "daily_tourism_intelligence",
            "input_corpus": "unused",
            "output_folder": "unused",
            "report_window_hours": 24,
            "system_prompt": "reporting/prompts/daily_tourism_system.md",
            "user_prompt": "reporting/prompts/daily_tourism_user.md",
            "context_strategy": "simple",
            "knowledge_base_recipe": "",
            "max_iterations": 3,
            "candidate_limit": 30,
            "model_name": "fake-model",
        }

        with patch("reporting.create_report.load_report_recipe", return_value=recipe):
            with self.assertRaises(ValueError) as hours_error:
                run_report_recipe("daily_tourism_intelligence", article_date="2026-04-10", hours="bad")

        self.assertEqual(str(hours_error.exception), "Report window hours must be a positive integer")

        with patch("reporting.create_report.load_report_recipe", return_value=recipe):
            with self.assertRaises(ValueError) as limit_error:
                run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    candidate_limit="0",
                )

        self.assertEqual(str(limit_error.exception), "Candidate limit must be a positive integer")

    def test_run_report_recipe_simple_uses_fake_model_and_saves_artifacts(self):
        article = {
            "id": "a1",
            "published_at": "2026-04-10T12:00:00+00:00",
            "text": "Tourism demand rose.",
            "metadata": {
                "title": "Tourism rises",
                "source": "PUBLICO",
                "date": "2026-04-10",
                "link": "https://example.com/a1",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            recipe = {
                "name": "daily_tourism_intelligence",
                "input_corpus": str(Path(tmp) / "articles"),
                "output_folder": str(Path(tmp) / "reports"),
                "report_window_hours": 24,
                "system_prompt": "reporting/prompts/daily_tourism_system.md",
                "user_prompt": "reporting/prompts/daily_tourism_user.md",
                "context_strategy": "simple",
                "knowledge_base_recipe": "",
                "max_iterations": 3,
                "candidate_limit": 30,
                "model_name": "fake-model",
            }
            article_dir = Path(recipe["input_corpus"])
            article_dir.mkdir(parents=True)
            (article_dir / "a1.json").write_text(json.dumps(article), encoding="utf-8")

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.call_chat_model", return_value={
                     "content": "Report claim [Source 1].",
                     "prompt_tokens": 10,
                     "completion_tokens": 20,
                 }):
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            self.assertTrue(result["report_path"].exists())
            self.assertTrue(result["manifest_path"].exists())
            self.assertIn("Sources Cited in Report", result["report_path"].read_text(encoding="utf-8"))

    def test_run_report_recipe_simple_does_not_record_unused_kb_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "simple")
            write_test_article(recipe)

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.call_chat_model", return_value={
                     "content": "Report claim [Source 1].",
                     "prompt_tokens": 10,
                     "completion_tokens": 20,
                 }):
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    knowledge_base_recipe="unused-kb",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["knowledge_base_recipe"], "")
            self.assertEqual(manifest["retrieved_chunk_ids"], [])
            self.assertEqual(manifest["available_tools"], [])
            self.assertEqual(manifest["required_tool_policy"], {})

    def test_run_report_recipe_uses_configured_candidate_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "simple")
            recipe["candidate_selector"] = "embedding_prototypes"
            write_test_article(recipe)

            selector_result = {
                "articles": [make_test_article()],
                "selection": {
                    "method": "embedding_prototypes_v2",
                    "raw_count": 1,
                    "kept_count": 1,
                    "excluded_count": 0,
                },
            }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.build_embedding_client", return_value=object()), \
                 patch("reporting.create_report.select_report_candidates", return_value=selector_result) as fake_selector, \
                 patch("reporting.create_report.call_chat_model", return_value={
                     "content": "Report claim [Source 1].",
                     "prompt_tokens": 10,
                     "completion_tokens": 20,
                 }):
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(fake_selector.call_count, 1)
            self.assertEqual(manifest["candidate_selection"]["method"], "embedding_prototypes_v2")
            self.assertEqual(manifest["candidate_selection"]["kept_count"], 1)

    def test_prepare_candidate_pool_runs_selector_once_and_returns_selected_articles(self):
        recipe = {
            "candidate_selector": "embedding_prototypes",
            "candidate_selector_model": "text-embedding-3-large",
            "candidate_selector_provider": "openai",
            "candidate_selector_positive_threshold": 0.28,
            "candidate_selector_margin_threshold": 0.03,
        }
        daily_articles = [
            {"id": "a1", "metadata": {"title": "One"}, "text": "One"},
            {"id": "a2", "metadata": {"title": "Two"}, "text": "Two"},
        ]
        selector_result = {
            "articles": [daily_articles[1]],
            "selection": {
                "method": "embedding_prototypes_v2",
                "raw_count": 2,
                "kept_count": 1,
                "excluded_count": 1,
            },
        }

        with patch("reporting.create_report.build_embedding_client", return_value=object()) as fake_client, \
             patch("reporting.create_report.select_report_candidates", return_value=selector_result) as fake_selector:
            result = prepare_candidate_pool(
                recipe,
                daily_articles,
                candidate_limit=10,
            )

        self.assertEqual(result["selected_articles"], [daily_articles[1]])
        self.assertEqual(result["candidate_selection"]["kept_count"], 1)
        fake_client.assert_called_once()
        fake_selector.assert_called_once()

    def test_run_report_recipe_uses_azure_selector_provider_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "simple")
            recipe["candidate_selector"] = "embedding_prototypes"
            recipe["model_provider"] = "azure_openai"
            recipe["model_name"] = "gpt-5"
            recipe["model_deployment"] = "azure-gpt5"
            recipe["candidate_selector_provider"] = "azure_openai"
            recipe["candidate_selector_model"] = "text-embedding-3-small"
            recipe["candidate_selector_deployment"] = "azure-embed-small"
            write_test_article(recipe)

            selector_result = {
                "articles": [make_test_article()],
                "selection": {
                    "method": "embedding_prototypes_v2",
                    "raw_count": 1,
                    "kept_count": 1,
                    "excluded_count": 0,
                },
            }

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()) as fake_model_client, \
                 patch("reporting.create_report.build_embedding_client", return_value=object()) as fake_embedding_client, \
                 patch("reporting.create_report.select_report_candidates", return_value=selector_result) as fake_selector, \
                 patch("reporting.create_report.call_chat_model", return_value={
                     "content": "Report claim [Source 1].",
                     "prompt_tokens": 10,
                     "completion_tokens": 20,
                 }):
                run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            fake_model_client.assert_called_once_with(recipe)
            selector_recipe = fake_embedding_client.call_args.args[0]
            self.assertEqual(selector_recipe["embedding_provider"], "azure_openai")
            self.assertEqual(selector_recipe["embedding_model"], "text-embedding-3-small")
            self.assertEqual(selector_recipe["embedding_deployment"], "azure-embed-small")
            self.assertEqual(fake_selector.call_count, 1)

    def test_run_report_recipe_react_basic_uses_recipe_kb_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-basic")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)
            model_results = [
                {
                    "content": "",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "tool_calls": [
                        {
                            "tool_call_id": "call-search-1",
                            "tool_name": "search_knowledge_base",
                            "arguments": {"query": "Portugal tourism context"},
                        },
                    ],
                },
                {
                    "content": "Report claim [Source 1].",
                    "prompt_tokens": 20,
                    "completion_tokens": 30,
                },
            ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.build_kb_search_function", return_value=lambda query: []) as fake_search_builder, \
                 patch("reporting.create_report.call_chat_model", side_effect=model_results):
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
            self.assertEqual(fake_search_builder.call_args.kwargs["indexed_before"], "2026-04-10T23:59:59+00:00")

    def test_run_report_recipe_missing_kb_stops_before_model_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-basic")
            write_test_article(recipe)

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client") as fake_client:
                with self.assertRaises(ValueError) as error:
                    run_report_recipe(
                        "daily_tourism_intelligence",
                        article_date="2026-04-10",
                        yes=True,
                    )

            self.assertEqual(str(error.exception), "react-basic needs --knowledge-base-recipe")
            fake_client.assert_not_called()

    def test_run_report_recipe_react_basic_records_tool_calls_and_honors_max_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-basic")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)
            client = make_fake_chat_client([
                {
                    "content": "",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "search_knowledge_base",
                            "arguments": {"query": "airport demand Portugal"},
                        },
                    ],
                },
                {
                    "content": "Final report [Source 2].",
                    "prompt_tokens": 30,
                    "completion_tokens": 40,
                },
            ])
            search_queries = []

            def fake_search(query):
                search_queries.append(query)
                return [
                    {
                        "chunk_id": "chunk-1",
                        "article_id": "kb-1",
                        "title": "Airport history",
                        "source": "SKIFT",
                        "published_at": "2026-04-01",
                        "url": "https://example.com/kb",
                        "chunk_text": "Earlier airport demand context.",
                    }
                ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=client), \
                 patch("reporting.create_report.build_kb_search_function", return_value=fake_search) as fake_search_builder:
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    max_iterations=2,
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(search_queries, ["airport demand Portugal"])
            self.assertEqual(fake_search_builder.call_args.kwargs["indexed_before"], "2026-04-10T23:59:59+00:00")
            self.assertEqual(manifest["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
            self.assertEqual(manifest["retrieved_chunk_ids"], ["chunk-1"])
            self.assertEqual(manifest["tool_call_log"][0]["tool_name"], "search_knowledge_base")
            self.assertEqual(manifest["tool_call_log"][0]["arguments"], {"query": "airport demand Portugal"})
            self.assertEqual(manifest["tool_call_log"][0]["retrieved_chunk_ids"], ["chunk-1"])
            self.assertEqual(manifest["model_metrics"]["llm_calls"], 2)
            self.assertEqual(manifest["available_tools"], ["search_knowledge_base"])
            self.assertEqual(manifest["required_tool_policy"]["minimum_search_knowledge_base_calls"], 1)
            self.assertEqual(manifest["tool_call_counts"]["search_knowledge_base"], 1)
            self.assertEqual(manifest["kb_search_call_count"], 1)
            self.assertEqual(manifest["read_article_call_count"], 0)
            self.assertEqual(manifest["kb_requirement_satisfied"], True)

    def test_run_report_recipe_react_basic_redirects_before_final_without_kb_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-basic")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)
            client = make_fake_chat_client([
                {
                    "content": "Premature report [Source 1].",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
                {
                    "content": "",
                    "prompt_tokens": 20,
                    "completion_tokens": 6,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "search_knowledge_base",
                            "arguments": {"query": "Portugal tourism demand"},
                        },
                    ],
                },
                {
                    "content": "Final report [Source 2].",
                    "prompt_tokens": 30,
                    "completion_tokens": 40,
                },
            ])
            search_queries = []

            def fake_search(query):
                search_queries.append(query)
                return [
                    {
                        "chunk_id": "chunk-1",
                        "article_id": "kb-1",
                        "title": "Portugal demand history",
                        "source": "SKIFT",
                        "published_at": "2026-04-01",
                        "url": "https://example.com/kb",
                        "chunk_text": "Earlier Portugal demand context.",
                    }
                ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=client), \
                 patch("reporting.create_report.build_kb_search_function", return_value=fake_search):
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    max_iterations=3,
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            redirected_message = "\n".join(
                message.get("content", "")
                for message in client.calls[1]["messages"]
            )

            self.assertIn("must call search_knowledge_base", redirected_message)
            self.assertEqual(search_queries, ["Portugal tourism demand"])
            self.assertEqual(manifest["model_metrics"]["llm_calls"], 3)
            self.assertEqual(manifest["kb_search_call_count"], 1)
            self.assertEqual(manifest["kb_requirement_satisfied"], True)

    def test_run_report_recipe_react_basic_fails_if_model_refuses_required_kb_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-basic")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)
            client = make_fake_chat_client([
                {
                    "content": "Premature report [Source 1].",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
                {
                    "content": "Still no KB search [Source 1].",
                    "prompt_tokens": 20,
                    "completion_tokens": 6,
                },
            ])

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=client), \
                 patch("reporting.create_report.build_kb_search_function", return_value=lambda query: []):
                with self.assertRaises(ValueError) as error:
                    run_report_recipe(
                        "daily_tourism_intelligence",
                        article_date="2026-04-10",
                        max_iterations=3,
                        yes=True,
                    )

            self.assertIn("search_knowledge_base", str(error.exception))

    def test_run_report_recipe_map_reduce_cancel_stops_before_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-map-reduce")
            write_test_article(recipe)

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=False), \
                 patch("reporting.create_report.build_model_client") as fake_client, \
                 patch("reporting.create_report.call_chat_model") as fake_call:
                with self.assertRaises(ValueError) as error:
                    run_report_recipe(
                        "daily_tourism_intelligence",
                        article_date="2026-04-10",
                        yes=False,
                    )

            self.assertEqual(str(error.exception), "Report generation cancelled")
            fake_client.assert_not_called()
            fake_call.assert_not_called()

    def test_run_report_recipe_progressive_cancel_stops_before_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-progressive")
            write_test_article(recipe)

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=False), \
                 patch("reporting.create_report.build_model_client") as fake_client, \
                 patch("reporting.create_report.call_chat_model") as fake_call:
                with self.assertRaises(ValueError) as error:
                    run_report_recipe(
                        "daily_tourism_intelligence",
                        article_date="2026-04-10",
                        yes=False,
                    )

            self.assertEqual(str(error.exception), "Report generation cancelled")
            fake_client.assert_not_called()
            fake_call.assert_not_called()

    def test_run_report_recipe_map_reduce_counts_batch_and_final_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-map-reduce")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)

            model_results = [
                {
                    "content": "Batch summary [Source 1].",
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                },
                {
                    "content": "",
                    "prompt_tokens": 30,
                    "completion_tokens": 5,
                    "tool_calls": [
                        {
                            "tool_call_id": "call-search-1",
                            "tool_name": "search_knowledge_base",
                            "arguments": {"query": "Portugal tourism context"},
                        },
                    ],
                },
                {
                    "content": "Final report [Source 1].",
                    "prompt_tokens": 40,
                    "completion_tokens": 50,
                },
            ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.build_kb_search_function", return_value=lambda query: []) as fake_search_builder, \
                 patch("reporting.create_report.call_chat_model", side_effect=model_results) as fake_call:
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(fake_call.call_count, 3)
            self.assertEqual(manifest["model_metrics"]["llm_calls"], 3)
            self.assertEqual(manifest["model_metrics"]["prompt_tokens"], 80)
            self.assertEqual(manifest["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
            self.assertEqual(fake_search_builder.call_args.kwargs["indexed_before"], "2026-04-10T23:59:59+00:00")
            self.assertEqual(manifest["kb_search_call_count"], 1)

    def test_run_report_recipe_triage_uses_kb_recipe_and_counts_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-triage")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)

            model_results = [
                {
                    "content": "",
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "tool_calls": [
                        {
                            "tool_call_id": "call-read-1",
                            "tool_name": "read_article",
                            "arguments": {"article_index": 1},
                        },
                    ],
                },
                {
                    "content": "Triage selection complete.",
                    "prompt_tokens": 15,
                    "completion_tokens": 5,
                },
                {
                    "content": "",
                    "prompt_tokens": 30,
                    "completion_tokens": 5,
                    "tool_calls": [
                        {
                            "tool_call_id": "call-search-1",
                            "tool_name": "search_knowledge_base",
                            "arguments": {"query": "Portugal tourism context"},
                        },
                    ],
                },
                {
                    "content": "Final report [Source 1].",
                    "prompt_tokens": 40,
                    "completion_tokens": 50,
                },
            ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.build_kb_search_function", return_value=lambda query: []) as fake_search_builder, \
                 patch("reporting.create_report.call_chat_model", side_effect=model_results) as fake_call:
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(fake_call.call_count, 4)
            self.assertEqual(manifest["model_metrics"]["llm_calls"], 4)
            self.assertEqual(manifest["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
            self.assertEqual(fake_search_builder.call_args.kwargs["indexed_before"], "2026-04-10T23:59:59+00:00")
            self.assertEqual(manifest["tool_call_log"][0]["tool_name"], "read_article")
            self.assertEqual(manifest["tool_call_log"][0]["arguments"], {"article_index": 1})
            self.assertEqual(manifest["tool_call_log"][1]["tool_name"], "search_knowledge_base")
            self.assertEqual(manifest["kb_search_call_count"], 1)
            self.assertEqual(manifest["read_article_call_count"], 1)

    def test_run_report_recipe_hybrid_uses_kb_recipe_and_counts_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-hybrid")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)

            model_results = [
                {
                    "content": '[{"index": 1, "score": 4}]',
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                },
                {
                    "content": "",
                    "prompt_tokens": 30,
                    "completion_tokens": 5,
                    "tool_calls": [
                        {
                            "tool_call_id": "call-search-1",
                            "tool_name": "search_knowledge_base",
                            "arguments": {"query": "Portugal tourism context"},
                        },
                    ],
                },
                {
                    "content": "Final report [Source 1].",
                    "prompt_tokens": 40,
                    "completion_tokens": 50,
                },
            ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.build_kb_search_function", return_value=lambda query: []) as fake_search_builder, \
                 patch("reporting.create_report.call_chat_model", side_effect=model_results) as fake_call:
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(fake_call.call_count, 3)
            self.assertEqual(manifest["model_metrics"]["llm_calls"], 3)
            self.assertEqual(manifest["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
            self.assertEqual(fake_search_builder.call_args.kwargs["indexed_before"], "2026-04-10T23:59:59+00:00")
            self.assertEqual(manifest["kb_search_call_count"], 1)

    def test_run_report_recipe_progressive_counts_batch_and_final_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe = make_test_recipe(tmp, "react-progressive")
            recipe["knowledge_base_recipe"] = "news_recursive_2000_overlap_3large"
            write_test_article(recipe)

            model_results = [
                {
                    "content": "Running draft [Source 1].",
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                },
                {
                    "content": "",
                    "prompt_tokens": 30,
                    "completion_tokens": 5,
                    "tool_calls": [
                        {
                            "tool_call_id": "call-search-1",
                            "tool_name": "search_knowledge_base",
                            "arguments": {"query": "Portugal tourism context"},
                        },
                    ],
                },
                {
                    "content": "Final report [Source 1].",
                    "prompt_tokens": 40,
                    "completion_tokens": 50,
                },
            ]

            with patch("reporting.create_report.load_report_recipe", return_value=recipe), \
                 patch("reporting.create_report.confirm_paid_call", return_value=True), \
                 patch("reporting.create_report.build_model_client", return_value=object()), \
                 patch("reporting.create_report.build_kb_search_function", return_value=lambda query: []) as fake_search_builder, \
                 patch("reporting.create_report.call_chat_model", side_effect=model_results) as fake_call:
                result = run_report_recipe(
                    "daily_tourism_intelligence",
                    article_date="2026-04-10",
                    yes=True,
                )

            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(fake_call.call_count, 3)
            self.assertEqual(manifest["model_metrics"]["llm_calls"], 3)
            self.assertEqual(manifest["model_metrics"]["prompt_tokens"], 80)
            self.assertEqual(manifest["knowledge_base_recipe"], "news_recursive_2000_overlap_3large")
            self.assertEqual(fake_search_builder.call_args.kwargs["indexed_before"], "2026-04-10T23:59:59+00:00")
            self.assertEqual(manifest["kb_search_call_count"], 1)
