"""
Reporting recipe helpers and report generation orchestration.
"""

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
import time

from knowledge_bases.embedding.openai_embeddings import build_embedding_client
from reporting.context.daily_articles import load_clean_articles
from reporting.context.daily_articles import parse_report_datetime
from reporting.context.daily_articles import select_articles_for_report_day
from reporting.context.source_registry import finalize_report_text
from reporting.context.source_registry import make_source_registry
from reporting.context.source_registry import register_daily_articles
from reporting.candidate_selector import DEFAULT_MARGIN_THRESHOLD
from reporting.candidate_selector import DEFAULT_POSITIVE_THRESHOLD
from reporting.candidate_selector import DEFAULT_SELECTOR_MODEL
from reporting.candidate_selector import select_report_candidates
from reporting.evaluation import write_report_run_evaluation
from reporting.html_viewer import write_report_batch_viewer
from reporting.metrics import extract_report_metrics
from reporting.model_calls import build_openai_chat_messages
from reporting.model_calls import build_model_client
from reporting.model_calls import call_chat_model
from reporting.model_calls import confirm_paid_call
from reporting.model_calls import get_chat_request_model
from reporting.model_calls import make_model_usage_tracker
from reporting.model_calls import record_model_usage
from reporting.strategies.context_construction import build_map_reduce_context
from reporting.strategies.context_construction import build_progressive_context
from reporting.strategies.context_construction import build_hybrid_context
from reporting.strategies.context_construction import build_context_from_selected_articles
from reporting.strategies.context_construction import format_article_for_context
from reporting.strategies.context_construction import format_article_titles
from reporting.strategies.context_construction import build_simple_context
from reporting.strategies.context_construction import validate_context_strategy
from reporting.context.daily_articles import get_article_id
from reporting.context.kb_context import format_kb_results_as_sources
from reporting.metrics import build_report_sources


RECIPES_FOLDER = Path("reporting/recipes")
REPORT_BATCH_STRATEGIES = [
    "simple",
    "react-basic",
    "react-map-reduce",
    "react-triage",
    "react-hybrid",
    "react-progressive",
]


def get_report_recipe_path(recipe_name):
    """
    Build the path for a report recipe JSON file.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - A Path object pointing to the recipe file
    """
    return RECIPES_FOLDER / f"{recipe_name}.json"


def list_report_recipe_names():
    """
    List every report recipe name.

    PARAMETERS:
    - None

    RETURNS:
    - A sorted list of recipe names without .json
    """
    recipe_names = []

    for recipe_path in RECIPES_FOLDER.glob("*.json"):
        recipe_names.append(recipe_path.stem)

    recipe_names.sort()
    return recipe_names


def load_report_recipe(recipe_name):
    """
    Load one report recipe from JSON.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - A dictionary loaded from JSON

    RAISES:
    - ValueError if the recipe file does not exist
    """
    recipe_path = get_report_recipe_path(recipe_name)

    if not recipe_path.exists():
        raise ValueError(f"Unknown report recipe: {recipe_name}")

    recipe_text = recipe_path.read_text(encoding="utf-8")
    return json.loads(recipe_text)


def load_prompt_text(prompt_path):
    """
    Load one Markdown prompt file.

    PARAMETERS:
    - prompt_path: Path to a prompt file

    RETURNS:
    - The prompt text

    RAISES:
    - ValueError when the file does not exist
    """
    path = Path(prompt_path)

    if not path.exists():
        raise ValueError(f"Prompt file not found: {prompt_path}")

    return path.read_text(encoding="utf-8")


def normalize_positive_integer(value, error_message):
    """
    Convert a value to a positive integer or raise a clear error.
    """
    try:
        number = int(value)
    except Exception:
        raise ValueError(error_message)

    if number <= 0:
        raise ValueError(error_message)

    return number


def normalize_non_negative_integer(value, error_message):
    """
    Convert a value to a non-negative integer or raise a clear error.
    """
    try:
        number = int(value)
    except Exception:
        raise ValueError(error_message)

    if number < 0:
        raise ValueError(error_message)

    return number


def build_kb_search_function(knowledge_base_recipe, top_k=8, indexed_before=None):
    """
    Build a simple search function for one knowledge-base recipe.
    """
    from knowledge_bases.retrieval.search_sqlite import search_recipe

    def search(query):
        return search_recipe(
            knowledge_base_recipe,
            query,
            top_k=top_k,
            search_mode="ann",
            indexed_before=indexed_before,
        )

    return search


def make_candidate_selector_embedding_recipe(report_recipe):
    """
    Build a minimal embedding recipe dictionary for candidate selection.
    """
    selector_provider = str(
        report_recipe.get(
            "candidate_selector_provider",
            report_recipe.get("model_provider", "openai"),
        )
    ).strip() or "openai"

    selector_recipe = {
        "embedding_provider": selector_provider,
        "embedding_model": report_recipe.get("candidate_selector_model", DEFAULT_SELECTOR_MODEL),
    }

    selector_deployment = str(report_recipe.get("candidate_selector_deployment", "")).strip()
    if selector_deployment:
        selector_recipe["embedding_deployment"] = selector_deployment

    return selector_recipe


def make_batch_summarize_function(client, model_name, prompt_text, model_usage):
    """
    Build a function that summarizes one context batch with the chat model.
    """
    def summarize(batch_text):
        filled_prompt = prompt_text.replace("{batch_text}", batch_text)
        if "{batch_text}" not in prompt_text:
            filled_prompt = prompt_text + "\n\nBatch:\n\n" + batch_text

        messages = [
            {"role": "user", "content": filled_prompt},
        ]
        model_result = call_chat_model(client, model_name, messages)
        record_model_usage(model_usage, model_result)
        return model_result["content"]

    return summarize


def make_progressive_update_function(client, model_name, prompt_text, report_date, model_usage):
    """
    Build a function that updates one running report draft with the chat model.
    """
    def update(current_draft, batch_text):
        filled_prompt = prompt_text.replace("{current_draft}", current_draft)
        filled_prompt = filled_prompt.replace("{batch_text}", batch_text)
        filled_prompt = filled_prompt.replace("{date}", report_date)

        messages = [
            {"role": "user", "content": filled_prompt},
        ]
        model_result = call_chat_model(client, model_name, messages)
        record_model_usage(model_usage, model_result)
        return model_result["content"]

    return update


def parse_json_array_from_text(text):
    """
    Parse a JSON array from model text.
    """
    start = text.find("[")
    end = text.rfind("]") + 1

    if start < 0 or end <= start:
        return []

    try:
        values = json.loads(text[start:end])
    except Exception:
        return []

    if not isinstance(values, list):
        return []

    return values


