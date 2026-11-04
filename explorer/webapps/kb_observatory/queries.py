"""
Read-only helpers for inspecting knowledge-base builds.
"""

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote


DEFAULT_KB_ROOT = Path("shared_data/knowledge_bases")
DEFAULT_EVALUATION_PATH = DEFAULT_KB_ROOT / "evaluation_metrics.json"
MAX_EXAMPLES = 20

METRIC_NOTES = {
    "article_coverage_rate": {
        "name": "Article coverage",
        "direction": "higher is better",
        "why": "Shows whether the KB indexed the articles it was expected to include.",
    },
    "skipped_too_large_article_count": {
        "name": "Skipped too-large articles",
        "direction": "lower is better",
        "why": "No-chunking recipes can lose long articles when one embedding input is too large.",
    },
    "boundary_break_rate": {
        "name": "Boundary break rate",
        "direction": "lower is better",
        "why": "High values mean chunks often start or end in the middle of a word.",
    },
    "lead_paragraph_intact_rate": {
        "name": "Lead paragraph intact",
        "direction": "higher is better",
        "why": "Shows whether the first paragraph survives as a coherent retrievable unit.",
    },
    "duplicate_chunk_rate": {
        "name": "Duplicate chunks",
        "direction": "lower is better",
        "why": "Duplicates waste storage and can crowd retrieval results.",
    },
    "same_article_max_chunk_share": {
        "name": "Largest article share",
        "direction": "lower is usually better",
        "why": "Shows whether one long article dominates the chunk set.",
    },
    "combined_self_retrieval_top_5_rate": {
        "name": "Top-5 self retrieval",
        "direction": "higher is better",
        "why": "Checks whether article titles and summaries retrieve their own article.",
    },
    "overlap_waste_rate": {
        "name": "Overlap waste",
        "direction": "lower is usually better",
        "why": "Measures repeated text returned in top-k retrieval results.",
    },
}


def load_json_file(path):
    """
    Load JSON from a path, returning an empty dictionary when missing.
    """
    path = Path(path)

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def read_jsonl_file(path, limit=MAX_EXAMPLES):
    """
    Read a JSONL file into a list of dictionaries.
    """
    path = Path(path)
    records = []

    if not path.exists():
        return records

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records

    for line in lines:
        if len(records) >= limit:
            break

        line = line.strip()
        if line == "":
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(record, dict):
            records.append(record)

    return records


def connect_database(db_path):
    """
    Open one SQLite database with dictionary-like rows.
    """
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row):
    """
    Convert a SQLite row to a normal dictionary.
    """
    return dict(row)


def safe_int(value, default_value):
    """
    Convert a value to int with a fallback.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def safe_float(value, default_value=None):
    """
    Convert a value to float with a fallback.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default_value


def normalize_recipe_name(recipe_name):
    """
    Decode and strip a recipe name from a URL path or request parameter.
    """
    return unquote(str(recipe_name)).strip()


def list_recipe_folders(kb_root):
    """
    Find KB output folders under the shared KB root.
    """
    kb_root = Path(kb_root)
    folders = []

    if not kb_root.exists():
        return folders

    for folder in kb_root.iterdir():
        if not folder.is_dir():
            continue

        if (folder / "manifest.json").exists() or (folder / "kb.sqlite").exists():
            folders.append(folder)

    folders.sort(key=lambda path: path.name)
    return folders


def load_evaluation_by_recipe(evaluation_path):
    """
    Load an evaluation JSON report keyed by recipe name.
    """
    report = load_json_file(evaluation_path)
    by_recipe = {}

    for recipe_report in report.get("recipes", []):
        if not isinstance(recipe_report, dict):
            continue

        recipe_name = recipe_report.get("recipe_name")
        if recipe_name:
            by_recipe[recipe_name] = recipe_report

    return by_recipe


def count_rows(connection, table_name):
    """
    Count rows in a normal SQLite table.
    """
    try:
        row = connection.execute("SELECT count(*) AS count FROM " + table_name).fetchone()
    except sqlite3.Error:
        return None

    return row["count"]


