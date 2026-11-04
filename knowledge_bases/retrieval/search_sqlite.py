"""
SQLite Vec1 search helpers for knowledge-base recipes.
"""

from pathlib import Path

from knowledge_bases.build_knowledge_base import load_recipe
from knowledge_bases.build_knowledge_base import parse_timestamp_to_epoch
from knowledge_bases.embedding.openai_embeddings import build_embedding_client
from knowledge_bases.embedding.openai_embeddings import create_embedding_batch
from knowledge_bases.storage.sqlite_kb import find_vec1_extension
from knowledge_bases.storage.sqlite_kb import load_vec1_extension
from knowledge_bases.storage.sqlite_kb import open_kb_database
from knowledge_bases.storage.sqlite_kb import pack_vector


def search_recipe(recipe_name, query_text, top_k, search_mode, indexed_before=None):
    """
    Search one SQLite Vec1 knowledge base.

    PARAMETERS:
    - recipe_name: KB recipe name
    - query_text: User search query
    - top_k: Number of results to print
    - search_mode: "ann" or "exact"
    - indexed_before: Optional RSS indexed timestamp cutoff

    RETURNS:
    - A list of result dictionaries
    """
    if top_k < 1:
        raise ValueError("--top-k must be at least 1")

    if search_mode not in ["ann", "exact"]:
        raise ValueError("--search-mode must be ann or exact")

    indexed_before_epoch = None
    if indexed_before:
        indexed_before_epoch = parse_timestamp_to_epoch(indexed_before)
        if indexed_before_epoch is None:
            raise ValueError(f"Could not parse --indexed-before timestamp: {indexed_before}")

    recipe = load_recipe(recipe_name)
    db_path = Path(recipe["output_folder"]) / "kb.sqlite"

    if not db_path.exists():
        raise ValueError(f"KB database does not exist yet: {db_path}")

    vec1_extension_path = find_vec1_extension()
    connection = open_kb_database(db_path)
    try:
        load_vec1_extension(connection, vec1_extension_path)

        if indexed_before_epoch is not None:
            ensure_indexed_before_supported(connection)

        client = build_embedding_client(recipe)
        embedding_result = create_embedding_batch(client, [query_text], recipe)
        query_vector = embedding_result["vectors"][0]
        query_blob = pack_vector(query_vector)

        if search_mode == "exact":
            results = search_exact(connection, recipe, query_blob, top_k, indexed_before_epoch)
        else:
            results = search_ann(connection, recipe, query_blob, top_k, indexed_before_epoch)
    finally:
        connection.close()

    print_search_results(results)
    return results


def article_column_exists(connection, column_name):
    """
    Check whether the articles table has one column.

    PARAMETERS:
    - connection: sqlite3 connection
    - column_name: Column name to find

    RETURNS:
    - True when the column exists
    """
    rows = connection.execute("PRAGMA table_info(articles)").fetchall()

    for row in rows:
        if row["name"] == column_name:
            return True

    return False


def ensure_indexed_before_supported(connection):
    """
    Fail clearly if a KB was built before indexed timestamp storage existed.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - None
    """
    if article_column_exists(connection, "indexed_at_epoch"):
        return

    raise ValueError("This KB lacks indexed_at_epoch; rebuild the KB before using --indexed-before.")


def table_exists(connection, table_name):
    """
    Check whether a SQLite table exists.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_name: Table name to find

    RETURNS:
    - True when the table exists
    """
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def count_chunks(connection):
    """
    Count normal chunk rows.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - Integer chunk count
    """
    row = connection.execute("SELECT count(*) AS row_count FROM chunks").fetchone()
    return row["row_count"]


def ensure_vec1_model_loaded_for_lookup(connection, query_blob):
    """
    Load Vec1's model/config before rowid vector lookups.

    PARAMETERS:
    - connection: sqlite3 connection
    - query_blob: Packed query vector

    RETURNS:
    - None
    """
    if not table_exists(connection, "vec1_chunks_config"):
        return

    if count_chunks(connection) == 0:
        return

    # A fresh connection to a rebuilt flat Vec1 index returns placeholder
    # values for rowid vector lookups until an ANN query loads the model.
    connection.execute(
        """
        SELECT rowid
        FROM vec1_chunks
        WHERE distance = ? AND cmd = ?
        ORDER BY distance
        LIMIT 1
        """,
        (query_blob, '{"K":1,"nprobe":8}'),
    ).fetchall()


