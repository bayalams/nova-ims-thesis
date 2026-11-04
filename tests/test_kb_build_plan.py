"""
Tests for knowledge-base build planning.
"""

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_bases.build_knowledge_base import build_pending_article_plans
from knowledge_bases.build_knowledge_base import embed_one_job_batch
from knowledge_bases.build_knowledge_base import create_backoff_state
from knowledge_bases.build_knowledge_base import filter_articles_for_build
from knowledge_bases.build_knowledge_base import make_article_record
from knowledge_bases.build_knowledge_base import make_article_filter_options
from knowledge_bases.build_knowledge_base import make_embedding_batches
from knowledge_bases.build_knowledge_base import make_embedding_jobs
from knowledge_bases.build_knowledge_base import make_manifest
from knowledge_bases.build_knowledge_base import parse_timestamp_to_epoch
from knowledge_bases.build_knowledge_base import run_prepared_build_plan
from knowledge_bases.build_knowledge_base import validate_recipe
from knowledge_bases.build_knowledge_base import write_embedding_skip_report
from knowledge_bases.embedding.openai_embeddings import get_safe_embedding_token_limit
from knowledge_bases.storage.sqlite_kb import create_kb_schema


def make_test_recipe():
    """
    Create a minimal no-chunking recipe for build-plan tests.

    PARAMETERS:
    - None

    RETURNS:
    - Recipe dictionary
    """
    return {
        "name": "test_no_chunking",
        "enabled": True,
        "input_corpus": "unused",
        "output_folder": "unused",
        "chunking_method": "none",
        "chunk_size_characters": 0,
        "chunk_overlap_characters": 0,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": None,
        "vector_backend": "sqlite_vec1",
        "search_distance": "cos",
    }


