"""
Tests for OpenAI embedding helper functions.
"""

import os
import unittest
from unittest.mock import patch

from knowledge_bases.embedding.openai_embeddings import build_embedding_client
from knowledge_bases.embedding.openai_embeddings import create_embedding_batch
from knowledge_bases.embedding.openai_embeddings import estimate_embedding_cost
from knowledge_bases.embedding.openai_embeddings import estimate_input_tokens
from knowledge_bases.embedding.openai_embeddings import get_safe_embedding_token_limit
from knowledge_bases.embedding.openai_embeddings import mask_api_key
from knowledge_bases.embedding.openai_embeddings import require_embedding_credentials
from knowledge_bases.embedding.openai_embeddings import require_openai_api_key
from knowledge_bases.embedding.openai_embeddings import text_is_too_large_for_embedding


class FakeUsage:
    total_tokens = 12


class FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(self):
        self.data = [
            FakeEmbeddingItem([0.1, 0.2]),
            FakeEmbeddingItem([0.3, 0.4]),
        ]
        self.usage = FakeUsage()


class FakeEmbeddings:
    def __init__(self):
        self.last_model = None
        self.last_input = None

    def create(self, model, input):
        self.last_model = model
        self.last_input = input
        return FakeEmbeddingResponse()


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()


def make_openai_recipe():
    return {
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
    }


def make_azure_recipe():
    return {
        "embedding_provider": "azure_openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_deployment": "azure-embed-small",
    }


class KnowledgeBaseEmbeddingTests(unittest.TestCase):
    def test_create_embedding_batch_uses_client_and_returns_vectors(self):
        client = FakeClient()

        result = create_embedding_batch(client, ["a", "b"], "text-embedding-3-small")

        self.assertEqual(client.embeddings.last_model, "text-embedding-3-small")
        self.assertEqual(client.embeddings.last_input, ["a", "b"])
        self.assertEqual(result["vectors"], [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(result["token_count"], 12)

    def test_create_embedding_batch_handles_empty_text_list(self):
        client = FakeClient()

        result = create_embedding_batch(client, [], "text-embedding-3-small")

        self.assertEqual(result["vectors"], [])
        self.assertEqual(result["token_count"], 0)

    def test_mask_api_key_hides_secret(self):
        self.assertEqual(mask_api_key("sk-1234567890"), "sk-12345...")

    def test_require_openai_api_key_reads_environment(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            self.assertEqual(require_openai_api_key(), "sk-test")

    def test_require_openai_api_key_fails_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                require_openai_api_key()

    def test_require_embedding_credentials_reads_openai_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            credentials = require_embedding_credentials(make_openai_recipe())

        self.assertEqual(credentials["api_key"], "sk-test")

    def test_require_embedding_credentials_reads_azure_fields(self):
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "azure-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_API_VERSION": "2024-02-01",
            },
            clear=True,
        ):
            credentials = require_embedding_credentials(make_azure_recipe())

        self.assertEqual(credentials["api_key"], "azure-key")
        self.assertEqual(credentials["azure_endpoint"], "https://example.openai.azure.com")
        self.assertEqual(credentials["api_version"], "2024-02-01")

    def test_require_embedding_credentials_rejects_missing_azure_deployment(self):
        recipe = make_azure_recipe()
        recipe["embedding_deployment"] = ""

        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "azure-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_API_VERSION": "2024-02-01",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "embedding_deployment"):
                require_embedding_credentials(recipe)

    def test_build_embedding_client_uses_azure_client_with_endpoint_and_version(self):
        azure_recipe = make_azure_recipe()

        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "azure-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_API_VERSION": "2024-02-01",
            },
            clear=True,
        ):
            with patch("openai.AzureOpenAI") as fake_azure_openai:
                build_embedding_client(azure_recipe)

        fake_azure_openai.assert_called_once_with(
            api_key="azure-key",
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-02-01",
        )

    def test_create_embedding_batch_uses_azure_deployment_name(self):
        client = FakeClient()
        azure_recipe = make_azure_recipe()

        result = create_embedding_batch(client, ["a", "b"], azure_recipe)

        self.assertEqual(client.embeddings.last_model, "azure-embed-small")
        self.assertEqual(client.embeddings.last_input, ["a", "b"])
        self.assertEqual(result["vectors"], [[0.1, 0.2], [0.3, 0.4]])

    def test_estimate_embedding_cost_uses_known_model_rate(self):
        self.assertEqual(estimate_embedding_cost("text-embedding-3-small", 1_000_000), 0.0184)

    def test_estimate_input_tokens_uses_simple_character_rule(self):
        self.assertEqual(estimate_input_tokens("abcd" * 10), 10)

    def test_text_is_too_large_for_embedding_uses_safe_limit(self):
        safe_limit = get_safe_embedding_token_limit("text-embedding-3-small")
        oversized_text = "abcd" * (safe_limit + 1)

        self.assertTrue(text_is_too_large_for_embedding(oversized_text, "text-embedding-3-small"))
        self.assertFalse(text_is_too_large_for_embedding("short text", "text-embedding-3-small"))


if __name__ == "__main__":
    unittest.main()