def make_triage_select_function(client, model_name, model_usage):
    """
    Build a function that selects article indexes from title lines.
    """
    def select(title_lines):
        prompt = (
            "Select the most tourism-relevant article indexes. "
            "Return only a JSON array of integers, for example [1, 4, 8]."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": title_lines},
        ]
        result = call_chat_model(client, model_name, messages)
        record_model_usage(model_usage, result)
        values = parse_json_array_from_text(result["content"])
        selected_indexes = []

        for value in values:
            try:
                selected_indexes.append(int(value))
            except Exception:
                pass

        return selected_indexes

    return select


def make_hybrid_score_function(client, model_name, prompt_text, model_usage):
    """
    Build a function that scores article titles.
    """
    def score(title_lines):
        messages = [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": title_lines},
        ]
        result = call_chat_model(client, model_name, messages)
        record_model_usage(model_usage, result)
        values = parse_json_array_from_text(result["content"])
        scores = {}

        for item in values:
            if isinstance(item, dict):
                try:
                    index = int(item.get("index", 0))
                    score_value = int(item.get("score", 0))
                except Exception:
                    index = 0
                    score_value = 0

                if index > 0:
                    scores[index] = score_value

        return scores

    return score


def normalize_max_iterations(value, default_value):
    """
    Convert the max-iterations option to a positive integer.
    """
    selected_value = value
    if selected_value is None:
        selected_value = default_value

    return normalize_positive_integer(
        selected_value,
        "Max iterations must be a positive integer",
    )


def strategy_uses_knowledge_base(context_strategy):
    """
    Return True when a context strategy should have KB search available.
    """
    return context_strategy != "simple"


def get_available_tools_for_strategy(context_strategy):
    """
    Return the tool names exposed to a context strategy.
    """
    if context_strategy == "simple":
        return []

    if context_strategy == "react-triage":
        return ["read_article", "search_knowledge_base"]

    return ["search_knowledge_base"]


def get_required_tool_policy_for_strategy(context_strategy):
    """
    Return the minimum required tool calls for a context strategy.
    """
    if strategy_uses_knowledge_base(context_strategy):
        return {
            "minimum_search_knowledge_base_calls": 1,
        }

    return {}


def count_tool_calls_by_name(tool_call_log):
    """
    Count all recorded tool calls by tool name.
    """
    counts = {}

    for tool_call in tool_call_log or []:
        tool_name = tool_call.get("tool_name", "")
        if not tool_name:
            continue
        counts[tool_name] = counts.get(tool_name, 0) + 1

    return counts


def count_successful_tool_calls(tool_call_log, tool_name):
    """
    Count successful tool calls with the requested tool name.
    """
    count = 0

    for tool_call in tool_call_log or []:
        if tool_call.get("tool_name") == tool_name and tool_call.get("status") == "ok":
            count = count + 1

    return count


def extract_selected_article_ids_from_tool_log(tool_call_log):
    """
    Return successful read_article ids, preserving first-seen order.
    """
    selected_article_ids = []

    for tool_call in tool_call_log or []:
        if tool_call.get("tool_name") != "read_article":
            continue
        if tool_call.get("status") != "ok":
            continue

        article_id = str(tool_call.get("article_id", "") or "").strip()
        if not article_id:
            continue
        if article_id in selected_article_ids:
            continue

        selected_article_ids.append(article_id)

    return selected_article_ids


def build_react_triage_fallback_query(context_result):
    """
    Build one simple fallback KB query from the first chosen daily article title.
    """
    registry = context_result.get("registry", {}) or {}

    for source_item in registry.get("source_articles", []):
        if source_item.get("source_type") != "daily":
            continue

        article = source_item.get("article", {}) or {}
        metadata = article.get("metadata", {}) or {}
        title = str(metadata.get("title", "") or "").strip()
        if title:
            return title

    return ""


def kb_requirement_is_satisfied(tool_call_log, required_tool_policy):
    """
    Return True when the required KB search policy is satisfied.
    """
    minimum_search_calls = int(
        required_tool_policy.get("minimum_search_knowledge_base_calls", 0) or 0
    )
    if minimum_search_calls <= 0:
        return True

    successful_search_calls = count_successful_tool_calls(
        tool_call_log,
        "search_knowledge_base",
    )
    return successful_search_calls >= minimum_search_calls


def build_search_tool_schema():
    """
    Build the search_knowledge_base tool schema for OpenAI chat calls.
    """
    return {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the selected tourism news knowledge base for older context "
                "published or indexed no later than the report date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A concise semantic search query.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def build_read_article_tool_schema():
    """
    Build the read_article tool schema for triage report generation.
    """
    return {
        "type": "function",
        "function": {
            "name": "read_article",
            "description": "Read one candidate article by its 1-based article index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_index": {
                        "type": "integer",
                        "description": "The 1-based index shown in the candidate title list.",
                    },
                },
                "required": ["article_index"],
                "additionalProperties": False,
            },
        },
    }


def build_assistant_message_from_tool_result(model_result):
    """
    Build the assistant message that precedes tool responses.
    """
    assistant_message = {
        "role": "assistant",
        "content": model_result.get("content", "") or "",
    }
    tool_calls = []

    for tool_call in model_result.get("tool_calls", []) or []:
        arguments_text = tool_call.get("arguments_text", "")
        if not arguments_text:
            arguments_text = json.dumps(tool_call.get("arguments", {}))

        tool_calls.append({
            "id": tool_call.get("tool_call_id", ""),
            "type": "function",
            "function": {
                "name": tool_call.get("tool_name", ""),
                "arguments": arguments_text,
            },
        })

    if tool_calls:
        assistant_message["tool_calls"] = tool_calls

    return assistant_message


def make_tool_log_entry(strategy, phase, iteration, tool_call):
    """
    Create the shared part of a manifest tool-call log entry.
    """
    return {
        "strategy": strategy,
        "phase": phase,
        "iteration": iteration,
        "tool_call_id": tool_call.get("tool_call_id", ""),
        "tool_name": tool_call.get("tool_name", ""),
        "arguments": tool_call.get("arguments", {}),
        "status": "ok",
        "result_count": 0,
        "article_id": "",
        "retrieved_chunk_ids": [],
        "rag_source_article_ids": [],
        "error": "",
    }