def get_distance_function(recipe):
    """
    Pick the Vec1 distance function for a recipe.

    PARAMETERS:
    - recipe: Recipe dictionary

    RETURNS:
    - SQL function name as a string
    """
    if recipe["search_distance"] == "cosine":
        return "vec1_cos_distance"

    return "vec1_l2_distance"


def search_ann(connection, recipe, query_blob, top_k, indexed_before_epoch=None):
    """
    Run a two-step Vec1 ANN search.

    PARAMETERS:
    - connection: sqlite3 connection
    - recipe: Recipe dictionary
    - query_blob: Packed query vector
    - top_k: Number of results
    - indexed_before_epoch: Optional RSS indexed timestamp cutoff

    RETURNS:
    - A list of result dictionaries
    """
    if indexed_before_epoch is None:
        candidate_count = max(top_k, top_k * 4)
    else:
        candidate_count = max(top_k * 20, 100)

    candidate_rowids = get_ann_candidate_rowids(connection, query_blob, candidate_count)
    rows = fetch_candidate_search_rows(
        connection,
        recipe,
        query_blob,
        candidate_rowids,
        top_k,
        indexed_before_epoch,
    )

    return rows_to_results(rows)


def get_ann_candidate_rowids(connection, query_blob, candidate_count):
    """
    Ask Vec1 for ANN candidate rowids only.

    PARAMETERS:
    - connection: sqlite3 connection
    - query_blob: Packed query vector
    - candidate_count: Number of candidate rowids to request

    RETURNS:
    - A list of chunk rowids
    """
    query_options = '{"K":' + str(candidate_count) + ',"nprobe":8}'
    rows = connection.execute(
        """
        SELECT rowid
        FROM vec1_chunks
        WHERE distance = ? AND cmd = ?
        ORDER BY distance
        LIMIT ?
        """,
        (query_blob, query_options, candidate_count),
    ).fetchall()

    candidate_rowids = []
    for row in rows:
        candidate_rowids.append(row["rowid"])

    return candidate_rowids


def fetch_candidate_search_rows(connection, recipe, query_blob, candidate_rowids, top_k, indexed_before_epoch=None):
    """
    Fetch candidate rows and rerank them with exact distance.

    PARAMETERS:
    - connection: sqlite3 connection
    - recipe: Recipe dictionary
    - query_blob: Packed query vector
    - candidate_rowids: ANN candidate rowids to consider
    - top_k: Number of rows to return
    - indexed_before_epoch: Optional RSS indexed timestamp cutoff

    RETURNS:
    - A list of SQLite rows
    """
    if not candidate_rowids:
        return []

    distance_function = get_distance_function(recipe)
    placeholders = []
    query_parameters = [query_blob]

    for candidate_rowid in candidate_rowids:
        placeholders.append("?")
        query_parameters.append(candidate_rowid)

    query_parameters.append(top_k)
    placeholder_text = ", ".join(placeholders)

    if indexed_before_epoch is not None:
        query_parameters = [query_blob]
        for candidate_rowid in candidate_rowids:
            query_parameters.append(candidate_rowid)
        query_parameters.append(indexed_before_epoch)
        query_parameters.append(top_k)

        rows = connection.execute(
            f"""
            SELECT
                c.chunk_rowid AS chunk_rowid,
                {distance_function}(?, lookup.vector) AS distance,
                c.chunk_id,
                c.article_id,
                c.chunk_index,
                c.chunk_text,
                a.source,
                a.title,
                a.url,
                a.published_at,
                a.indexed_at,
                a.indexed_at_epoch
            FROM chunks AS c
            JOIN articles AS a ON a.article_id = c.article_id
            JOIN vec1_chunks AS lookup ON lookup.rowid = c.chunk_rowid
            WHERE c.chunk_rowid IN ({placeholder_text})
              AND a.indexed_at_epoch <= ?
            ORDER BY distance
            LIMIT ?
            """,
            query_parameters,
        ).fetchall()

        return rows

    rows = connection.execute(
        f"""
        SELECT
            c.chunk_rowid AS chunk_rowid,
            {distance_function}(?, lookup.vector) AS distance,
            c.chunk_id,
            c.article_id,
            c.chunk_index,
            c.chunk_text,
            a.source,
            a.title,
            a.url,
            a.published_at
        FROM chunks AS c
        JOIN articles AS a ON a.article_id = c.article_id
        JOIN vec1_chunks AS lookup ON lookup.rowid = c.chunk_rowid
        WHERE c.chunk_rowid IN ({placeholder_text})
        ORDER BY distance
        LIMIT ?
        """,
        query_parameters,
    ).fetchall()

    return rows


