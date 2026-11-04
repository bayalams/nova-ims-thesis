"""
Local HTTP server for the KB Observatory.
"""

import json
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlparse

from explorer.webapps.kb_observatory.queries import DEFAULT_EVALUATION_PATH
from explorer.webapps.kb_observatory.queries import DEFAULT_KB_ROOT
from explorer.webapps.kb_observatory.queries import get_kb_summary
from explorer.webapps.kb_observatory.queries import get_recipe_detail
from explorer.webapps.kb_observatory.queries import run_query_search


STATIC_DIR = Path(__file__).parent / "static"


def make_json_response(data, status=200):
    """
    Return a JSON response tuple.
    """
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    return status, headers, body


def make_plain_response(message, status=404):
    """
    Return a plain text response tuple.
    """
    body = str(message).encode("utf-8")
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    return status, headers, body


def make_empty_response(status=204):
    """
    Return an empty response tuple.
    """
    return status, {"Content-Length": "0"}, b""


def flatten_query(query_values):
    """
    Convert parsed query values to a plain dictionary.
    """
    params = {}

    for key in query_values:
        values = query_values[key]
        if values:
            params[key] = values[-1]
        else:
            params[key] = ""

    return params


def guess_content_type(path):
    """
    Guess content type for static files.
    """
    suffix = Path(path).suffix.lower()

    if suffix == ".html":
        return "text/html; charset=utf-8"

    if suffix == ".css":
        return "text/css; charset=utf-8"

    if suffix == ".js":
        return "application/javascript; charset=utf-8"

    return "application/octet-stream"


def make_static_response(request_path):
    """
    Serve a file from the static folder.
    """
    if request_path == "/favicon.ico":
        return make_empty_response()

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


def send_response_tuple(handler, response):
    """
    Send a response tuple through a BaseHTTPRequestHandler.
    """
    status, headers, body = response
    handler.send_response(status)

    for name in headers:
        handler.send_header(name, headers[name])

    handler.end_headers()
    handler.wfile.write(body)


def handle_api_request(path, params, kb_root, evaluation_path):
    """
    Route one API request.
    """
    try:
        if path == "/api/summary":
            return make_json_response(get_kb_summary(kb_root, evaluation_path))

        if path.startswith("/api/recipes/"):
            recipe_name = path[len("/api/recipes/"):]
            return make_json_response(get_recipe_detail(kb_root, recipe_name, evaluation_path))

        if path == "/api/search":
            return make_json_response(
                run_query_search(
                    kb_root,
                    params.get("recipe", ""),
                    params.get("query", ""),
                    params.get("top_k", "10"),
                    params.get("search_mode", "ann"),
                    params.get("indexed_before", ""),
                )
            )

        return make_json_response({"error": "Unknown API path"}, status=404)
    except KeyError as error:
        return make_json_response({"error": "Recipe not found: " + str(error)}, status=404)
    except ValueError as error:
        return make_json_response({"error": str(error)}, status=400)
    except Exception as error:
        return make_json_response({"error": str(error)}, status=500)


def make_handler(kb_root, evaluation_path):
    """
    Build a request handler for one observatory server.
    """

    class KbObservatoryHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            params = flatten_query(parse_qs(parsed_url.query))

            if path.startswith("/api/"):
                response = handle_api_request(path, params, kb_root, evaluation_path)
            else:
                response = make_static_response(path)

            send_response_tuple(self, response)

        def log_message(self, message_format, *values):
            print("[INFO] " + (message_format % values))

    return KbObservatoryHandler


def serve_kb_observatory(
    kb_root=DEFAULT_KB_ROOT,
    evaluation_path=DEFAULT_EVALUATION_PATH,
    host="127.0.0.1",
    port=8766,
):
    """
    Run the KB Observatory server.
    """
    kb_root = Path(kb_root)
    evaluation_path = Path(evaluation_path)

    if not kb_root.exists():
        print("[ERROR] Knowledge-base root does not exist: " + str(kb_root))
        print("[ERROR] Build KBs first with: uv run --env-file .env build-kb run ...")
        return 1

    handler = make_handler(kb_root, evaluation_path)
    server = ThreadingHTTPServer((host, port), handler)

    try:
        print("[INFO] KB Observatory server")
        print("[INFO] KB root: " + str(kb_root))
        print("[INFO] Evaluation report: " + str(evaluation_path))
        print("[INFO] URL: http://" + host + ":" + str(port))
        print("[INFO] Query workbench calls OpenAI only when you run a query")
        print("[INFO] Press Ctrl+C to stop")
        server.serve_forever()
    except KeyboardInterrupt:
        print("[INFO] Stopping KB Observatory server")
    finally:
        server.server_close()

    return 0
