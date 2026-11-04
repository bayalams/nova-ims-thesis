"""
SQLite read helpers for knowledge-base evaluation.
"""

import sqlite3


def get_table_names(connection):
    """
    Read SQLite table names.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - List of table names
    """
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """
    ).fetchall()

    table_names = []
    for row in rows:
        table_names.append(row["name"])

    return table_names


def get_table_columns(connection, table_name):
    """
    Read column names for one SQLite table.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_name: Table name

    RETURNS:
    - List of column names
    """
    try:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    except sqlite3.Error:
        return []

    column_names = []
    for row in rows:
        column_names.append(row["name"])

    return column_names


def fetch_article_rows(connection, table_names, article_columns):
    """
    Fetch article rows with whichever known metadata columns exist.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_names: Existing table names
    - article_columns: Existing article columns

    RETURNS:
    - Article rows as dictionaries
    """
    if "articles" not in table_names:
        return []

    wanted_columns = [
        "article_id",
        "source",
        "title",
        "url",
        "published_at",
        "indexed_at",
        "input_file_path",
        "content_hash",
    ]

    select_columns = []
    for column_name in wanted_columns:
        if column_name in article_columns:
            select_columns.append(column_name)

    if not select_columns:
        return []

    rows = connection.execute(
        "SELECT " + ", ".join(select_columns) + " FROM articles ORDER BY article_id"
    ).fetchall()

    article_rows = []
    for row in rows:
        row_dictionary = {}

        for column_name in wanted_columns:
            if column_name in select_columns:
                row_dictionary[column_name] = row[column_name]
            else:
                row_dictionary[column_name] = None

        article_rows.append(row_dictionary)

    return article_rows


def fetch_chunk_rows(connection, table_names):
    """
    Fetch chunk rows.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_names: Existing table names

    RETURNS:
    - Chunk rows as dictionaries
    """
    if "chunks" not in table_names:
        return []

    rows = connection.execute(
        """
        SELECT
            chunk_rowid,
            chunk_id,
            article_id,
            chunk_index,
            chunk_text,
            character_start,
            character_end
        FROM chunks
        ORDER BY article_id, chunk_index
        """
    ).fetchall()

    chunk_rows = []
    for row in rows:
        chunk_rows.append(
            {
                "chunk_rowid": row["chunk_rowid"],
                "chunk_id": row["chunk_id"],
                "article_id": row["article_id"],
                "chunk_index": row["chunk_index"],
                "chunk_text": row["chunk_text"],
                "character_start": row["character_start"],
                "character_end": row["character_end"],
            }
        )

    return chunk_rows


def count_rows_with_manifest_fallback(connection, table_names, table_name, manifest, manifest_key):
    """
    Count table rows, using manifest value if SQLite cannot read the table.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_names: Existing table names
    - table_name: Table name to count
    - manifest: Build manifest dictionary
    - manifest_key: Manifest key to use as fallback

    RETURNS:
    - Row count, or None
    """
    if table_name not in table_names:
        return manifest.get(manifest_key)

    try:
        row = connection.execute(f"SELECT count(*) AS row_count FROM {table_name}").fetchone()
        return row["row_count"]
    except sqlite3.Error:
        return manifest.get(manifest_key)