def search_exact(connection, recipe, query_blob, top_k, indexed_before_epoch=None):
    """
    Run an exact Vec1 full scan.

    PARAMETERS:
    - connection: sqlite3 connection
    - recipe: Recipe dictionary
    - query_blob: Packed query vector
    - top_k: Number of results
    - indexed_before_epoch: Optional RSS indexed timestamp cutoff

    RETURNS:
    - A list of result dictionaries
    """
    distance_function = get_distance_function(recipe)
    ensure_vec1_model_loaded_for_lookup(connection, query_blob)

    if indexed_before_epoch is not None:
        ensure_indexed_before_supported(connection)

        rows = connection.execute(
            f"""
            SELECT
                c.chunk_rowid AS chunk_rowid,
                {distance_function}(?, lookup.vector) AS distance,
                c.chunk_id,
                c.article_id,
                c.chunk_index,
                c.chunk_text,
                a.source,
                a.title,
                a.url,
                a.published_at,
                a.indexed_at,
                a.indexed_at_epoch
            FROM chunks AS c
            CROSS JOIN vec1_chunks AS lookup
            JOIN articles AS a ON a.article_id = c.article_id
            WHERE lookup.rowid = c.chunk_rowid
              AND a.indexed_at_epoch <= ?
            ORDER BY distance
            LIMIT ?
            """,
            (query_blob, indexed_before_epoch, top_k),
        ).fetchall()

        return rows_to_results(rows)

    rows = connection.execute(
        f"""
        SELECT
            c.chunk_rowid AS chunk_rowid,
            {distance_function}(?, lookup.vector) AS distance,
            c.chunk_id,
            c.article_id,
            c.chunk_index,
            c.chunk_text,
            a.source,
            a.title,
            a.url,
            a.published_at
        FROM chunks AS c
        CROSS JOIN vec1_chunks AS lookup
        JOIN articles AS a ON a.article_id = c.article_id
        WHERE lookup.rowid = c.chunk_rowid
        ORDER BY distance
        LIMIT ?
        """,
        (query_blob, top_k),
    ).fetchall()

    return rows_to_results(rows)


def rows_to_results(rows):
    """
    Convert SQLite rows to plain dictionaries.

    PARAMETERS:
    - rows: sqlite3 rows

    RETURNS:
    - A list of result dictionaries
    """
    results = []

    for row in rows:
        result = {
            "chunk_rowid": row["chunk_rowid"],
            "distance": row["distance"],
            "chunk_id": row["chunk_id"],
            "article_id": row["article_id"],
            "chunk_index": row["chunk_index"],
            "chunk_text": row["chunk_text"],
            "source": row["source"],
            "title": row["title"],
            "url": row["url"],
            "published_at": row["published_at"],
        }

        row_keys = row.keys()
        if "indexed_at" in row_keys:
            result["indexed_at"] = row["indexed_at"]
        if "indexed_at_epoch" in row_keys:
            result["indexed_at_epoch"] = row["indexed_at_epoch"]

        results.append(result)

    return results


def make_preview(text, maximum_characters=260):
    """
    Build a short single-line result preview.

    PARAMETERS:
    - text: Chunk text
    - maximum_characters: Maximum preview length

    RETURNS:
    - Preview string
    """
    preview = " ".join(text.split())

    if len(preview) <= maximum_characters:
        return preview

    return preview[:maximum_characters].rstrip() + "..."


def print_search_results(results):
    """
    Print search results for a human operator.

    PARAMETERS:
    - results: List of result dictionaries

    RETURNS:
    - None
    """
    print(f"[INFO] Search results: {len(results)}")

    for position, result in enumerate(results, start=1):
        print(f"[{position}/{len(results)}] {result['source']} distance={result['distance']}")
        print(f"    title: {result['title']}")
        print(f"    url: {result['url']}")
        print(f"    chunk: {result['chunk_index']}")
        print(f"    text: {make_preview(result['chunk_text'])}")