def execute_search_tool(registry, search_function, strategy, phase, iteration, tool_call):
    """
    Run one search_knowledge_base tool call.
    """
    log_entry = make_tool_log_entry(strategy, phase, iteration, tool_call)
    arguments = tool_call.get("arguments", {}) or {}
    query = str(arguments.get("query", "") or "").strip()

    if not query:
        log_entry["status"] = "error"
        log_entry["error"] = "Missing query"
        return {
            "content": "ERROR: search_knowledge_base needs a non-empty query.",
            "log_entry": log_entry,
            "retrieved_chunk_ids": [],
        }

    try:
        before_rag_ids = set(registry.get("rag_source_article_ids", []))
        results = search_function(query)
        formatted = format_kb_results_as_sources(registry, results)
        after_rag_ids = set(registry.get("rag_source_article_ids", []))
    except Exception as error:
        log_entry["status"] = "error"
        log_entry["error"] = str(error)
        return {
            "content": f"ERROR: search_knowledge_base failed: {error}",
            "log_entry": log_entry,
            "retrieved_chunk_ids": [],
        }

    context_text = formatted["context_text"]
    retrieved_chunk_ids = formatted["retrieved_chunk_ids"]
    new_rag_ids = sorted(after_rag_ids - before_rag_ids)

    log_entry["result_count"] = len(results or [])
    log_entry["retrieved_chunk_ids"] = retrieved_chunk_ids
    log_entry["rag_source_article_ids"] = new_rag_ids

    if not context_text:
        content = f"No knowledge-base results found for query: {query}"
    else:
        content = f"Knowledge-base results for query: {query}\n\n{context_text}"

    return {
        "content": content,
        "log_entry": log_entry,
        "retrieved_chunk_ids": retrieved_chunk_ids,
    }


def find_registered_source_item(registry, article_id):
    """
    Find a source registry item by article id.
    """
    for source_item in registry.get("source_articles", []):
        if source_item.get("article_id") == article_id:
            return source_item

    return None


def register_article_if_needed(registry, article):
    """
    Register one daily article and return its source item.
    """
    article_id = get_article_id(article)
    source_item = find_registered_source_item(registry, article_id)
    if source_item is not None:
        return source_item

    register_daily_articles(registry, [article])
    return find_registered_source_item(registry, article_id)


def execute_read_article_tool(registry, articles, strategy, phase, iteration, tool_call):
    """
    Run one read_article tool call.
    """
    log_entry = make_tool_log_entry(strategy, phase, iteration, tool_call)
    arguments = tool_call.get("arguments", {}) or {}

    try:
        article_index = int(arguments.get("article_index", 0))
    except Exception:
        article_index = 0

    if article_index < 1 or article_index > len(articles):
        log_entry["status"] = "error"
        log_entry["error"] = "Article index out of range"
        return {
            "content": f"ERROR: read_article needs an article_index from 1 to {len(articles)}.",
            "log_entry": log_entry,
            "retrieved_chunk_ids": [],
        }

    article = articles[article_index - 1]
    source_item = register_article_if_needed(registry, article)
    if source_item is None:
        log_entry["status"] = "error"
        log_entry["error"] = "Article could not be registered"
        return {
            "content": "ERROR: article could not be registered as a report source.",
            "log_entry": log_entry,
            "retrieved_chunk_ids": [],
        }

    log_entry["article_id"] = str(source_item.get("article_id", "") or "")
    log_entry["result_count"] = 1
    content = format_article_for_context(source_item, 3000)
    return {
        "content": content,
        "log_entry": log_entry,
        "retrieved_chunk_ids": [],
    }


def execute_tool_call(registry, articles, search_function, strategy, phase, iteration, tool_call):
    """
    Execute one model-requested tool call.
    """
    tool_name = tool_call.get("tool_name", "")

    if tool_name == "search_knowledge_base":
        return execute_search_tool(registry, search_function, strategy, phase, iteration, tool_call)

    if tool_name == "read_article":
        return execute_read_article_tool(registry, articles, strategy, phase, iteration, tool_call)

    log_entry = make_tool_log_entry(strategy, phase, iteration, tool_call)
    log_entry["status"] = "error"
    log_entry["error"] = f"Unknown tool: {tool_name}"
    return {
        "content": f"ERROR: Unknown tool: {tool_name}",
        "log_entry": log_entry,
        "retrieved_chunk_ids": [],
    }


def run_tool_calling_report(
    client,
    model_name,
    messages,
    tools,
    registry,
    articles,
    search_function,
    model_usage,
    strategy,
    phase,
    max_iterations,
    required_tool_policy=None,
    search_requirement_fallback_query="",
):
    """
    Run a small ReAct-style loop until the model returns report text.
    """
    current_messages = list(messages)
    retrieved_chunk_ids = []
    tool_call_log = []
    iteration = 1
    required_policy = required_tool_policy or {}
    minimum_search_calls = int(
        required_policy.get("minimum_search_knowledge_base_calls", 0) or 0
    )
    minimum_read_article_calls = int(
        required_policy.get("minimum_read_article_calls", 0) or 0
    )
    successful_search_calls = 0
    successful_read_article_calls = 0
    required_search_redirect_sent = False
    required_search_fallback_used = False
    required_read_article_redirect_sent = False

    while iteration <= max_iterations:
        model_result = call_chat_model(client, model_name, current_messages, tools=tools)
        record_model_usage(model_usage, model_result)
        tool_calls = model_result.get("tool_calls", []) or []

        if not tool_calls:
            if successful_read_article_calls < minimum_read_article_calls:
                if not required_read_article_redirect_sent:
                    current_messages.append({
                        "role": "assistant",
                        "content": model_result.get("content", "") or "",
                    })
                    current_messages.append({
                        "role": "user",
                        "content": (
                            "You must call read_article at least once before finalizing triage. "
                            "Choose the most relevant article_index from the title list and read it "
                            "before continuing."
                        ),
                    })
                    required_read_article_redirect_sent = True
                    iteration = iteration + 1
                    continue

                raise ValueError(
                    "react-triage must read at least one article before building final context"
                )

            if successful_search_calls < minimum_search_calls:
                if not required_search_redirect_sent:
                    current_messages.append({
                        "role": "assistant",
                        "content": model_result.get("content", "") or "",
                    })
                    current_messages.append({
                        "role": "user",
                        "content": (
                            "You must call search_knowledge_base at least once before "
                            "writing the final report. Choose a concise query that checks "
                            "older knowledge-base context for today's tourism signal."
                        ),
                    })
                    required_search_redirect_sent = True
                    iteration = iteration + 1
                    continue

                fallback_query = str(search_requirement_fallback_query or "").strip()
                if fallback_query and not required_search_fallback_used:
                    required_search_fallback_used = True
                    current_messages.append({
                        "role": "assistant",
                        "content": model_result.get("content", "") or "",
                    })
                    fallback_tool_call = {
                        "tool_call_id": f"fallback-search-{iteration}",
                        "tool_name": "search_knowledge_base",
                        "arguments": {"query": fallback_query},
                    }
                    tool_result = execute_tool_call(
                        registry,
                        articles,
                        search_function,
                        strategy,
                        phase,
                        iteration,
                        fallback_tool_call,
                    )
                    tool_call_log.append(tool_result["log_entry"])
                    retrieved_chunk_ids.extend(tool_result["retrieved_chunk_ids"])
                    if tool_result["log_entry"].get("status") == "ok":
                        successful_search_calls = successful_search_calls + 1

                    current_messages.append({
                        "role": "user",
                        "content": (
                            "You skipped the required knowledge-base search twice, so a fallback "
                            "search_knowledge_base call was run using the first chosen article title.\n\n"
                            f"{tool_result['content']}\n\n"
                            "Use this evidence to write the final report now. Do not call more tools."
                        ),
                    })
                    iteration = iteration + 1
                    continue

                raise ValueError(
                    "search_knowledge_base is required before final report generation"
                )

            return {
                "content": model_result["content"],
                "retrieved_chunk_ids": retrieved_chunk_ids,
                "tool_call_log": tool_call_log,
            }

        current_messages.append(build_assistant_message_from_tool_result(model_result))

        for tool_call in tool_calls:
            tool_result = execute_tool_call(
                registry,
                articles,
                search_function,
                strategy,
                phase,
                iteration,
                tool_call,
            )
            tool_call_log.append(tool_result["log_entry"])
            retrieved_chunk_ids.extend(tool_result["retrieved_chunk_ids"])
            if (
                tool_result["log_entry"].get("tool_name") == "search_knowledge_base"
                and tool_result["log_entry"].get("status") == "ok"
            ):
                successful_search_calls = successful_search_calls + 1
            if (
                tool_result["log_entry"].get("tool_name") == "read_article"
                and tool_result["log_entry"].get("status") == "ok"
            ):
                successful_read_article_calls = successful_read_article_calls + 1
            current_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("tool_call_id", ""),
                "name": tool_call.get("tool_name", ""),
                "content": tool_result["content"],
            })

        iteration = iteration + 1

    if successful_read_article_calls < minimum_read_article_calls:
        raise ValueError(
            "react-triage must read at least one article before building final context"
        )

    if successful_search_calls < minimum_search_calls:
        raise ValueError(
            "search_knowledge_base is required before final report generation"
        )

    current_messages.append({
        "role": "user",
        "content": "Use the gathered evidence to write the final report now. Do not call more tools.",
    })
    model_result = call_chat_model(client, model_name, current_messages)
    record_model_usage(model_usage, model_result)
    return {
        "content": model_result["content"],
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "tool_call_log": tool_call_log,
    }


