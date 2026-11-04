"""
SQLite helpers for knowledge-base databases.

This module owns normal SQLite tables and the small amount of extension-loading
logic needed before Vec1 can be used.
"""

import sqlite3
import struct
from pathlib import Path


def open_kb_database(db_path):
    """
    Open a SQLite knowledge-base database.

    PARAMETERS:
    - db_path: Path to the SQLite database file

    RETURNS:
    - A sqlite3 connection
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row

    # Step 1: Make normal SQLite writes more reliable for command-line use.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")

    return connection


def create_kb_schema(connection):
    """
    Create normal SQLite tables for a KB database.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - None
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS build_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            article_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            url TEXT,
            published_at TEXT,
            indexed_at TEXT,
            indexed_at_epoch REAL,
            cleaned_at TEXT,
            input_file_path TEXT,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_rowid INTEGER PRIMARY KEY,
            chunk_id TEXT NOT NULL UNIQUE,
            article_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            character_start INTEGER NOT NULL,
            character_end INTEGER NOT NULL,
            chunk_hash TEXT NOT NULL,
            FOREIGN KEY(article_id) REFERENCES articles(article_id) ON DELETE CASCADE
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_batches (
            batch_id TEXT PRIMARY KEY,
            embedding_model TEXT NOT NULL,
            embedding_dimensions INTEGER,
            token_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_text TEXT
        )
        """
    )

    connection.commit()


def list_table_names(connection):
    """
    List SQLite table names in a KB database.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - A sorted list of table names
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


def find_vec1_extension(local_tools_folder=Path(".local_tools/vec1")):
    """
    Find the compiled Vec1 extension for this machine.

    PARAMETERS:
    - local_tools_folder: Folder where setup_vec1.sh writes Vec1 artifacts

    RETURNS:
    - Path to the extension file

    RAISES:
    - ValueError when no compiled extension can be found
    """
    local_tools_folder = Path(local_tools_folder)

    possible_paths = [
        local_tools_folder / "vec1.dylib",
        local_tools_folder / "vec1.so",
    ]

    for possible_path in possible_paths:
        if possible_path.exists():
            return possible_path

    raise ValueError("Vec1 extension is missing. Run: uv run build-kb setup-vec1")


def load_vec1_extension(connection, extension_path):
    """
    Load the Vec1 SQLite extension into one connection.

    PARAMETERS:
    - connection: sqlite3 connection
    - extension_path: Path to vec1.dylib or vec1.so

    RETURNS:
    - None
    """
    extension_path = Path(extension_path)

    if not extension_path.exists():
        raise ValueError(f"Vec1 extension does not exist: {extension_path}")

    connection.enable_load_extension(True)

    try:
        connection.load_extension(str(extension_path))
    finally:
        connection.enable_load_extension(False)


def create_vec1_table(connection):
    """
    Create the Vec1 virtual table that stores chunk embeddings.

    PARAMETERS:
    - connection: sqlite3 connection with Vec1 already loaded

    RETURNS:
    - None
    """
    connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vec1_chunks USING vec1(vector)")
    connection.commit()


def pack_vector(vector):
    """
    Convert a Python list of floats into Vec1's native blob format.

    PARAMETERS:
    - vector: A list of float values

    RETURNS:
    - A bytes object containing 32-bit floats
    """
    if not vector:
        raise ValueError("Cannot pack an empty vector")

    format_string = "<" + ("f" * len(vector))
    return struct.pack(format_string, *vector)


def get_article_hashes(connection):
    """
    Read content hashes for articles that finished embedding.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - A dictionary mapping article_id to content_hash
    """
    rows = connection.execute(
        """
        SELECT article_id, content_hash
        FROM articles
        WHERE status = 'ready'
        """
    ).fetchall()

    article_hashes = {}
    for row in rows:
        article_hashes[row["article_id"]] = row["content_hash"]

    return article_hashes


def set_article_status(connection, article_id, status):
    """
    Update the build status for one article row.

    PARAMETERS:
    - connection: sqlite3 connection
    - article_id: Article id to update
    - status: New status text

    RETURNS:
    - None
    """
    connection.execute(
        """
        UPDATE articles
        SET status = ?
        WHERE article_id = ?
        """,
        (status, article_id),
    )


def delete_article_rows(connection, article_id):
    """
    Delete one article and its old chunks/vectors.

    PARAMETERS:
    - connection: sqlite3 connection
    - article_id: Article id to delete

    RETURNS:
    - Number of chunk rows removed
    """
    rows = connection.execute(
        """
        SELECT chunk_rowid
        FROM chunks
        WHERE article_id = ?
        """,
        (article_id,),
    ).fetchall()

    deleted_chunks = len(rows)

    for row in rows:
        connection.execute("DELETE FROM vec1_chunks WHERE rowid = ?", (row["chunk_rowid"],))

    connection.execute("DELETE FROM articles WHERE article_id = ?", (article_id,))

    return deleted_chunks