def get_database_counts(db_path):
    """
    Read basic counts from a KB SQLite database.
    """
    counts = {
        "article_count": None,
        "chunk_count": None,
        "vector_count": None,
        "embedding_batch_count": None,
    }

    if not Path(db_path).exists():
        return counts

    connection = connect_database(db_path)
    try:
        counts["article_count"] = count_rows(connection, "articles")
        counts["chunk_count"] = count_rows(connection, "chunks")
        counts["vector_count"] = count_rows(connection, "vec1_chunks")
        counts["embedding_batch_count"] = count_rows(connection, "embedding_batches")
    finally:
        connection.close()

    return counts


def get_nested_value(data, keys, default_value=None):
    """
    Read a nested dictionary value.
    """
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default_value

        if key not in current:
            return default_value

        current = current[key]

    return current


def first_present(values, default_value=None):
    """
    Return the first value that is not None.
    """
    for value in values:
        if value is not None:
            return value

    return default_value


def make_recipe_summary(folder, evaluation_by_recipe):
    """
    Create one compact recipe row for the observatory table.
    """
    manifest_path = folder / "manifest.json"
    db_path = folder / "kb.sqlite"
    skip_path = folder / "embedding_skipped_articles.jsonl"
    manifest = load_json_file(manifest_path)
    recipe_name = manifest.get("recipe_name", folder.name)
    evaluation = evaluation_by_recipe.get(recipe_name, {})
    sanity = evaluation.get("sanity_metrics", {})
    thesis = evaluation.get("thesis_metrics", {})
    diagnostics = evaluation.get("diagnostic_metrics", {})
    retrieval = evaluation.get("retrieval_metrics", {})
    counts = get_database_counts(db_path)

    article_count = first_present([sanity.get("article_count"), counts["article_count"], manifest.get("article_count")], 0)
    chunk_count = first_present([sanity.get("chunk_count"), counts["chunk_count"], manifest.get("chunk_count")], 0)
    vector_count = first_present([sanity.get("vector_count"), counts["vector_count"], manifest.get("vector_count")], 0)
    skipped_count = first_present(
        [
            sanity.get("skipped_too_large_article_count"),
            manifest.get("skipped_too_large_article_count"),
        ],
        0,
    )

    return {
        "recipe_name": recipe_name,
        "folder_name": folder.name,
        "output_folder": str(folder),
        "has_database": db_path.exists(),
        "has_manifest": manifest_path.exists(),
        "has_skip_report": skip_path.exists(),
        "status": evaluation.get("status", "not_evaluated"),
        "embedding_model": first_present(
            [
                get_nested_value(evaluation, ["recipe_config", "embedding_model"]),
                manifest.get("embedding_model"),
                get_nested_value(manifest, ["recipe", "embedding_model"]),
            ],
            "",
        ),
        "chunking_method": first_present(
            [
                get_nested_value(evaluation, ["recipe_config", "chunking_method"]),
                manifest.get("chunking_method"),
                get_nested_value(manifest, ["recipe", "chunking_method"]),
            ],
            "",
        ),
        "chunk_size_characters": first_present(
            [
                get_nested_value(evaluation, ["recipe_config", "chunk_size_characters"]),
                manifest.get("chunk_size_characters"),
                get_nested_value(manifest, ["recipe", "chunk_size_characters"]),
            ],
            None,
        ),
        "chunk_overlap_characters": first_present(
            [
                get_nested_value(evaluation, ["recipe_config", "chunk_overlap_characters"]),
                manifest.get("chunk_overlap_characters"),
                get_nested_value(manifest, ["recipe", "chunk_overlap_characters"]),
            ],
            None,
        ),
        "expected_article_count": sanity.get("expected_article_count"),
        "article_count": article_count,
        "article_coverage_rate": sanity.get("article_coverage_rate"),
        "chunk_count": chunk_count,
        "vector_count": vector_count,
        "skipped_too_large_article_count": skipped_count,
        "boundary_break_rate": thesis.get("boundary_break_rate"),
        "lead_paragraph_intact_rate": thesis.get("lead_paragraph_intact_rate"),
        "duplicate_chunk_rate": diagnostics.get("duplicate_chunk_rate"),
        "same_article_max_chunk_share": diagnostics.get("same_article_max_chunk_share"),
        "combined_self_retrieval_top_5_rate": get_nested_value(
            retrieval,
            ["self_retrieval", "combined_top_5_rate"],
        ),
        "overlap_waste_rate": get_nested_value(
            retrieval,
            ["context_efficiency", "overlap_waste_rate"],
        ),
    }