def append_tool_guidance(messages, allow_read_article, require_kb_search=False):
    """
    Add concise tool-use guidance to the report prompt.
    """
    updated_messages = []
    for message in messages:
        updated_messages.append(dict(message))

    guidance_lines = [
        "",
        "Tool use:",
        "- Do not cite a source unless its numbered source block was provided in the prompt or by a tool result.",
    ]
    if require_kb_search:
        guidance_lines.append(
            "- You must call search_knowledge_base at least once before writing the final report."
        )
        guidance_lines.append(
            "- After one KB search, continue searching only if older context is still needed."
        )
    else:
        guidance_lines.append(
            "- Use search_knowledge_base only when older context is needed to verify or explain today's tourism signal."
        )

    if allow_read_article:
        guidance_lines.append("- Use read_article before citing or analyzing an article from the title list.")

    updated_messages[-1]["content"] = updated_messages[-1]["content"] + "\n".join(guidance_lines)
    return updated_messages


def run_report_from_context(
    strategy,
    phase,
    context_result,
    client,
    model_name,
    system_prompt,
    user_prompt,
    report_date,
    search_function,
    model_usage,
    max_iterations,
):
    """
    Generate a final report from a prepared context block with KB search available.
    """
    messages = build_openai_chat_messages(
        system_prompt,
        user_prompt,
        context_result["context_text"],
        report_date,
    )
    required_tool_policy = get_required_tool_policy_for_strategy(strategy)
    fallback_query = ""

    if strategy == "react-triage" and phase == "final_report":
        fallback_query = build_react_triage_fallback_query(context_result)

    messages = append_tool_guidance(
        messages,
        allow_read_article=False,
        require_kb_search=required_tool_policy != {},
    )
    loop_result = run_tool_calling_report(
        client,
        model_name,
        messages,
        [build_search_tool_schema()],
        context_result["registry"],
        [],
        search_function,
        model_usage,
        strategy,
        phase,
        max_iterations,
        required_tool_policy=required_tool_policy,
        search_requirement_fallback_query=fallback_query,
    )

    retrieved_chunk_ids = list(context_result["retrieved_chunk_ids"])
    retrieved_chunk_ids.extend(loop_result["retrieved_chunk_ids"])

    return {
        "report_text": loop_result["content"],
        "registry": context_result["registry"],
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "tool_call_log": loop_result["tool_call_log"],
    }


def generate_react_basic_report(
    articles,
    client,
    model_name,
    system_prompt,
    user_prompt,
    report_date,
    search_function,
    model_usage,
    max_iterations,
):
    """
    Generate a basic ReAct report from full selected article context.
    """
    context_result = build_simple_context(articles)
    return run_report_from_context(
        "react-basic",
        "final_report",
        context_result,
        client,
        model_name,
        system_prompt,
        user_prompt,
        report_date,
        search_function,
        model_usage,
        max_iterations,
    )


def generate_map_reduce_report(
    articles,
    client,
    model_name,
    system_prompt,
    user_prompt,
    map_prompt,
    report_date,
    search_function,
    model_usage,
    max_iterations,
):
    """
    Summarize article batches, then generate a report with optional KB search.
    """
    summarize_function = make_batch_summarize_function(
        client,
        model_name,
        map_prompt,
        model_usage,
    )
    context_result = build_map_reduce_context(articles, summarize_function)
    return run_report_from_context(
        "react-map-reduce",
        "reduce",
        context_result,
        client,
        model_name,
        system_prompt,
        user_prompt,
        report_date,
        search_function,
        model_usage,
        max_iterations,
    )


def generate_progressive_report(
    articles,
    client,
    model_name,
    system_prompt,
    user_prompt,
    progressive_prompt,
    report_date,
    search_function,
    model_usage,
    max_iterations,
):
    """
    Build a progressive draft, then enrich it with optional KB search.
    """
    update_function = make_progressive_update_function(
        client,
        model_name,
        progressive_prompt,
        report_date,
        model_usage,
    )
    context_result = build_progressive_context(articles, update_function)
    return run_report_from_context(
        "react-progressive",
        "enrichment",
        context_result,
        client,
        model_name,
        system_prompt,
        user_prompt,
        report_date,
        search_function,
        model_usage,
        max_iterations,
    )


def generate_hybrid_report(
    articles,
    client,
    model_name,
    system_prompt,
    user_prompt,
    scoring_prompt,
    report_date,
    search_function,
    model_usage,
    max_iterations,
):
    """
    Score titles, keep the stronger candidates, then run basic ReAct.
    """
    score_function = make_hybrid_score_function(
        client,
        model_name,
        scoring_prompt,
        model_usage,
    )
    context_result = build_hybrid_context(articles, score_function)
    return run_report_from_context(
        "react-hybrid",
        "final_report",
        context_result,
        client,
        model_name,
        system_prompt,
        user_prompt,
        report_date,
        search_function,
        model_usage,
        max_iterations,
    )