def insert_article(connection, article_record):
    """
    Insert one article metadata row.

    PARAMETERS:
    - connection: sqlite3 connection
    - article_record: Dictionary with article fields

    RETURNS:
    - None
    """
    connection.execute(
        """
        INSERT INTO articles (
            article_id,
            source,
            title,
            url,
            published_at,
            indexed_at,
            indexed_at_epoch,
            cleaned_at,
            input_file_path,
            content_hash,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_record["article_id"],
            article_record["source"],
            article_record["title"],
            article_record["url"],
            article_record["published_at"],
            article_record["indexed_at"],
            article_record["indexed_at_epoch"],
            article_record["cleaned_at"],
            article_record["input_file_path"],
            article_record["content_hash"],
            article_record["status"],
        ),
    )


def insert_chunk(connection, chunk_record):
    """
    Insert one chunk row.

    PARAMETERS:
    - connection: sqlite3 connection
    - chunk_record: Dictionary with chunk fields

    RETURNS:
    - The integer chunk_rowid generated by SQLite
    """
    cursor = connection.execute(
        """
        INSERT INTO chunks (
            chunk_id,
            article_id,
            chunk_index,
            chunk_text,
            character_start,
            character_end,
            chunk_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_record["chunk_id"],
            chunk_record["article_id"],
            chunk_record["chunk_index"],
            chunk_record["chunk_text"],
            chunk_record["character_start"],
            chunk_record["character_end"],
            chunk_record["chunk_hash"],
        ),
    )

    return cursor.lastrowid


def insert_vec1_vector(connection, rowid, vector):
    """
    Insert one chunk vector into Vec1.

    PARAMETERS:
    - connection: sqlite3 connection
    - rowid: Rowid matching the chunks.chunk_rowid value
    - vector: Python list of floats

    RETURNS:
    - None
    """
    vector_blob = pack_vector(vector)
    connection.execute(
        """
        INSERT INTO vec1_chunks(rowid, vector)
        VALUES (?, ?)
        """,
        (rowid, vector_blob),
    )


def insert_embedding_batch(connection, batch_record):
    """
    Record one embedding batch result.

    PARAMETERS:
    - connection: sqlite3 connection
    - batch_record: Dictionary with embedding batch fields

    RETURNS:
    - None
    """
    connection.execute(
        """
        INSERT INTO embedding_batches (
            batch_id,
            embedding_model,
            embedding_dimensions,
            token_count,
            status,
            error_text
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            batch_record["batch_id"],
            batch_record["embedding_model"],
            batch_record["embedding_dimensions"],
            batch_record["token_count"],
            batch_record["status"],
            batch_record["error_text"],
        ),
    )


def count_table_rows(connection, table_name):
    """
    Count rows in a known table.

    PARAMETERS:
    - connection: sqlite3 connection
    - table_name: Table name to count

    RETURNS:
    - Integer row count
    """
    allowed_tables = ["articles", "chunks", "embedding_batches", "vec1_chunks"]

    if table_name not in allowed_tables:
        raise ValueError(f"Unknown count table: {table_name}")

    row = connection.execute(f"SELECT count(*) AS row_count FROM {table_name}").fetchone()
    return row["row_count"]


def set_vec1_threads(connection, workers):
    """
    Tell Vec1 how many threads to use for rebuild work.

    PARAMETERS:
    - connection: sqlite3 connection
    - workers: Worker count

    RETURNS:
    - None
    """
    connection.execute(
        """
        INSERT INTO vec1_chunks(cmd, vector)
        VALUES ('nthread', ?)
        """,
        (workers,),
    )


def rebuild_vec1_index(connection, workers, distance):
    """
    Rebuild the Vec1 index.

    PARAMETERS:
    - connection: sqlite3 connection
    - workers: Worker count for Vec1 rebuild
    - distance: "cosine" or "l2"

    RETURNS:
    - A status string
    """
    vector_count = count_table_rows(connection, "vec1_chunks")

    if vector_count == 0:
        return "empty"

    set_vec1_threads(connection, workers)

    if distance == "cosine":
        vec1_distance = "cos"
    else:
        vec1_distance = "l2"

    if vector_count < 512:
        rebuild_config = '{"index":"flat","distance":"' + vec1_distance + '"}'
        connection.execute(
            """
            INSERT INTO vec1_chunks(cmd, vector)
            VALUES ('rebuild', ?)
            """,
            (rebuild_config,),
        )
        connection.commit()
        return "flat_index"

    train_config = '{"distance":"' + vec1_distance + '","nbucket":32,"codesize":0}'
    row = connection.execute(
        """
        SELECT vec1_train(vector, ?) AS model
        FROM vec1_chunks
        """,
        (train_config,),
    ).fetchone()

    model_blob = row["model"]
    connection.execute(
        """
        INSERT INTO vec1_chunks(cmd, vector)
        VALUES ('rebuild', ?)
        """,
        (model_blob,),
    )
    connection.commit()
    return "ann_index"