def get_kb_summary(kb_root=DEFAULT_KB_ROOT, evaluation_path=DEFAULT_EVALUATION_PATH):
    """
    Return a root-level summary of all discovered KB recipe folders.
    """
    evaluation_by_recipe = load_evaluation_by_recipe(evaluation_path)
    recipes = []

    for folder in list_recipe_folders(kb_root):
        recipes.append(make_recipe_summary(folder, evaluation_by_recipe))

    built_count = 0
    total_articles = 0
    total_chunks = 0
    total_skipped = 0

    for recipe in recipes:
        if recipe["has_database"]:
            built_count = built_count + 1
        total_articles = total_articles + safe_int(recipe.get("article_count"), 0)
        total_chunks = total_chunks + safe_int(recipe.get("chunk_count"), 0)
        total_skipped = total_skipped + safe_int(recipe.get("skipped_too_large_article_count"), 0)

    return {
        "kb_root": str(Path(kb_root)),
        "evaluation_path": str(Path(evaluation_path)),
        "evaluation_exists": Path(evaluation_path).exists(),
        "recipe_count": len(recipes),
        "built_recipe_count": built_count,
        "total_articles": total_articles,
        "total_chunks": total_chunks,
        "total_skipped_too_large_articles": total_skipped,
        "recipes": recipes,
        "metric_notes": METRIC_NOTES,
    }


def find_recipe_folder(kb_root, recipe_name):
    """
    Find one recipe folder by manifest recipe name or folder name.
    """
    recipe_name = normalize_recipe_name(recipe_name)

    for folder in list_recipe_folders(kb_root):
        if folder.name == recipe_name:
            return folder

        manifest = load_json_file(folder / "manifest.json")
        if manifest.get("recipe_name") == recipe_name:
            return folder

    raise KeyError(recipe_name)


def fetch_rows(connection, sql, values=None):
    """
    Run a SELECT query and return dictionaries.
    """
    if values is None:
        values = []

    rows = connection.execute(sql, values).fetchall()
    return [row_to_dict(row) for row in rows]


def make_chunk_preview(text, maximum_characters=360):
    """
    Return a compact one-line chunk preview.
    """
    preview = " ".join(str(text or "").split())

    if len(preview) <= maximum_characters:
        return preview

    return preview[:maximum_characters].rstrip() + "..."


def add_chunk_previews(rows):
    """
    Add chunk length and preview fields to example rows.
    """
    for row in rows:
        text = row.get("chunk_text", "")
        row["chunk_character_count"] = len(str(text))
        row["chunk_preview"] = make_chunk_preview(text)
        if "chunk_text" in row:
            del row["chunk_text"]

    return rows