def generate_triage_report(
    articles,
    client,
    model_name,
    system_prompt,
    user_prompt,
    report_date,
    search_function,
    model_usage,
    max_iterations,
):
    """
    Let the model choose articles to read, then reuse the shared KB-backed report stage.
    """
    title_lines = format_article_titles(articles)
    context_text = (
        "Candidate article titles are listed below. "
        "Use read_article before citing or analyzing any candidate article.\n\n"
        f"{title_lines}"
    )
    messages = build_openai_chat_messages(
        system_prompt,
        user_prompt,
        context_text,
        report_date,
    )
    messages = append_tool_guidance(
        messages,
        allow_read_article=True,
        require_kb_search=False,
    )
    messages[-1]["content"] = messages[-1]["content"] + (
        "\n- For react-triage, first review the candidate titles, then read the most relevant daily articles."
        "\n- After triage, the final report phase must perform at least one KB search for older or background context before writing the final report."
    )
    triage_registry = make_source_registry()
    triage_result = run_tool_calling_report(
        client,
        model_name,
        messages,
        [build_read_article_tool_schema()],
        triage_registry,
        articles,
        search_function,
        model_usage,
        "react-triage",
        "triage",
        max_iterations,
        required_tool_policy={"minimum_read_article_calls": 1},
    )

    selected_article_ids = extract_selected_article_ids_from_tool_log(
        triage_result["tool_call_log"]
    )
    if not selected_article_ids:
        raise ValueError(
            "react-triage must read at least one article before building final context"
        )

    context_result = build_context_from_selected_articles(
        articles,
        selected_article_ids,
    )
    final_result = run_report_from_context(
        "react-triage",
        "final_report",
        context_result,
        client,
        model_name,
        system_prompt,
        user_prompt,
        report_date,
        search_function,
        model_usage,
        max_iterations,
    )

    retrieved_chunk_ids = list(triage_result["retrieved_chunk_ids"])
    retrieved_chunk_ids.extend(final_result["retrieved_chunk_ids"])

    tool_call_log = list(triage_result["tool_call_log"])
    tool_call_log.extend(final_result["tool_call_log"])

    return {
        "report_text": final_result["report_text"],
        "registry": final_result["registry"],
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "tool_call_log": tool_call_log,
    }


def build_report_manifest(
    recipe,
    context_strategy,
    report_datetime,
    window_start,
    window_end,
    registry,
    prompt_files,
    retrieved_chunk_ids,
    metrics,
    model_metrics,
    candidate_selection=None,
    tool_call_log=None,
    available_tools=None,
    required_tool_policy=None,
):
    """
    Build the metadata saved next to a generated report.

    PARAMETERS:
    - recipe: The report recipe dictionary
    - context_strategy: The context-construction strategy name
    - report_datetime: The report run datetime as text
    - window_start: The report window start datetime as text
    - window_end: The report window end datetime as text
    - registry: The source registry used for citations
    - prompt_files: Prompt file names used for the report
    - retrieved_chunk_ids: Knowledge-base chunk IDs retrieved for the report
    - metrics: Report quality and citation metrics
    - model_metrics: Model token and call metrics

    RETURNS:
    - A dictionary ready to write as JSON
    """
    report_source_article_ids = []

    for source_article in registry.get("source_articles", []):
        report_source_article_ids.append(source_article.get("article_id"))

    selected_tool_call_log = tool_call_log or []
    selected_required_tool_policy = required_tool_policy or {}
    tool_call_counts = count_tool_calls_by_name(selected_tool_call_log)
    successful_kb_search_call_count = count_successful_tool_calls(
        selected_tool_call_log,
        "search_knowledge_base",
    )

    return {
        "recipe_name": recipe["name"],
        "context_strategy": context_strategy,
        "report_datetime": report_datetime,
        "window_start": window_start,
        "window_end": window_end,
        "daily_article_ids": registry.get("daily_article_ids", []),
        "rag_source_article_ids": registry.get("rag_source_article_ids", []),
        "report_source_article_ids": report_source_article_ids,
        "report_sources": build_report_sources(registry, window_start, window_end),
        "knowledge_base_recipe": recipe.get("knowledge_base_recipe", ""),
        "prompt_files": prompt_files,
        "candidate_selection": candidate_selection or {},
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "available_tools": available_tools or [],
        "required_tool_policy": selected_required_tool_policy,
        "tool_call_counts": tool_call_counts,
        "kb_search_call_count": tool_call_counts.get("search_knowledge_base", 0),
        "successful_kb_search_call_count": successful_kb_search_call_count,
        "read_article_call_count": tool_call_counts.get("read_article", 0),
        "kb_requirement_satisfied": kb_requirement_is_satisfied(
            selected_tool_call_log,
            selected_required_tool_policy,
        ),
        "tool_call_log": selected_tool_call_log,
        "metrics": metrics,
        "model_metrics": model_metrics,
    }


def build_unfiltered_candidate_selection(raw_count, kept_count, candidate_limit):
    """
    Build a candidate-selection manifest block for unfiltered runs.
    """
    return {
        "method": "none",
        "raw_count": raw_count,
        "kept_count": kept_count,
        "excluded_count": max(0, raw_count - kept_count),
        "candidate_limit": candidate_limit,
        "excluded_examples": [],
    }


def normalize_candidate_limit_value(recipe, candidate_limit):
    """
    Normalize one candidate limit from CLI or recipe configuration.
    """
    selected_candidate_limit = candidate_limit
    if selected_candidate_limit is None:
        selected_candidate_limit = recipe.get("candidate_limit")
    if selected_candidate_limit is not None:
        selected_candidate_limit = normalize_positive_integer(
            selected_candidate_limit,
            "Candidate limit must be a positive integer",
        )
    return selected_candidate_limit


