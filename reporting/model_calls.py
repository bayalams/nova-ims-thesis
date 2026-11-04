"""
Helpers for calling chat models during report generation.
"""

import os
import json


def fill_prompt_variables(prompt_text, variables):
    """
    Replace simple prompt variables in one prompt string.
    """
    filled_text = prompt_text

    for variable_name in variables:
        value = variables[variable_name]
        filled_text = filled_text.replace("{" + variable_name + "}", value)
        filled_text = filled_text.replace("{{" + variable_name + "}}", value)

    return filled_text


def build_openai_chat_messages(system_prompt, user_prompt, context_text, report_date):
    """
    Build the two chat messages for report generation.
    """
    variables = {
        "context_text": context_text,
        "articles_text": context_text,
        "date": report_date,
        "today": report_date,
    }
    filled_system = fill_prompt_variables(system_prompt, variables)
    filled_user = fill_prompt_variables(user_prompt, variables)

    return [
        {"role": "system", "content": filled_system},
        {"role": "user", "content": filled_user},
    ]


def confirm_paid_call(recipe_name, context_strategy, yes=False):
    """
    Confirm before a paid model call.
    """
    if yes:
        return True

    print("[WARNING] Report generation will call the configured LLM.")
    print(f"[INFO] Recipe: {recipe_name}")
    print(f"[INFO] Context strategy: {context_strategy}")
    answer = input("Continue? [y/N] ").strip().lower()
    return answer == "y"


def make_model_usage_tracker():
    """
    Create a simple token and call counter.
    """
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "llm_calls": 0,
    }


def record_model_usage(tracker, model_result):
    """
    Add one model call result to the tracker.
    """
    prompt_tokens = int(model_result.get("prompt_tokens", 0))
    completion_tokens = int(model_result.get("completion_tokens", 0))

    tracker["prompt_tokens"] = tracker["prompt_tokens"] + prompt_tokens
    tracker["completion_tokens"] = tracker["completion_tokens"] + completion_tokens
    tracker["llm_calls"] = tracker["llm_calls"] + 1


def require_openai_api_key():
    """
    Read OPENAI_API_KEY or fail clearly.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Run with: uv run --env-file .env report ...")
    return api_key


def require_model_credentials(recipe):
    """
    Read credentials for the configured report model provider.
    """
    provider = str(recipe.get("model_provider", "openai")).strip() or "openai"

    if provider == "openai":
        return {
            "api_key": require_openai_api_key(),
        }

    if provider == "azure_openai":
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "").strip()
        deployment = str(recipe.get("model_deployment", "")).strip()

        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is missing. Run with: uv run --env-file .env report ...")
        if not azure_endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is missing. Run with: uv run --env-file .env report ...")
        if not api_version:
            raise ValueError("AZURE_OPENAI_API_VERSION is missing. Run with: uv run --env-file .env report ...")
        if not deployment:
            raise ValueError("Recipe is missing model_deployment for azure_openai")

        return {
            "api_key": api_key,
            "azure_endpoint": azure_endpoint,
            "api_version": api_version,
            "model_deployment": deployment,
        }

    raise ValueError(f"Unsupported model provider: {provider}")


def build_openai_client():
    """
    Build an OpenAI client.
    """
    api_key = require_openai_api_key()
    try:
        from openai import OpenAI
    except Exception as error:
        raise ValueError("The openai package is not installed. Run: uv sync") from error

    return OpenAI(api_key=api_key)


def build_model_client(recipe):
    """
    Build the chat model client for one report recipe.
    """
    provider = str(recipe.get("model_provider", "openai")).strip() or "openai"
    credentials = require_model_credentials(recipe)

    try:
        from openai import AzureOpenAI
        from openai import OpenAI
    except Exception as error:
        raise ValueError("The openai package is not installed. Run: uv sync") from error

    if provider == "openai":
        return OpenAI(api_key=credentials["api_key"])

    return AzureOpenAI(
        api_key=credentials["api_key"],
        azure_endpoint=credentials["azure_endpoint"],
        api_version=credentials["api_version"],
    )


def get_chat_request_model(recipe):
    """
    Resolve the model or deployment name used in chat requests.
    """
    provider = str(recipe.get("model_provider", "openai")).strip() or "openai"

    if provider == "azure_openai":
        deployment = str(recipe.get("model_deployment", "")).strip()
        if not deployment:
            raise ValueError("Recipe is missing model_deployment for azure_openai")
        return deployment

    return str(recipe.get("model_name", "gpt-4o-mini")).strip() or "gpt-4o-mini"


def parse_tool_call_arguments(arguments_text):
    """
    Parse one tool-call argument string into a dictionary.
    """
    if not arguments_text:
        return {}

    try:
        parsed = json.loads(arguments_text)
    except Exception:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return parsed


def extract_tool_calls(message):
    """
    Convert OpenAI tool call objects into plain dictionaries.
    """
    tool_calls = []
    raw_tool_calls = getattr(message, "tool_calls", []) or []

    for raw_tool_call in raw_tool_calls:
        function = getattr(raw_tool_call, "function", None)
        if function is None:
            continue

        arguments_text = getattr(function, "arguments", "") or ""
        tool_calls.append({
            "tool_call_id": getattr(raw_tool_call, "id", "") or "",
            "tool_name": getattr(function, "name", "") or "",
            "arguments": parse_tool_call_arguments(arguments_text),
            "arguments_text": arguments_text,
        })

    return tool_calls


def call_chat_model(client, model_name, messages, tools=None):
    """
    Call the chat model and return content plus token metrics.
    """
    if tools is None:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
    else:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
        )

    choices = getattr(response, "choices", []) or []
    if not choices:
        raise ValueError("Model returned no choices")

    message = choices[0].message
    content = getattr(message, "content", "") or ""
    tool_calls = extract_tool_calls(message)
    if not content.strip() and not tool_calls:
        raise ValueError("Model returned an empty report")

    usage = getattr(response, "usage", None)
    prompt_tokens = 0
    completion_tokens = 0
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

    return {
        "content": content,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tool_calls": tool_calls,
    }