def get_recipe_examples(db_path):
    """
    Read useful real examples from the KB database.
    """
    empty_examples = {
        "longest_chunks": [],
        "shortest_chunks": [],
        "articles_by_chunk_count": [],
        "duplicate_chunks": [],
        "latest_articles": [],
    }

    if not Path(db_path).exists():
        return empty_examples

    connection = connect_database(db_path)

    try:
        longest_chunks = fetch_rows(
            connection,
            """
            SELECT
                c.chunk_id,
                c.article_id,
                c.chunk_index,
                c.chunk_text,
                a.source,
                a.title,
                a.published_at,
                a.url
            FROM chunks AS c
            JOIN articles AS a ON a.article_id = c.article_id
            ORDER BY length(c.chunk_text) DESC, c.chunk_id ASC
            LIMIT 10
            """,
        )
        shortest_chunks = fetch_rows(
            connection,
            """
            SELECT
                c.chunk_id,
                c.article_id,
                c.chunk_index,
                c.chunk_text,
                a.source,
                a.title,
                a.published_at,
                a.url
            FROM chunks AS c
            JOIN articles AS a ON a.article_id = c.article_id
            ORDER BY length(c.chunk_text) ASC, c.chunk_id ASC
            LIMIT 10
            """,
        )
        articles_by_chunk_count = fetch_rows(
            connection,
            """
            SELECT
                a.article_id,
                a.source,
                a.title,
                a.published_at,
                COUNT(c.chunk_id) AS chunk_count
            FROM articles AS a
            LEFT JOIN chunks AS c ON c.article_id = a.article_id
            GROUP BY a.article_id, a.source, a.title, a.published_at
            ORDER BY chunk_count DESC, a.article_id ASC
            LIMIT 10
            """,
        )
        duplicate_chunks = fetch_rows(
            connection,
            """
            SELECT
                lower(trim(chunk_text)) AS normalized_text,
                COUNT(*) AS duplicate_count,
                MIN(chunk_id) AS first_chunk_id,
                MIN(article_id) AS first_article_id,
                MIN(chunk_text) AS chunk_text
            FROM chunks
            GROUP BY lower(trim(chunk_text))
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC, first_chunk_id ASC
            LIMIT 10
            """,
        )
        latest_articles = fetch_rows(
            connection,
            """
            SELECT
                article_id,
                source,
                title,
                published_at,
                indexed_at,
                url
            FROM articles
            ORDER BY indexed_at_epoch IS NULL ASC, indexed_at_epoch DESC, article_id ASC
            LIMIT 10
            """,
        )
    except sqlite3.Error:
        return empty_examples
    finally:
        connection.close()

    return {
        "longest_chunks": add_chunk_previews(longest_chunks),
        "shortest_chunks": add_chunk_previews(shortest_chunks),
        "articles_by_chunk_count": articles_by_chunk_count,
        "duplicate_chunks": add_chunk_previews(duplicate_chunks),
        "latest_articles": latest_articles,
    }


def get_recipe_metrics(evaluation_by_recipe, recipe_name):
    """
    Return metric groups for one recipe from the evaluation report.
    """
    evaluation = evaluation_by_recipe.get(recipe_name, {})

    return {
        "status": evaluation.get("status", "not_evaluated"),
        "sanity_metrics": evaluation.get("sanity_metrics", {}),
        "thesis_metrics": evaluation.get("thesis_metrics", {}),
        "diagnostic_metrics": evaluation.get("diagnostic_metrics", {}),
        "retrieval_metrics": evaluation.get("retrieval_metrics", {}),
    }


def get_recipe_detail(kb_root, recipe_name, evaluation_path=DEFAULT_EVALUATION_PATH):
    """
    Return manifest, metrics, skipped articles, and example rows for one recipe.
    """
    folder = find_recipe_folder(kb_root, recipe_name)
    manifest = load_json_file(folder / "manifest.json")
    actual_recipe_name = manifest.get("recipe_name", folder.name)
    evaluation_by_recipe = load_evaluation_by_recipe(evaluation_path)

    return {
        "recipe_name": actual_recipe_name,
        "folder_name": folder.name,
        "output_folder": str(folder),
        "database_path": str(folder / "kb.sqlite"),
        "manifest_path": str(folder / "manifest.json"),
        "skip_report_path": str(folder / "embedding_skipped_articles.jsonl"),
        "manifest": manifest,
        "summary": make_recipe_summary(folder, evaluation_by_recipe),
        "metrics": get_recipe_metrics(evaluation_by_recipe, actual_recipe_name),
        "metric_notes": METRIC_NOTES,
        "skipped_articles": read_jsonl_file(folder / "embedding_skipped_articles.jsonl", limit=50),
        "examples": get_recipe_examples(folder / "kb.sqlite"),
    }


def parse_top_k(value):
    """
    Parse and clamp top-k for search requests.
    """
    top_k = safe_int(value, 10)

    if top_k < 1:
        top_k = 1

    if top_k > 50:
        top_k = 50

    return top_k