def prepare_candidate_pool(recipe, daily_articles, candidate_limit=None):
    """
    Build the selected candidate article pool for one report day.
    """
    selected_candidate_limit = normalize_candidate_limit_value(recipe, candidate_limit)

    selector_name = recipe.get("candidate_selector", "none")

    if selector_name == "embedding_prototypes":
        selector_recipe = make_candidate_selector_embedding_recipe(recipe)
        selector_client = build_embedding_client(selector_recipe)
        positive_threshold = float(
            recipe.get("candidate_selector_positive_threshold", DEFAULT_POSITIVE_THRESHOLD)
        )
        margin_threshold = float(
            recipe.get("candidate_selector_margin_threshold", DEFAULT_MARGIN_THRESHOLD)
        )
        selector_result = select_report_candidates(
            daily_articles,
            selector_client,
            model_name=selector_recipe,
            candidate_limit=selected_candidate_limit,
            positive_threshold=positive_threshold,
            margin_threshold=margin_threshold,
        )
        return {
            "selected_articles": selector_result["articles"],
            "candidate_selection": selector_result["selection"],
            "candidate_limit": selected_candidate_limit,
        }

    if selector_name in ["", "none"]:
        selected_articles = list(daily_articles)
        if selected_candidate_limit is not None:
            selected_articles = selected_articles[:selected_candidate_limit]
        return {
            "selected_articles": selected_articles,
            "candidate_selection": build_unfiltered_candidate_selection(
                len(daily_articles),
                len(selected_articles),
                selected_candidate_limit,
            ),
            "candidate_limit": selected_candidate_limit,
        }

    raise ValueError(f"Unknown candidate selector: {selector_name}")


def build_report_filename(recipe_name, context_strategy, report_date):
    """
    Build a markdown report filename.

    PARAMETERS:
    - recipe_name: The report recipe name
    - context_strategy: The context-construction strategy name
    - report_date: The date label for the report

    RETURNS:
    - A safe filename ending in .md
    """
    safe_recipe_name = recipe_name.replace(" ", "_")
    safe_context_strategy = context_strategy.replace(" ", "_")
    utc_suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")

    return f"{report_date}_{safe_recipe_name}_{safe_context_strategy}_{utc_suffix}.md"


def save_report_artifacts(
    output_folder,
    recipe_name,
    context_strategy,
    report_date,
    report_text,
    manifest,
    artifact_stem=None,
):
    """
    Save the generated report markdown and matching manifest JSON.

    PARAMETERS:
    - output_folder: Folder where artifacts should be written
    - recipe_name: The report recipe name
    - context_strategy: The context-construction strategy name
    - report_date: The date label for the report
    - report_text: The markdown report body
    - manifest: The manifest dictionary

    RETURNS:
    - A dictionary containing the report and manifest paths
    """
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    if artifact_stem:
        report_filename = f"{artifact_stem}.md"
    else:
        report_filename = build_report_filename(recipe_name, context_strategy, report_date)

    report_path = output_path / report_filename
    manifest_filename = report_path.stem + "_manifest.json"
    manifest_path = output_path / manifest_filename

    report_path.write_text(report_text, encoding="utf-8")
    manifest_text = json.dumps(manifest, indent=2)
    manifest_path.write_text(manifest_text + "\n", encoding="utf-8")

    return {
        "report_path": report_path,
        "manifest_path": manifest_path,
    }


def explain_report_recipe_text(recipe_name):
    """
    Create a plain-language explanation for one report recipe.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - A multi-line string explaining the recipe
    """
    recipe = load_report_recipe(recipe_name)

    lines = []
    lines.append(f"Recipe: {recipe['name']}")
    lines.append(f"Purpose: {recipe['purpose']}")
    lines.append(f"Input corpus: {recipe['input_corpus']}")
    lines.append(f"Context source: {recipe.get('context_source', recipe.get('knowledge_base_recipe', ''))}")
    lines.append(f"Prompt strategy: {recipe.get('prompt_strategy', 'fixed_daily_tourism_report')}")
    if "context_strategy" in recipe:
        lines.append(f"Context strategy: {recipe['context_strategy']}")
    lines.append(f"Report window: {recipe['report_window_hours']} hours")
    lines.append(f"Output folder: {recipe['output_folder']}")

    return "\n".join(lines)


def print_report_status():
    """
    Print report status.
    """
    recipe_names = list_report_recipe_names()

    print("[INFO] Reporting status")
    print(f"    recipes found: {len(recipe_names)}")
    print("    output folder: shared_data/reports")

    for position, recipe_name in enumerate(recipe_names, start=1):
        recipe = load_report_recipe(recipe_name)
        strategy = recipe.get("context_strategy", "simple")
        print(f"[{position}/{len(recipe_names)}] {recipe_name}: context_strategy={strategy}")


