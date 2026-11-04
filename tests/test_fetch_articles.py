"""
Tests for raw article fetching.

These tests avoid real ScrapingBee calls. They use temporary folders and mocked
network functions so the collector can be changed safely.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from collector.articles import fetch_articles


class FetchArticlesTests(unittest.TestCase):
    def test_create_article_id_is_sha256_of_link(self):
        article_id = fetch_articles.create_article_id("https://example.com/article")

        self.assertEqual(len(article_id), 64)
        self.assertEqual(
            article_id,
            "632538290468e7a39c06323c9e3ae98f31072d641cbb37ea37917f56bbeb5539",
        )

    def test_get_article_output_path_uses_raw_articles_folder(self):
        output_path = fetch_articles.get_article_output_path("abc123")

        self.assertEqual(
            output_path,
            Path("shared_data/corpus/news/raw/articles/abc123.json"),
        )

    def test_load_articles_from_jsonl_skips_blank_lines(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            jsonl_path = Path(temporary_folder) / "links.jsonl"
            jsonl_path.write_text(
                json.dumps({"link": "https://example.com/one", "source": "PUBLICO"})
                + "\n\n"
                + json.dumps({"link": "https://example.com/two", "source": "PUBLICO"})
                + "\n",
                encoding="utf-8",
            )

            articles = fetch_articles.load_articles_from_jsonl(jsonl_path)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["link"], "https://example.com/one")

    def test_find_link_files_only_selected_sources(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            links_dir = Path(temporary_folder)
            (links_dir / "PUBLICO").mkdir()
            (links_dir / "BBC").mkdir()
            publico_file = links_dir / "PUBLICO" / "a.jsonl"
            bbc_file = links_dir / "BBC" / "b.jsonl"
            publico_file.write_text("", encoding="utf-8")
            bbc_file.write_text("", encoding="utf-8")
            selected_sources = [{"name": "PUBLICO"}]

            files = fetch_articles.find_link_files(selected_sources, links_dir)

        self.assertEqual(files, [publico_file])

    def test_build_fetch_queue_dedupes_by_link_and_skips_existing(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            links_dir = base_dir / "links"
            articles_dir = base_dir / "articles"
            (links_dir / "PUBLICO").mkdir(parents=True)
            articles_dir.mkdir()
            link = "https://example.com/article"
            article_id = fetch_articles.create_article_id(link)
            (articles_dir / f"{article_id}.json").write_text("{}", encoding="utf-8")
            jsonl_path = links_dir / "PUBLICO" / "links.jsonl"
            jsonl_path.write_text(
                json.dumps({"link": link, "source": "PUBLICO", "tags": []})
                + "\n"
                + json.dumps({"link": link, "source": "PUBLICO", "tags": []})
                + "\n",
                encoding="utf-8",
            )

            queue, counts = fetch_articles.build_fetch_queue(
                [{"name": "PUBLICO"}],
                links_dir=links_dir,
                articles_dir=articles_dir,
                overwrite_existing=False,
                use_filters=True,
                limit=None,
                per_source=None,
            )

        self.assertEqual(queue, [])
        self.assertEqual(counts["skipped_existing"], 1)
        self.assertEqual(counts["duplicates"], 1)

    def test_build_fetch_queue_overwrite_existing_selects_saved_article(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            links_dir = base_dir / "links"
            articles_dir = base_dir / "articles"
            (links_dir / "PUBLICO").mkdir(parents=True)
            articles_dir.mkdir()
            link = "https://example.com/article"
            article_id = fetch_articles.create_article_id(link)
            (articles_dir / f"{article_id}.json").write_text("{}", encoding="utf-8")
            jsonl_path = links_dir / "PUBLICO" / "links.jsonl"
            jsonl_path.write_text(
                json.dumps({"link": link, "source": "PUBLICO", "tags": []}) + "\n",
                encoding="utf-8",
            )

            queue, counts = fetch_articles.build_fetch_queue(
                [{"name": "PUBLICO"}],
                links_dir=links_dir,
                articles_dir=articles_dir,
                overwrite_existing=True,
                use_filters=True,
                limit=None,
                per_source=None,
            )

        self.assertEqual(len(queue), 1)
        self.assertEqual(counts["skipped_existing"], 0)

    def test_build_fetch_queue_no_filters_keeps_filtered_article(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            base_dir = Path(temporary_folder)
            links_dir = base_dir / "links"
            articles_dir = base_dir / "articles"
            (links_dir / "PUBLICO").mkdir(parents=True)
            articles_dir.mkdir()
            jsonl_path = links_dir / "PUBLICO" / "links.jsonl"
            jsonl_path.write_text(
                json.dumps(
                    {
                        "link": "https://example.com/video/story",
                        "source": "PUBLICO",
                        "tags": [{"term": "video"}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            queue, counts = fetch_articles.build_fetch_queue(
                [{"name": "PUBLICO"}],
                links_dir=links_dir,
                articles_dir=articles_dir,
                overwrite_existing=False,
                use_filters=False,
                limit=None,
                per_source=None,
            )

        self.assertEqual(len(queue), 1)
        self.assertEqual(counts["skipped_filter"], 0)

    def test_should_scrape_filters_global_video_patterns(self):
        article = {
            "source": "PUBLICO",
            "link": "https://example.com/video/story",
            "tags": [{"term": "News"}],
        }

        self.assertFalse(fetch_articles.should_scrape(article))

    def test_should_scrape_filters_expresso_unmapped_tags(self):
        article = {
            "source": "EXPRESSO",
            "link": "https://expresso.pt/article",
            "tags": [{"term": "Blitz"}],
        }

        self.assertFalse(fetch_articles.should_scrape(article))

    def test_should_scrape_keeps_expresso_mapped_tags(self):
        article = {
            "source": "EXPRESSO",
            "link": "https://expresso.pt/article",
            "tags": [{"term": "Governo"}],
        }

        self.assertTrue(fetch_articles.should_scrape(article))

    def test_scrape_article_saves_success_shape_without_real_network(self):
        class FakeResponse:
            ok = True
            status_code = 200
            text = "article markdown"
            headers = {"content-type": "text/plain"}

        with patch("collector.articles.fetch_articles.requests.get") as mocked_get:
            mocked_get.return_value = FakeResponse()

            result = fetch_articles.scrape_article(
                "secret-key",
                "https://example.com/article",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["content"], "article markdown")
        mocked_get.assert_called_once()

    def test_scrape_article_returns_failed_result_on_request_exception(self):
        with patch("collector.articles.fetch_articles.requests.get") as mocked_get:
            mocked_get.side_effect = requests.RequestException("timeout")

            result = fetch_articles.scrape_article(
                "secret-key",
                "https://example.com/article",
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "timeout")

    def test_save_article_writes_json(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            articles_dir = Path(temporary_folder)
            article_data = {
                "id": "abc123",
                "link": "https://example.com/article",
                "source": "PUBLICO",
                "metadata": {"title": "Title"},
                "scraped_at": "2026-05-08T12:00:00+00:00",
                "scrapingbee": {"success": True},
            }

            output_path = fetch_articles.save_article(article_data, articles_dir)

            saved_data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(saved_data["id"], "abc123")
        self.assertEqual(saved_data["scrapingbee"]["success"], True)

    def test_fetch_one_article_saves_failed_scrapingbee_result(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            articles_dir = Path(temporary_folder)
            article = {
                "link": "https://example.com/article",
                "source": "PUBLICO",
                "tags": [],
            }
            article_id = fetch_articles.create_article_id(article["link"])

            with patch("collector.articles.fetch_articles.scrape_article") as mocked_scrape:
                mocked_scrape.return_value = {"success": False, "status_code": 500}
                result = fetch_articles.fetch_one_article(
                    article,
                    article_id,
                    "PUBLICO",
                    "secret-key",
                    articles_dir,
                )

            output_path = articles_dir / f"{article_id}.json"
            saved_data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(saved_data["scrapingbee"]["success"], False)

    def test_fetch_articles_returns_error_when_api_key_missing(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            links_dir = Path(temporary_folder) / "links"
            articles_dir = Path(temporary_folder) / "articles"

            with patch("collector.articles.fetch_articles.get_api_key") as mocked_key:
                mocked_key.return_value = None
                exit_code = fetch_articles.fetch_articles(
                    [{"name": "PUBLICO"}],
                    overwrite_existing=False,
                    workers=1,
                    limit=None,
                    per_source=None,
                    use_filters=True,
                    links_dir=links_dir,
                    articles_dir=articles_dir,
                )

        self.assertEqual(exit_code, 1)

    def test_run_fetching_uses_sequential_path_when_workers_one(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            articles_dir = Path(temporary_folder)
            queue = [
                {
                    "article": {"link": "https://example.com/one"},
                    "article_id": "one",
                    "source": "PUBLICO",
                },
                {
                    "article": {"link": "https://example.com/two"},
                    "article_id": "two",
                    "source": "PUBLICO",
                },
            ]
            calls = []

            def fake_fetch_one_article(article, article_id, source, api_key, articles_dir):
                calls.append(article_id)
                return {
                    "article_id": article_id,
                    "source": source,
                    "status": "SAVED",
                    "output_path": str(articles_dir / f"{article_id}.json"),
                    "error": None,
                }

            with patch("collector.articles.fetch_articles.fetch_one_article", fake_fetch_one_article):
                with patch("collector.articles.fetch_articles.ThreadPoolExecutor") as mocked_executor:
                    results = fetch_articles.run_fetching(
                        queue,
                        "secret-key",
                        articles_dir,
                        workers=1,
                    )

        mocked_executor.assert_not_called()
        self.assertEqual(calls, ["one", "two"])
        self.assertEqual(len(results), 2)

    def test_run_fetching_uses_thread_pool_when_workers_above_one(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            articles_dir = Path(temporary_folder)
            queue = [
                {
                    "article": {"link": "https://example.com/one"},
                    "article_id": "one",
                    "source": "PUBLICO",
                }
            ]

            def fake_fetch_one_article(article, article_id, source, api_key, articles_dir):
                return {
                    "article_id": article_id,
                    "source": source,
                    "status": "SAVED",
                    "output_path": str(articles_dir / f"{article_id}.json"),
                    "error": None,
                }

            with patch("collector.articles.fetch_articles.fetch_one_article", fake_fetch_one_article):
                with patch(
                    "collector.articles.fetch_articles.ThreadPoolExecutor",
                    wraps=fetch_articles.ThreadPoolExecutor,
                ) as mocked_executor:
                    results = fetch_articles.run_fetching(
                        queue,
                        "secret-key",
                        articles_dir,
                        workers=2,
                    )

        mocked_executor.assert_called_once_with(max_workers=2)
        self.assertEqual(results[0]["status"], "SAVED")

    def test_find_failed_articles_selects_only_failed_records(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            articles_dir = Path(temporary_folder)
            failed_path = articles_dir / "failed.json"
            success_path = articles_dir / "success.json"
            failed_path.write_text(
                json.dumps(
                    {
                        "id": "failed",
                        "link": "https://example.com/failed",
                        "source": "PUBLICO",
                        "metadata": {"link": "https://example.com/failed"},
                        "scrapingbee": {"success": False},
                    }
                ),
                encoding="utf-8",
            )
            success_path.write_text(
                json.dumps(
                    {
                        "id": "success",
                        "link": "https://example.com/success",
                        "source": "PUBLICO",
                        "metadata": {"link": "https://example.com/success"},
                        "scrapingbee": {"success": True},
                    }
                ),
                encoding="utf-8",
            )

            failed_articles = fetch_articles.find_failed_articles(
                [{"name": "PUBLICO"}],
                articles_dir,
                limit=None,
                per_source=None,
            )

        self.assertEqual(len(failed_articles), 1)
        self.assertEqual(failed_articles[0]["article_id"], "failed")

    def test_retry_failed_articles_uses_failed_queue(self):
        with tempfile.TemporaryDirectory() as temporary_folder:
            articles_dir = Path(temporary_folder)

            with patch("collector.articles.fetch_articles.get_api_key") as mocked_key:
                mocked_key.return_value = "secret-key"

                with patch("collector.articles.fetch_articles.find_failed_articles") as mocked_find:
                    mocked_find.return_value = [
                        {
                            "article": {
                                "link": "https://example.com/failed",
                                "source": "PUBLICO",
                            },
                            "article_id": "failed",
                            "source": "PUBLICO",
                        }
                    ]

                    with patch("collector.articles.fetch_articles.run_fetching") as mocked_run:
                        mocked_run.return_value = [
                            {
                                "article_id": "failed",
                                "source": "PUBLICO",
                                "status": "SAVED",
                                "output_path": str(articles_dir / "failed.json"),
                                "error": None,
                            }
                        ]

                        exit_code = fetch_articles.retry_failed_articles(
                            [{"name": "PUBLICO"}],
                            workers=1,
                            limit=None,
                            per_source=None,
                            articles_dir=articles_dir,
                        )

        self.assertEqual(exit_code, 0)
        mocked_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