def load_search_recipe_config(folder, recipe_name):
    """
    Load enough recipe configuration to run a search.
    """
    manifest = load_json_file(folder / "manifest.json")
    recipe = manifest.get("recipe", {})

    if not isinstance(recipe, dict):
        recipe = {}

    if not recipe:
        recipe = {
            "name": recipe_name,
            "output_folder": str(folder),
            "embedding_model": manifest.get("embedding_model", "text-embedding-3-small"),
            "search_distance": manifest.get("search_distance", "cosine"),
        }

    recipe["name"] = recipe.get("name", recipe_name)
    recipe["output_folder"] = str(folder)
    recipe["embedding_model"] = recipe.get("embedding_model", manifest.get("embedding_model", "text-embedding-3-small"))
    recipe["search_distance"] = recipe.get("search_distance", manifest.get("search_distance", "cosine"))
    return recipe


def run_query_search(
    kb_root,
    recipe_name,
    query_text,
    top_k=10,
    search_mode="ann",
    indexed_before="",
):
    """
    Run an explicit user-triggered vector query against one KB recipe.
    """
    from knowledge_bases.build_knowledge_base import parse_timestamp_to_epoch
    from knowledge_bases.embedding.openai_embeddings import build_openai_client
    from knowledge_bases.embedding.openai_embeddings import create_embedding_batch
    from knowledge_bases.retrieval.search_sqlite import ensure_indexed_before_supported
    from knowledge_bases.retrieval.search_sqlite import search_ann
    from knowledge_bases.retrieval.search_sqlite import search_exact
    from knowledge_bases.storage.sqlite_kb import find_vec1_extension
    from knowledge_bases.storage.sqlite_kb import load_vec1_extension
    from knowledge_bases.storage.sqlite_kb import open_kb_database
    from knowledge_bases.storage.sqlite_kb import pack_vector

    query_text = str(query_text or "").strip()
    search_mode = str(search_mode or "ann").strip().lower()
    top_k = parse_top_k(top_k)

    if query_text == "":
        raise ValueError("Search query cannot be blank")

    if search_mode != "ann" and search_mode != "exact":
        raise ValueError("Search mode must be ann or exact")

    indexed_before_epoch = None
    if indexed_before is not None and str(indexed_before).strip() != "":
        indexed_before_epoch = parse_timestamp_to_epoch(indexed_before)
        if indexed_before_epoch is None:
            raise ValueError("Could not parse indexed-before timestamp")

    folder = find_recipe_folder(kb_root, recipe_name)
    recipe = load_search_recipe_config(folder, normalize_recipe_name(recipe_name))
    db_path = folder / "kb.sqlite"

    if not db_path.exists():
        raise ValueError("KB database does not exist: " + str(db_path))

    vec1_extension_path = find_vec1_extension()
    connection = open_kb_database(db_path)

    try:
        load_vec1_extension(connection, vec1_extension_path)

        if indexed_before_epoch is not None:
            ensure_indexed_before_supported(connection)

        client = build_openai_client()
        embedding_result = create_embedding_batch(client, [query_text], recipe["embedding_model"])
        query_vector = embedding_result["vectors"][0]
        query_blob = pack_vector(query_vector)

        if indexed_before_epoch is not None:
            results = search_exact(connection, recipe, query_blob, top_k, indexed_before_epoch)
        elif search_mode == "exact":
            results = search_exact(connection, recipe, query_blob, top_k)
        else:
            results = search_ann(connection, recipe, query_blob, top_k)
    finally:
        connection.close()

    for result in results:
        result["chunk_preview"] = make_chunk_preview(result.get("chunk_text", ""))
        result["chunk_character_count"] = len(str(result.get("chunk_text", "")))

    return {
        "recipe_name": recipe["name"],
        "query_text": query_text,
        "top_k": top_k,
        "search_mode": search_mode,
        "indexed_before": str(indexed_before or ""),
        "result_count": len(results),
        "results": results,
    }