def run_report_recipe(
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
    """
    Create one report recipe using the selected context strategy.

    PARAMETERS:
    - recipe_name: The recipe name without .json
    - context_strategy: Optional context-construction strategy override
    - article_date: Optional article date filter
    - report_datetime: Optional report datetime override
    - hours: Optional report window override
    - knowledge_base_recipe: Optional knowledge-base recipe override
    - max_iterations: Optional maximum context-construction iterations
    - candidate_limit: Optional article candidate limit
    - yes: Whether confirmation prompts should be skipped
    - output_folder_override: Optional output folder override for grouped batch runs
    - artifact_stem: Optional fixed output filename stem for grouped batch runs
    - precomputed_daily_articles: Optional shared batch day article list
    - precomputed_selected_articles: Optional shared batch selected article list
    - precomputed_candidate_selection: Optional shared batch selection metadata

    RETURNS:
    - A dictionary containing the report and manifest paths
    """
    recipe = load_report_recipe(recipe_name)

    selected_context_strategy = context_strategy
    if selected_context_strategy is None:
        selected_context_strategy = recipe.get("context_strategy", "simple")
    selected_context_strategy = validate_context_strategy(selected_context_strategy)

    report_datetime_value = report_datetime
    if report_datetime_value is None:
        report_datetime_value = article_date
    report_time = parse_report_datetime(report_datetime_value)

    selected_max_iterations = normalize_max_iterations(
        max_iterations,
        recipe.get("max_iterations", 3),
    )
    normalize_candidate_limit_value(recipe, candidate_limit)

    search_function = None
    selected_knowledge_base_recipe = ""
    if strategy_uses_knowledge_base(selected_context_strategy):
        selected_knowledge_base_recipe = knowledge_base_recipe
        if selected_knowledge_base_recipe is None:
            selected_knowledge_base_recipe = recipe.get("knowledge_base_recipe", "")

    report_window_hours = hours
    if report_window_hours is None:
        report_window_hours = recipe["report_window_hours"]
    report_window_hours = normalize_positive_integer(
        report_window_hours,
        "Report window hours must be a positive integer",
    )
    window_start = report_time.replace(hour=0, minute=0, second=0, microsecond=0)

    recipe_for_manifest = dict(recipe)
    recipe_for_manifest["knowledge_base_recipe"] = selected_knowledge_base_recipe

    print(f"[INFO] Running report recipe: {recipe['name']}")
    print(f"      Context strategy: {selected_context_strategy}")
    print("[1/6] Loading clean articles")
    print(f"      Input: {recipe['input_corpus']}")
    if precomputed_daily_articles is None:
        raw_articles = load_clean_articles(recipe["input_corpus"])
        daily_articles = select_articles_for_report_day(
            raw_articles,
            report_time.isoformat(),
        )
    else:
        print("      Using precomputed batch day articles")
        daily_articles = list(precomputed_daily_articles)

    print(f"      Daily articles before candidate selection: {len(daily_articles)}")
    print(f"      Report window start: {window_start.isoformat()}")
    print(f"      Report window end: {report_time.isoformat()}")

    if not daily_articles:
        raise ValueError("No clean articles found inside the report day")

    print("[2/6] Confirming model call")
    confirmed = confirm_paid_call(recipe["name"], selected_context_strategy, yes=yes)
    if not confirmed:
        raise ValueError("Report generation cancelled")

    if strategy_uses_knowledge_base(selected_context_strategy):
        if not selected_knowledge_base_recipe:
            raise ValueError(f"{selected_context_strategy} needs --knowledge-base-recipe")

    client = build_model_client(recipe)
    model_name = get_chat_request_model(recipe)
    model_usage = make_model_usage_tracker()
    generation_started_at = datetime.now(timezone.utc)
    report_date = report_time.date().isoformat()

    if precomputed_selected_articles is not None:
        print("      Using precomputed batch candidate pool")
        selected_articles = list(precomputed_selected_articles)
        candidate_selection = precomputed_candidate_selection or {}
    else:
        candidate_pool = prepare_candidate_pool(
            recipe,
            daily_articles,
            candidate_limit=candidate_limit,
        )
        selected_articles = candidate_pool["selected_articles"]
        candidate_selection = candidate_pool["candidate_selection"]

    print(f"      Selected articles: {len(selected_articles)}")
    if not selected_articles:
        raise ValueError("No tourism-relevant candidate articles found for report generation")

    if strategy_uses_knowledge_base(selected_context_strategy):
        search_function = build_kb_search_function(
            selected_knowledge_base_recipe,
            indexed_before=report_time.isoformat(),
        )

    system_prompt = load_prompt_text(recipe["system_prompt"])
    user_prompt = load_prompt_text(recipe["user_prompt"])
    prompt_files = [recipe["system_prompt"], recipe["user_prompt"]]
    tool_call_log = []
    available_tools = get_available_tools_for_strategy(selected_context_strategy)
    required_tool_policy = get_required_tool_policy_for_strategy(selected_context_strategy)

    print("[3/6] Running context-construction strategy")
    if selected_context_strategy == "simple":
        context_result = build_simple_context(selected_articles)
        registry = context_result["registry"]
        retrieved_chunk_ids = context_result["retrieved_chunk_ids"]

        print("[4/6] Calling chat model")
        messages = build_openai_chat_messages(
            system_prompt,
            user_prompt,
            context_result["context_text"],
            report_date,
        )
        model_result = call_chat_model(client, model_name, messages)
        record_model_usage(model_usage, model_result)
        raw_report_text = model_result["content"]
    elif selected_context_strategy == "react-basic":
        generation_result = generate_react_basic_report(
            selected_articles,
            client,
            model_name,
            system_prompt,
            user_prompt,
            report_date,
            search_function,
            model_usage,
            selected_max_iterations,
        )
        registry = generation_result["registry"]
        retrieved_chunk_ids = generation_result["retrieved_chunk_ids"]
        tool_call_log = generation_result["tool_call_log"]
        raw_report_text = generation_result["report_text"]
    elif selected_context_strategy == "react-map-reduce":
        prompt_text = load_prompt_text("reporting/prompts/map_reduce_batch.md")
        prompt_files.append("reporting/prompts/map_reduce_batch.md")
        generation_result = generate_map_reduce_report(
            selected_articles,
            client,
            model_name,
            system_prompt,
            user_prompt,
            prompt_text,
            report_date,
            search_function,
            model_usage,
            selected_max_iterations,
        )
        registry = generation_result["registry"]
        retrieved_chunk_ids = generation_result["retrieved_chunk_ids"]
        tool_call_log = generation_result["tool_call_log"]
        raw_report_text = generation_result["report_text"]
    elif selected_context_strategy == "react-triage":
        generation_result = generate_triage_report(
            selected_articles,
            client,
            model_name,
            system_prompt,
            user_prompt,
            report_date,
            search_function,
            model_usage,
            selected_max_iterations,
        )
        registry = generation_result["registry"]
        retrieved_chunk_ids = generation_result["retrieved_chunk_ids"]
        tool_call_log = generation_result["tool_call_log"]
        raw_report_text = generation_result["report_text"]
    elif selected_context_strategy == "react-hybrid":
        prompt_text = load_prompt_text("reporting/prompts/triage_scoring.md")
        prompt_files.append("reporting/prompts/triage_scoring.md")
        generation_result = generate_hybrid_report(
            selected_articles,
            client,
            model_name,
            system_prompt,
            user_prompt,
            prompt_text,
            report_date,
            search_function,
            model_usage,
            selected_max_iterations,
        )
        registry = generation_result["registry"]
        retrieved_chunk_ids = generation_result["retrieved_chunk_ids"]
        tool_call_log = generation_result["tool_call_log"]
        raw_report_text = generation_result["report_text"]
    elif selected_context_strategy == "react-progressive":
        prompt_text = load_prompt_text("reporting/prompts/progressive_draft.md")
        prompt_files.append("reporting/prompts/progressive_draft.md")
        generation_result = generate_progressive_report(
            selected_articles,
            client,
            model_name,
            system_prompt,
            user_prompt,
            prompt_text,
            report_date,
            search_function,
            model_usage,
            selected_max_iterations,
        )
        registry = generation_result["registry"]
        retrieved_chunk_ids = generation_result["retrieved_chunk_ids"]
        tool_call_log = generation_result["tool_call_log"]
        raw_report_text = generation_result["report_text"]
    else:
        raise ValueError(
            "Context strategy is unavailable before its implementation task runs: "
            f"{selected_context_strategy}"
        )

    print("[5/6] Finalizing report text and metrics")
    report_text = finalize_report_text(raw_report_text, registry)
    generation_finished_at = datetime.now(timezone.utc)
    model_usage["runtime_seconds"] = (
        generation_finished_at - generation_started_at
    ).total_seconds()
    metrics = extract_report_metrics(
        report_text,
        registry,
        retrieved_chunk_ids,
        window_start=window_start.isoformat(),
        window_end=report_time.isoformat(),
        tool_call_log=tool_call_log,
        model_metrics=model_usage,
    )
    manifest = build_report_manifest(
        recipe_for_manifest,
        selected_context_strategy,
        report_time.isoformat(),
        window_start.isoformat(),
        report_time.isoformat(),
        registry,
        prompt_files,
        retrieved_chunk_ids,
        metrics,
        model_usage,
        candidate_selection=candidate_selection,
        tool_call_log=tool_call_log,
        available_tools=available_tools,
        required_tool_policy=required_tool_policy,
    )

    print("[6/6] Saving report artifacts")
    result = save_report_artifacts(
        output_folder_override or recipe["output_folder"],
        recipe["name"],
        selected_context_strategy,
        report_date,
        report_text,
        manifest,
        artifact_stem=artifact_stem,
    )

    print(f"[INFO] Saved report: {result['report_path']}")
    print(f"[INFO] Saved manifest: {result['manifest_path']}")
    return result


def make_safe_run_folder_name(run_name):
    """
    Make a simple safe folder name from a user-provided run name.
    """
    clean_name = (run_name or "").strip()
    clean_name = clean_name.replace(" ", "_")
    clean_name = clean_name.replace("/", "_")
    clean_name = clean_name.replace("\\", "_")

    if not clean_name:
        raise ValueError("--run-name cannot be empty")

    return clean_name


def build_batch_run_folder_name(recipe_name, report_time, run_name=None):
    """
    Build the folder name for one grouped report batch run.
    """
    if run_name is not None:
        return make_safe_run_folder_name(run_name)

    report_date = report_time.date().isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")
    safe_recipe_name = recipe_name.replace(" ", "_")
    return f"{report_date}_{timestamp}_{safe_recipe_name}"


def build_batch_run_manifest(
    recipe,
    run_name,
    report_time,
    run_folder,
    strategies,
    candidate_selection,
    started_at,
    finished_at,
):
    """
    Build the run-level manifest for a grouped report batch.
    """
    error_count = 0
    for strategy_result in strategies:
        if strategy_result.get("status") != "ok":
            error_count = error_count + 1

    status = "ok"
    if error_count > 0:
        status = "completed_with_errors"

    return {
        "recipe_name": recipe["name"],
        "run_name": run_name,
        "status": status,
        "report_datetime": report_time.isoformat(),
        "run_folder": str(run_folder),
        "knowledge_base_recipe": recipe.get("knowledge_base_recipe", ""),
        "candidate_selection": candidate_selection or {},
        "started_at": started_at,
        "finished_at": finished_at,
        "strategies": strategies,
    }


def run_report_batch(
    recipe_name,
    article_date=None,
    report_datetime=None,
    hours=None,
    knowledge_base_recipe=None,
    max_iterations=None,
    candidate_limit=None,
    run_name=None,
    strategy_delay_seconds=None,
    yes=False,
):
    """
    Run every context-construction strategy into one grouped folder.
    """
    recipe = load_report_recipe(recipe_name)
    report_datetime_value = report_datetime
    if report_datetime_value is None:
        report_datetime_value = article_date
    report_time = parse_report_datetime(report_datetime_value)
    selected_strategy_delay_seconds = strategy_delay_seconds
    if selected_strategy_delay_seconds is None:
        selected_strategy_delay_seconds = 0
    selected_strategy_delay_seconds = normalize_non_negative_integer(
        selected_strategy_delay_seconds,
        "Strategy delay seconds must be zero or greater",
    )
    normalize_candidate_limit_value(recipe, candidate_limit)

    folder_name = build_batch_run_folder_name(recipe["name"], report_time, run_name=run_name)
    output_folder = Path(recipe["output_folder"])
    run_folder = output_folder / folder_name
    if run_folder.exists() and any(run_folder.iterdir()):
        raise ValueError(f"Run folder already exists and is not empty: {run_folder}")

    run_folder.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Running report batch: {recipe['name']}")
    print(f"      Run folder: {run_folder}")
    print(f"      Strategy delay seconds: {selected_strategy_delay_seconds}")
    print("[1/3] Loading clean articles for shared batch candidate pool")
    print(f"      Input: {recipe['input_corpus']}")
    raw_articles = load_clean_articles(recipe["input_corpus"])
    daily_articles = select_articles_for_report_day(
        raw_articles,
        report_time.isoformat(),
    )
    print(f"      Daily articles before candidate selection: {len(daily_articles)}")
    if not daily_articles:
        raise ValueError("No clean articles found inside the report day")

    print("[2/3] Building shared batch candidate pool")
    candidate_pool = prepare_candidate_pool(
        recipe,
        daily_articles,
        candidate_limit=candidate_limit,
    )
    selected_articles = candidate_pool["selected_articles"]
    candidate_selection = candidate_pool["candidate_selection"]
    print(f"      Selected articles for all strategies: {len(selected_articles)}")
    if not selected_articles:
        raise ValueError("No tourism-relevant candidate articles found for report generation")

    started_at = datetime.now(timezone.utc).isoformat()
    strategy_results = []

    for index, strategy_name in enumerate(REPORT_BATCH_STRATEGIES, start=1):
        print(f"[3/3] [{index}/{len(REPORT_BATCH_STRATEGIES)}] Running strategy: {strategy_name}")
        try:
            result = run_report_recipe(
                recipe_name,
                context_strategy=strategy_name,
                article_date=article_date,
                report_datetime=report_datetime,
                hours=hours,
                knowledge_base_recipe=knowledge_base_recipe,
                max_iterations=max_iterations,
                candidate_limit=candidate_limit,
                yes=yes,
                output_folder_override=run_folder,
                artifact_stem=strategy_name,
                precomputed_daily_articles=daily_articles,
                precomputed_selected_articles=selected_articles,
                precomputed_candidate_selection=candidate_selection,
            )
            strategy_results.append({
                "strategy": strategy_name,
                "status": "ok",
                "report_path": str(result["report_path"]),
                "manifest_path": str(result["manifest_path"]),
                "error": "",
            })
        except Exception as error:
            print(f"[ERROR] Strategy failed: {strategy_name}: {error}")
            strategy_results.append({
                "strategy": strategy_name,
                "status": "error",
                "report_path": "",
                "manifest_path": "",
                "error": str(error),
            })

        if selected_strategy_delay_seconds > 0 and index < len(REPORT_BATCH_STRATEGIES):
            print(f"[INFO] Waiting {selected_strategy_delay_seconds}s before next strategy")
            time.sleep(selected_strategy_delay_seconds)

    finished_at = datetime.now(timezone.utc).isoformat()
    manifest = build_batch_run_manifest(
        recipe,
        folder_name,
        report_time,
        run_folder,
        strategy_results,
        candidate_selection,
        started_at,
        finished_at,
    )
    run_manifest_path = run_folder / "run_manifest.json"
    run_manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    evaluation_result = write_report_run_evaluation(run_folder)
    viewer_path = write_report_batch_viewer(run_folder)

    print(f"[INFO] Saved batch manifest: {run_manifest_path}")
    print(f"[INFO] Saved batch evaluation: {evaluation_result['csv_path']}")
    print(f"[INFO] Saved report viewer: {viewer_path}")
    return {
        "run_folder": run_folder,
        "run_manifest_path": run_manifest_path,
        "evaluation_csv_path": evaluation_result["csv_path"],
        "evaluation_json_path": evaluation_result["json_path"],
        "viewer_path": viewer_path,
        "manifest": manifest,
    }