class KnowledgeBaseBuildPlanTests(unittest.TestCase):
    def test_validate_recipe_accepts_azure_openai_with_deployment(self):
        recipe = make_test_recipe()
        recipe["embedding_provider"] = "azure_openai"
        recipe["embedding_deployment"] = "azure-embed-small"

        validate_recipe(recipe)

    def test_validate_recipe_rejects_azure_openai_without_deployment(self):
        recipe = make_test_recipe()
        recipe["embedding_provider"] = "azure_openai"
        recipe.pop("embedding_deployment", None)

        with self.assertRaisesRegex(ValueError, "embedding_deployment"):
            validate_recipe(recipe)

    def test_parse_timestamp_handles_rss_iso_and_collector_filename(self):
        rss_epoch = parse_timestamp_to_epoch("Fri, 27 Feb 2026 04:30:01 GMT")
        iso_epoch = parse_timestamp_to_epoch("2026-02-27T04:30:01+00:00")
        filename_epoch = parse_timestamp_to_epoch("20260227_043001")

        self.assertEqual(rss_epoch, iso_epoch)
        self.assertEqual(filename_epoch, iso_epoch)

    def test_article_filter_options_only_keep_sampling_options(self):
        options = make_article_filter_options(
            sample_articles=3,
            random_seed=7,
        )

        self.assertEqual(options["sample_articles"], 3)
        self.assertEqual(options["random_seed"], 7)
        self.assertNotIn("published_before", options)
        self.assertNotIn("indexed_before", options)

    def test_article_filters_do_not_apply_timestamp_cutoffs_at_build_time(self):
        articles = [
            make_filter_test_article("old", "Fri, 01 May 2026 10:00:00 GMT", "2026-05-01T12:00:00+00:00"),
            make_filter_test_article("new", "Fri, 03 May 2026 10:00:00 GMT", "2026-05-03T12:00:00+00:00"),
            make_filter_test_article("missing", "", ""),
        ]
        options = make_article_filter_options(
            sample_articles=None,
            random_seed=None,
        )

        result = filter_articles_for_build(articles, options)

        self.assertEqual([article["id"] for article in result["articles"]], ["old", "new", "missing"])
        self.assertNotIn("skipped_after_published_cutoff", result)
        self.assertNotIn("skipped_after_indexed_cutoff", result)

    def test_article_filters_apply_reproducible_sample(self):
        articles = []
        for position in range(10):
            articles.append(
                make_filter_test_article(
                    f"article-{position}",
                    "Fri, 01 May 2026 10:00:00 GMT",
                    "2026-05-01T12:00:00+00:00",
                )
            )

        options = make_article_filter_options(
            sample_articles=3,
            random_seed=7,
        )

        first_result = filter_articles_for_build(articles, options)
        second_result = filter_articles_for_build(articles, options)

        first_ids = [article["id"] for article in first_result["articles"]]
        second_ids = [article["id"] for article in second_result["articles"]]
        self.assertEqual(len(first_ids), 3)
        self.assertEqual(first_ids, second_ids)

    def test_sample_filter_defaults_to_stable_seed(self):
        options = make_article_filter_options(
            sample_articles=5,
            random_seed=None,
        )

        self.assertEqual(options["random_seed"], 42)

    def test_manifest_uses_sample_filter_summary_without_timestamp_cutoff_keys(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        create_kb_schema(connection)
        connection.execute("CREATE TABLE vec1_chunks (rowid INTEGER PRIMARY KEY, vector BLOB)")
        recipe = make_test_recipe()
        build_plan = {
            "articles_loaded": 10,
            "article_filter_options": {
                "sample_articles": 3,
                "random_seed": 42,
            },
            "article_filter_summary": {
                "before_sample_count": 10,
                "after_filter_count": 3,
                "sample_applied": True,
            },
            "new_articles": 0,
            "changed_articles": 0,
            "skipped_unchanged": 0,
            "skipped_too_large": 0,
            "vec1_extension_path": "test_vec1",
        }

        manifest = make_manifest(
            recipe,
            build_plan,
            connection,
            token_count=0,
            vectors_written=0,
            index_status="empty",
            start_time=time.time(),
        )
        connection.close()

        self.assertEqual(manifest["article_filter_options"]["sample_articles"], 3)
        self.assertEqual(manifest["articles_before_random_sample"], 10)
        self.assertEqual(manifest["articles_after_filters"], 3)
        self.assertNotIn("skipped_after_published_cutoff", manifest)
        self.assertNotIn("skipped_after_indexed_cutoff", manifest)

    def test_make_article_record_includes_indexed_timestamp_fields(self):
        article = make_filter_test_article(
            "article-one",
            "Fri, 01 May 2026 10:00:00 GMT",
            "2026-05-01T12:00:00+00:00",
        )

        record = make_article_record(article)

        self.assertEqual(record["indexed_at"], "2026-05-01T12:00:00+00:00")
        self.assertEqual(record["indexed_at_epoch"], parse_timestamp_to_epoch("2026-05-01T12:00:00+00:00"))

    def test_make_article_record_uses_empty_indexed_fields_when_missing_or_invalid(self):
        missing_article = make_filter_test_article("missing", "", "")
        invalid_article = make_filter_test_article("invalid", "", "not a timestamp")

        missing_record = make_article_record(missing_article)
        invalid_record = make_article_record(invalid_article)

        self.assertEqual(missing_record["indexed_at"], "")
        self.assertIsNone(missing_record["indexed_at_epoch"])
        self.assertEqual(invalid_record["indexed_at"], "")
        self.assertIsNone(invalid_record["indexed_at_epoch"])

    def test_oversized_no_chunking_article_is_skipped_before_embedding(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        create_kb_schema(connection)
        recipe = make_test_recipe()
        safe_limit = get_safe_embedding_token_limit(recipe["embedding_model"])
        oversized_text = "abcd" * (safe_limit + 1)

        articles = [
            {
                "id": "article-one",
                "source": "PUBLICO",
                "title": "Long article",
                "link": "https://example.com/long",
                "text": oversized_text,
                "metadata": {},
            }
        ]

        result = build_pending_article_plans(recipe, connection, articles)

        self.assertEqual(result["pending_plans"], [])
        self.assertEqual(result["skipped_too_large"], 1)
        self.assertEqual(result["skipped_too_large_records"][0]["article_id"], "article-one")
        self.assertEqual(result["skipped_too_large_records"][0]["chunking_method"], "none")

    def test_skip_report_writes_jsonl_records(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            report_path = write_embedding_skip_report(
                temporary_folder,
                [{"article_id": "article-one", "reason": "too large"}],
            )
            report_text = report_path.read_text(encoding="utf-8")

        self.assertIn('"article_id": "article-one"', report_text)
        self.assertIn('"reason": "too large"', report_text)

    def test_embedding_batches_respect_token_limit(self):
        jobs = [
            {"chunk_id": "one", "text": "a" * 80},
            {"chunk_id": "two", "text": "b" * 80},
            {"chunk_id": "three", "text": "c" * 80},
        ]

        batches = make_embedding_batches(jobs, batch_size=10, max_batch_tokens=40)

        self.assertEqual(len(batches), 2)
        self.assertEqual([job["chunk_id"] for job in batches[0]], ["one", "two"])
        self.assertEqual([job["chunk_id"] for job in batches[1]], ["three"])

    def test_embedding_batch_retries_rate_limit_once(self):
        client = FakeRateLimitClient()
        jobs = [{"chunk_id": "one", "text": "short text"}]

        with patch("knowledge_bases.build_knowledge_base.time.sleep") as fake_sleep:
            result = embed_one_job_batch(
                client,
                "text-embedding-3-small",
                jobs,
                batch_number=1,
                max_retries=2,
                backoff_state=create_backoff_state(),
            )

        self.assertEqual(client.embeddings.call_count, 2)
        self.assertEqual(fake_sleep.call_count, 1)
        self.assertEqual(result["vectors"], [[0.1, 0.2]])

    def test_rate_limit_backoff_waits_before_next_request(self):
        client = FakeClient()
        jobs = [{"chunk_id": "one", "text": "short text"}]
        backoff_state = create_backoff_state()
        backoff_state["blocked_until"] = time.time() + 5.0

        with patch("knowledge_bases.build_knowledge_base.time.sleep") as fake_sleep:
            result = embed_one_job_batch(
                client,
                "text-embedding-3-small",
                jobs,
                batch_number=1,
                max_retries=2,
                backoff_state=backoff_state,
            )

        self.assertEqual(fake_sleep.call_count, 1)
        self.assertEqual(result["vectors"], [[0.1, 0.2]])

    def test_prepared_build_writes_each_embedding_batch_before_next_request(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = f"{temporary_folder}/kb.sqlite"
            recipe = make_test_recipe()
            recipe["output_folder"] = temporary_folder
            pending_plans = [
                make_test_pending_plan("article-one", "chunk one"),
                make_test_pending_plan("article-two", "chunk two"),
            ]
            build_plan = {
                "recipe": recipe,
                "db_path": db_path,
                "vec1_extension_path": "test_vec1",
                "articles_loaded": 2,
                "article_filter_options": make_article_filter_options(None, None),
                "article_filter_summary": {
                    "before_sample_count": 2,
                    "after_filter_count": 2,
                    "sample_applied": False,
                },
                "pending_plans": pending_plans,
                "embedding_jobs": make_embedding_jobs(pending_plans),
                "new_articles": 2,
                "changed_articles": 0,
                "skipped_unchanged": 0,
                "skipped_too_large": 0,
                "skipped_too_large_records": [],
            }
            client = InspectingStreamingClient(db_path)

            with patch("knowledge_bases.build_knowledge_base.load_vec1_extension"), \
                 patch("knowledge_bases.build_knowledge_base.create_vec1_table", create_test_vec1_table), \
                 patch("knowledge_bases.build_knowledge_base.rebuild_vec1_index", return_value="test_index"):
                run_prepared_build_plan(
                    build_plan,
                    client,
                    workers=1,
                    embedding_batch_size=1,
                    embedding_max_batch_tokens=1000,
                    embedding_request_delay_seconds=0,
                    embedding_max_retries=0,
                )

            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            chunk_count = connection.execute("SELECT count(*) AS count FROM chunks").fetchone()["count"]
            ready_count = connection.execute(
                "SELECT count(*) AS count FROM articles WHERE status = 'ready'"
            ).fetchone()["count"]
            batch_count = connection.execute("SELECT count(*) AS count FROM embedding_batches").fetchone()["count"]
            connection.close()

        self.assertEqual(client.embeddings.call_count, 2)
        self.assertEqual(chunk_count, 2)
        self.assertEqual(ready_count, 2)
        self.assertEqual(batch_count, 2)

    def test_prepared_build_skips_runtime_oversized_input_and_embeds_remaining_articles(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            db_path = f"{temporary_folder}/kb.sqlite"
            recipe = make_test_recipe()
            recipe["output_folder"] = temporary_folder
            pending_plans = [
                make_test_pending_plan("article-one", "chunk one"),
                make_test_pending_plan("article-two", "bad chunk"),
                make_test_pending_plan("article-three", "chunk three"),
            ]
            build_plan = {
                "recipe": recipe,
                "db_path": db_path,
                "vec1_extension_path": "test_vec1",
                "articles_loaded": 3,
                "article_filter_options": make_article_filter_options(None, None),
                "article_filter_summary": {
                    "before_sample_count": 3,
                    "after_filter_count": 3,
                    "sample_applied": False,
                },
                "pending_plans": pending_plans,
                "embedding_jobs": make_embedding_jobs(pending_plans),
                "new_articles": 3,
                "changed_articles": 0,
                "skipped_unchanged": 0,
                "skipped_too_large": 0,
                "skipped_too_large_records": [],
            }
            client = RuntimeOversizedInputClient()

            with patch("knowledge_bases.build_knowledge_base.load_vec1_extension"), \
                 patch("knowledge_bases.build_knowledge_base.create_vec1_table", create_test_vec1_table), \
                 patch("knowledge_bases.build_knowledge_base.rebuild_vec1_index", return_value="test_index"):
                run_prepared_build_plan(
                    build_plan,
                    client,
                    workers=1,
                    embedding_batch_size=3,
                    embedding_max_batch_tokens=1000,
                    embedding_request_delay_seconds=0,
                    embedding_max_retries=0,
                )

            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            chunk_count = connection.execute("SELECT count(*) AS count FROM chunks").fetchone()["count"]
            ready_ids = connection.execute(
                "SELECT article_id FROM articles WHERE status = 'ready' ORDER BY article_id"
            ).fetchall()
            skipped_row = connection.execute(
                "SELECT article_id FROM articles WHERE article_id = 'article-two'"
            ).fetchone()
            connection.close()

            skip_report_text = (Path(temporary_folder) / "embedding_skipped_articles.jsonl").read_text(encoding="utf-8")
            manifest = json.loads((Path(temporary_folder) / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(client.embeddings.call_count, 2)
        self.assertEqual(client.embeddings.second_input, ["chunk one", "chunk three"])
        self.assertEqual(chunk_count, 2)
        self.assertEqual([row["article_id"] for row in ready_ids], ["article-one", "article-three"])
        self.assertIsNone(skipped_row)
        self.assertIn('"article_id": "article-two"', skip_report_text)
        self.assertEqual(manifest["skipped_too_large_article_count"], 1)


class FakeUsage:
    total_tokens = 2


class FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(self):
        self.data = [FakeEmbeddingItem([0.1, 0.2])]
        self.usage = FakeUsage()


class FakeEmbeddingsWithRateLimit:
    def __init__(self):
        self.call_count = 0

    def create(self, model, input):
        self.call_count = self.call_count + 1

        if self.call_count == 1:
            raise RuntimeError("Rate limit reached. Please try again in 1.17s.")

        return FakeEmbeddingResponse()


class FakeRateLimitClient:
    def __init__(self):
        self.embeddings = FakeEmbeddingsWithRateLimit()


class FakeEmbeddings:
    def create(self, model, input):
        return FakeEmbeddingResponse()


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()


class InspectingEmbeddingResponse:
    def __init__(self, text_count):
        self.data = []

        for position in range(text_count):
            self.data.append(FakeEmbeddingItem([float(position), float(position + 1)]))

        self.usage = FakeUsage()


class InspectingStreamingEmbeddings:
    def __init__(self, db_path):
        self.db_path = db_path
        self.call_count = 0

    def create(self, model, input):
        self.call_count = self.call_count + 1

        if self.call_count == 2:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT count(*) AS count FROM chunks").fetchone()
            connection.close()
            if row["count"] != 1:
                raise AssertionError("first embedding batch was not written before the next request")

        return InspectingEmbeddingResponse(len(input))


class InspectingStreamingClient:
    def __init__(self, db_path):
        self.embeddings = InspectingStreamingEmbeddings(db_path)


class RuntimeOversizedInputEmbeddings:
    def __init__(self):
        self.call_count = 0
        self.second_input = []

    def create(self, model, input):
        self.call_count = self.call_count + 1

        if self.call_count == 1:
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': "
                "\"Invalid 'input[1]': maximum input length is 8192 tokens.\"}}"
            )

        self.second_input = list(input)
        return InspectingEmbeddingResponse(len(input))


class RuntimeOversizedInputClient:
    def __init__(self):
        self.embeddings = RuntimeOversizedInputEmbeddings()


def create_test_vec1_table(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS vec1_chunks(rowid INTEGER PRIMARY KEY, vector BLOB)")
    connection.commit()


def make_test_pending_plan(article_id, chunk_text):
    article = make_filter_test_article(
        article_id,
        "Fri, 01 May 2026 10:00:00 GMT",
        "2026-05-01T12:00:00+00:00",
    )
    article_record = make_article_record(article)
    article_record["status"] = "ready"

    return {
        "article_record": article_record,
        "chunk_records": [
            {
                "chunk_id": f"{article_id}_chunk_0",
                "article_id": article_id,
                "chunk_index": 0,
                "chunk_text": chunk_text,
                "character_start": 0,
                "character_end": len(chunk_text),
                "chunk_hash": f"{article_id}-hash",
            }
        ],
        "skip_record": None,
    }


def make_filter_test_article(article_id, published, indexed_at):
    """
    Create a clean article dictionary for filter tests.

    PARAMETERS:
    - article_id: Stable article id
    - published: Published timestamp text
    - indexed_at: RSS indexed timestamp text

    RETURNS:
    - Clean article dictionary
    """
    return {
        "id": article_id,
        "source": "PUBLICO",
        "title": article_id,
        "link": f"https://example.com/{article_id}",
        "text": "Clean article text",
        "metadata": {
            "published": published,
            "indexed_at": indexed_at,
        },
    }


if __name__ == "__main__":
    unittest.main()
