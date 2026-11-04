"""
OpenAI embedding helpers for knowledge-base builds.

This module keeps OpenAI-specific code in one place so the rest of the KB
builder can work with simple lists of text and vectors.
"""

import os


EMBEDDING_PRICING_EUR_PER_1M_TOKENS = {
    "text-embedding-3-small": 0.0184,
    "text-embedding-3-large": 0.1196,
}

OPENAI_EMBEDDING_MAX_INPUT_TOKENS = {
    "text-embedding-3-small": 8192,
    "text-embedding-3-large": 8192,
}

# Keep a large safety margin so OpenAI does not reject an entire batch because
# one no-chunking article is too long.
OPENAI_EMBEDDING_SAFETY_MARGIN_TOKENS = 2000


def mask_api_key(api_key):
    """
    Return a short masked API key for logs.

    PARAMETERS:
    - api_key: The API key string

    RETURNS:
    - A masked string that is safe to print
    """
    if not api_key:
        return "<missing>"

    return f"{api_key[:8]}..."


def require_openai_api_key():
    """
    Read OPENAI_API_KEY and fail clearly if it is missing.

    PARAMETERS:
    - None

    RETURNS:
    - The OpenAI API key string

    RAISES:
    - ValueError when OPENAI_API_KEY is missing
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Run with: uv run --env-file .env build-kb ...")

    return api_key


def require_embedding_credentials(recipe):
    """
    Read credentials for the embedding provider selected by one recipe.

    PARAMETERS:
    - recipe: Recipe dictionary

    RETURNS:
    - A dictionary with the credentials needed for that provider
    """
    provider = str(recipe.get("embedding_provider", "")).strip()

    if provider == "openai":
        return {
            "api_key": require_openai_api_key(),
        }

    if provider == "azure_openai":
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "").strip()
        deployment = str(recipe.get("embedding_deployment", "")).strip()

        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is missing. Run with: uv run --env-file .env build-kb ...")

        if not azure_endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is missing. Run with: uv run --env-file .env build-kb ...")

        if not api_version:
            raise ValueError("AZURE_OPENAI_API_VERSION is missing. Run with: uv run --env-file .env build-kb ...")

        if not deployment:
            raise ValueError("Recipe is missing embedding_deployment for azure_openai")

        return {
            "api_key": api_key,
            "azure_endpoint": azure_endpoint,
            "api_version": api_version,
            "embedding_deployment": deployment,
        }

    raise ValueError(f"Unsupported embedding provider: {provider}")


def build_openai_client():
    """
    Build an OpenAI client from environment variables.

    PARAMETERS:
    - None

    RETURNS:
    - An OpenAI client object
    """
    api_key = require_openai_api_key()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()

    try:
        from openai import OpenAI
    except Exception as error:
        raise ValueError("The openai package is not installed. Run: uv sync") from error

    print("[INFO] OpenAI embedding provider selected")
    print(f"[INFO] OpenAI API key prefix: {mask_api_key(api_key)}")

    if base_url:
        print(f"[INFO] OpenAI base URL: {base_url}")
        return OpenAI(api_key=api_key, base_url=base_url)

    print("[INFO] OpenAI base URL: https://api.openai.com/v1")
    return OpenAI(api_key=api_key)


def build_embedding_client(recipe):
    """
    Build the embedding client for one recipe.

    PARAMETERS:
    - recipe: Recipe dictionary

    RETURNS:
    - An OpenAI-compatible client object
    """
    provider = str(recipe.get("embedding_provider", "")).strip()
    credentials = require_embedding_credentials(recipe)

    try:
        from openai import AzureOpenAI
        from openai import OpenAI
    except Exception as error:
        raise ValueError("The openai package is not installed. Run: uv sync") from error

    if provider == "openai":
        api_key = credentials["api_key"]
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip()

        print("[INFO] OpenAI embedding provider selected")
        print(f"[INFO] OpenAI API key prefix: {mask_api_key(api_key)}")

        if base_url:
            print(f"[INFO] OpenAI base URL: {base_url}")
            return OpenAI(api_key=api_key, base_url=base_url)

        print("[INFO] OpenAI base URL: https://api.openai.com/v1")
        return OpenAI(api_key=api_key)

    print("[INFO] Azure OpenAI embedding provider selected")
    print(f"[INFO] Azure OpenAI API key prefix: {mask_api_key(credentials['api_key'])}")
    print(f"[INFO] Azure OpenAI endpoint: {credentials['azure_endpoint']}")
    print(f"[INFO] Azure OpenAI API version: {credentials['api_version']}")

    return AzureOpenAI(
        api_key=credentials["api_key"],
        azure_endpoint=credentials["azure_endpoint"],
        api_version=credentials["api_version"],
    )


def get_embedding_request_model(recipe_or_model):
    """
    Resolve the model or deployment name used in the embeddings API call.

    PARAMETERS:
    - recipe_or_model: Recipe dictionary or model string

    RETURNS:
    - Model or deployment name string
    """
    if isinstance(recipe_or_model, dict):
        provider = str(recipe_or_model.get("embedding_provider", "")).strip()

        if provider == "azure_openai":
            deployment = str(recipe_or_model.get("embedding_deployment", "")).strip()
            if not deployment:
                raise ValueError("Recipe is missing embedding_deployment for azure_openai")
            return deployment

        return str(recipe_or_model.get("embedding_model", "")).strip()

    return str(recipe_or_model).strip()


def create_embedding_batch(client, texts, recipe_or_model):
    """
    Create embeddings for a batch of text strings.

    PARAMETERS:
    - client: OpenAI or Azure OpenAI client or fake test client
    - texts: A list of strings to embed
    - recipe_or_model: Recipe dictionary or embedding model name

    RETURNS:
    - A dictionary with vectors and token count
    """
    if not texts:
        return {
            "vectors": [],
            "token_count": 0,
        }

    model = get_embedding_request_model(recipe_or_model)
    print(f"[INFO] Embedding batch with {len(texts)} texts using {model}")

    response = client.embeddings.create(
        model=model,
        input=texts,
    )

    vectors = []
    for item in response.data:
        vectors.append(item.embedding)

    if len(vectors) != len(texts):
        raise ValueError(f"Returned {len(vectors)} vectors for {len(texts)} texts")

    token_count = 0
    if getattr(response, "usage", None) is not None:
        token_count = getattr(response.usage, "total_tokens", 0) or 0

    return {
        "vectors": vectors,
        "token_count": token_count,
    }


def estimate_input_tokens(text):
    """
    Estimate tokens for one text before calling OpenAI.

    PARAMETERS:
    - text: The text that would be embedded

    RETURNS:
    - Rough token estimate
    """
    character_count = len(text)
    estimated_tokens = int(character_count / 4)

    if character_count > 0 and estimated_tokens == 0:
        return 1

    return estimated_tokens


def get_safe_embedding_token_limit(model):
    """
    Return the safe estimated-token limit for an embedding model.

    PARAMETERS:
    - model: OpenAI embedding model name

    RETURNS:
    - Token limit with a safety margin subtracted
    """
    maximum_tokens = OPENAI_EMBEDDING_MAX_INPUT_TOKENS.get(model, 8192)
    safe_limit = maximum_tokens - OPENAI_EMBEDDING_SAFETY_MARGIN_TOKENS

    if safe_limit < 1:
        return maximum_tokens

    return safe_limit


def text_is_too_large_for_embedding(text, model):
    """
    Check whether a text is likely too large for one OpenAI embedding input.

    PARAMETERS:
    - text: Text to check
    - model: OpenAI embedding model name

    RETURNS:
    - True if the estimated token count is above the safe limit
    """
    estimated_tokens = estimate_input_tokens(text)
    safe_limit = get_safe_embedding_token_limit(model)
    return estimated_tokens > safe_limit


def estimate_embedding_cost(model, token_count):
    """
    Estimate embedding cost in EUR.

    PARAMETERS:
    - model: OpenAI embedding model name
    - token_count: Number of input tokens

    RETURNS:
    - Estimated cost in EUR
    """
    rate = EMBEDDING_PRICING_EUR_PER_1M_TOKENS.get(model, 0.0)
    cost = (token_count / 1_000_000) * rate
    return round(cost, 6)
