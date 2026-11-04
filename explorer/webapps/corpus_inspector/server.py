"""
Local HTTP server for the corpus inspector.
"""

import json
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlparse

from explorer.webapps.corpus_inspector.indexer import DEFAULT_INDEX_PATH
from explorer.webapps.corpus_inspector.queries import get_article_detail
from explorer.webapps.corpus_inspector.queries import get_article_page
from explorer.webapps.corpus_inspector.queries import get_facets
from explorer.webapps.corpus_inspector.queries import get_summary


STATIC_DIR = Path(__file__).parent / "static"


def make_json_response(data, status=200):
    """
    Return a response tuple for a JSON payload.
    """
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    return status, headers, body


def flatten_query(query_values):
    """
    Convert parse_qs values into a plain dictionary.
    """
    params = {}

    for key in query_values:
        values = query_values[key]
        if len(values) > 0:
            params[key] = values[-1]
        else:
            params[key] = ""

    return params


def handle_api_request(path, params, index_path):
    """
    Route one API request to the corpus inspector query helpers.
    """
    try:
        if path == "/api/summary":
            return make_json_response(get_summary(index_path))

        if path == "/api/facets":
            return make_json_response(get_facets(index_path, params))

        if path == "/api/articles":
            return make_json_response(get_article_page(index_path, params))

        if path.startswith("/api/articles/"):
            article_id = path[len("/api/articles/"):]
            return make_json_response(get_article_detail(index_path, article_id))

        return make_json_response({"error": "Unknown API path"}, status=404)
    except ValueError as error:
        return make_json_response({"error": str(error)}, status=400)
    except KeyError:
        return make_json_response({"error": "Article not found"}, status=404)
    except Exception as error:
        return make_json_response({"error": str(error)}, status=500)


def guess_content_type(path):
    """
    Guess a simple content type for static files.
    """
    suffix = Path(path).suffix.lower()

    if suffix == ".html":
        return "text/html; charset=utf-8"

    if suffix == ".css":
        return "text/css; charset=utf-8"

    if suffix == ".js":
        return "application/javascript; charset=utf-8"

    return "application/octet-stream"


def make_plain_response(message, status=404):
    """
    Return a response tuple for a plain text payload.
    """
    body = message.encode("utf-8")
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    return status, headers, body


def make_empty_response(status=204):
    """
    Return an empty response for browser requests that do not need a body.
    """
    headers = {
        "Content-Length": "0",
    }
    return status, headers, b""


def send_response_tuple(handler, response):
    """
    Send a response tuple through a BaseHTTPRequestHandler instance.
    """
    status, headers, body = response
    handler.send_response(status)

    for name in headers:
        handler.send_header(name, headers[name])

    handler.end_headers()
    handler.wfile.write(body)


def make_static_response(request_path):
    """
    Return a static file response, or a plain 404 response.
    """
    if request_path == "/favicon.ico":
        return make_empty_response(status=204)

    if request_path == "/":
        request_path = "/index.html"

    relative_path = unquote(request_path).lstrip("/")
    static_root = STATIC_DIR.resolve()
    file_path = (STATIC_DIR / relative_path).resolve()

    try:
        file_path.relative_to(static_root)
    except ValueError:
        return make_plain_response("Not found", status=404)

    if not file_path.is_file():
        return make_plain_response("Not found", status=404)

    try:
        body = file_path.read_bytes()
    except OSError as error:
        return make_plain_response(str(error), status=500)

    headers = {
        "Content-Type": guess_content_type(file_path),
        "Content-Length": str(len(body)),
    }
    return 200, headers, body


def make_handler(index_path):
    """
    Build the request handler class for one corpus inspector index.
    """

    class CorpusInspectorHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_values = parse_qs(parsed_url.query)
            params = flatten_query(query_values)

            if path.startswith("/api/"):
                response = handle_api_request(path, params, index_path)
            else:
                response = self.serve_static(path)

            send_response_tuple(self, response)

        def serve_static(self, path):
            return make_static_response(path)

        def log_message(self, message_format, *values):
            print("[INFO] " + (message_format % values))

    return CorpusInspectorHandler


def serve_corpus_inspector(index_path=DEFAULT_INDEX_PATH, host="127.0.0.1", port=8765):
    """
    Run the corpus inspector HTTP server.
    """
    index_path = Path(index_path)

    if not index_path.exists():
        print("[ERROR] Corpus inspector index does not exist: " + str(index_path))
        print("[ERROR] Run: uv run explore corpus-inspector index")
        return 1

    handler = make_handler(index_path)
    server = ThreadingHTTPServer((host, port), handler)

    try:
        print("[INFO] Corpus inspector server")
        print("[INFO] URL: http://" + host + ":" + str(port))
        print("[INFO] Press Ctrl+C to stop")
        server.serve_forever()
    except KeyboardInterrupt:
        print("[INFO] Stopping corpus inspector server")
    finally:
        server.server_close()

    return 0
