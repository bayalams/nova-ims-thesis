"""
Tests for corpus inspector HTTP helpers.
"""

import json
import tempfile
import unittest
from pathlib import Path

from explorer.webapps.corpus_inspector.indexer import build_corpus_index
from explorer.webapps.corpus_inspector.server import flatten_query
from explorer.webapps.corpus_inspector.server import guess_content_type
from explorer.webapps.corpus_inspector.server import handle_api_request
from explorer.webapps.corpus_inspector.server import make_static_response
from explorer.webapps.corpus_inspector.server import make_json_response


class CorpusInspectorServerTests(unittest.TestCase):
    def write_json(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def make_index(self):
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name)
        raw_dir = root / "raw"
        clean_dir = root / "clean"
        index_path = root / "index.sqlite"
        raw_dir.mkdir()
        clean_dir.mkdir()
        self.write_json(raw_dir / "one.json", {"id": "one", "source": "BBC", "text": "Useful article text for testing."})
        self.write_json(clean_dir / "one.json", {"id": "one", "source": "BBC", "title": "One", "link": "https://example.com/one", "text": "Useful article text for testing."})
        build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=10)
        return folder, index_path

    def make_encoded_id_index(self):
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name)
        raw_dir = root / "raw"
        clean_dir = root / "clean"
        index_path = root / "index.sqlite"
        raw_dir.mkdir()
        clean_dir.mkdir()
        self.write_json(raw_dir / "safe.json", {"id": "a%2Fb", "source": "BBC", "text": "Useful article text for testing encoded ids."})
        self.write_json(clean_dir / "safe.json", {"id": "a%2Fb", "source": "BBC", "title": "Encoded", "link": "https://example.com/encoded", "text": "Useful article text for testing encoded ids."})
        build_corpus_index(raw_dir=raw_dir, clean_dir=clean_dir, index_path=index_path, minimum_text_characters=10)
        return folder, index_path

    def test_make_json_response_encodes_status_headers_and_body(self):
        status, headers, body = make_json_response({"ok": True}, status=201)

        self.assertEqual(status, 201)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(body.decode("utf-8")), {"ok": True})

    def test_handle_api_request_routes_summary_articles_facets_and_detail(self):
        folder, index_path = self.make_index()
        try:
            summary_status, _, summary_body = handle_api_request("/api/summary", {}, index_path)
            articles_status, _, articles_body = handle_api_request("/api/articles", {"page_size": "10"}, index_path)
            facets_status, _, facets_body = handle_api_request("/api/facets", {}, index_path)
            detail_status, _, detail_body = handle_api_request("/api/articles/one", {}, index_path)
        finally:
            folder.cleanup()

        self.assertEqual(summary_status, 200)
        self.assertEqual(json.loads(summary_body.decode("utf-8"))["total_articles"], 1)
        self.assertEqual(articles_status, 200)
        self.assertEqual(json.loads(articles_body.decode("utf-8"))["total"], 1)
        self.assertEqual(facets_status, 200)
        self.assertIn("sources", json.loads(facets_body.decode("utf-8")))
        self.assertEqual(detail_status, 200)
        self.assertEqual(json.loads(detail_body.decode("utf-8"))["article"]["article_id"], "one")

    def test_handle_api_request_decodes_article_id_once(self):
        folder, index_path = self.make_encoded_id_index()
        try:
            status, _, body = handle_api_request("/api/articles/a%252Fb", {}, index_path)
        finally:
            folder.cleanup()

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["article"]["article_id"], "a%2Fb")

    def test_handle_api_request_returns_errors(self):
        folder, index_path = self.make_index()
        try:
            bad_status, _, bad_body = handle_api_request("/api/articles", {"sort": "bad"}, index_path)
            missing_status, _, missing_body = handle_api_request("/api/articles/missing", {}, index_path)
            unknown_status, _, unknown_body = handle_api_request("/api/nope", {}, index_path)
        finally:
            folder.cleanup()

        self.assertEqual(bad_status, 400)
        self.assertIn("error", json.loads(bad_body.decode("utf-8")))
        self.assertEqual(missing_status, 404)
        self.assertIn("error", json.loads(missing_body.decode("utf-8")))
        self.assertEqual(unknown_status, 404)
        self.assertIn("error", json.loads(unknown_body.decode("utf-8")))

    def test_flatten_query_uses_last_value(self):
        params = flatten_query({"source": ["BBC", "RTP"], "empty": []})

        self.assertEqual(params["source"], "RTP")
        self.assertEqual(params["empty"], "")

    def test_static_response_rejects_traversal_paths(self):
        plain_status, _, plain_body = make_static_response("/../server.py")
        encoded_status, _, encoded_body = make_static_response("/%2e%2e/server.py")

        self.assertEqual(plain_status, 404)
        self.assertEqual(plain_body.decode("utf-8"), "Not found")
        self.assertEqual(encoded_status, 404)
        self.assertEqual(encoded_body.decode("utf-8"), "Not found")

    def test_static_response_ignores_favicon_request(self):
        status, headers, body = make_static_response("/favicon.ico")

        self.assertEqual(status, 204)
        self.assertEqual(headers["Content-Length"], "0")
        self.assertEqual(body, b"")

    def test_guess_content_type_handles_css_and_js(self):
        self.assertEqual(guess_content_type(Path("style.css")), "text/css; charset=utf-8")
        self.assertEqual(guess_content_type(Path("app.js")), "application/javascript; charset=utf-8")

    def test_static_assets_exist(self):
        static_root = Path("explorer/webapps/corpus_inspector/static")

        self.assertTrue((static_root / "index.html").exists())
        self.assertTrue((static_root / "app.js").exists())
        self.assertTrue((static_root / "styles.css").exists())


if __name__ == "__main__":
    unittest.main()
