"""
Shared SQLite storage for precomputed entity mentions.
"""

import hashlib
import json
import sqlite3
from datetime import datetime
from datetime import timezone
from pathlib import Path


def open_entity_store(db_path):
    """
    Open the shared entity store database.

    PARAMETERS:
    - db_path: SQLite database path

    RETURNS:
    - sqlite3 connection
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def create_entity_store_schema(connection):
    """
    Create entity store tables.

    PARAMETERS:
    - connection: sqlite3 connection

    RETURNS:
    - None
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_documents (
            cache_key TEXT PRIMARY KEY,
            article_id TEXT,
            content_hash TEXT,
            text_hash TEXT NOT NULL,
            text_character_count INTEGER NOT NULL,
            ner_backend TEXT NOT NULL,
            ner_model TEXT NOT NULL,
            ner_labels_json TEXT NOT NULL,
            ner_threshold REAL NOT NULL,
            resolved_device TEXT NOT NULL,
            batch_size INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_text TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_mentions (
            cache_key TEXT NOT NULL,
            mention_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            label TEXT NOT NULL,
            start INTEGER NOT NULL,
            end INTEGER NOT NULL,
            score REAL NOT NULL,
            PRIMARY KEY (cache_key, mention_index),
            FOREIGN KEY(cache_key) REFERENCES entity_documents(cache_key) ON DELETE CASCADE
        )
        """
    )
    connection.commit()


def make_entity_cache_key(text, config, resolved_device):
    """
    Build a stable key from text, NER config, and resolved device.

    PARAMETERS:
    - text: Clean article text
    - config: Entity metric config
    - resolved_device: cpu or mps

    RETURNS:
    - SHA256 hex string
    """
    cache_input = {
        "text": str(text),
        "ner_backend": config["ner_backend"],
        "ner_model": config["ner_model"],
        "ner_labels": list(config["ner_labels"]),
        "ner_threshold": config["ner_threshold"],
        "entity_processing_version": config.get("entity_processing_version", "full-text-v1"),
        "entity_window_tokens": config.get("entity_window_tokens", 0),
        "entity_window_overlap_tokens": config.get("entity_window_overlap_tokens", 0),
        "resolved_device": resolved_device,
    }
    cache_text = json.dumps(cache_input, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(cache_text.encode("utf-8")).hexdigest()


def hash_text(text):
    """
    Hash plain text for metadata and debugging.
    """
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def utc_now_text():
    """
    Return an ISO UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def write_entity_record(
    connection,
    cache_key,
    article_id,
    content_hash,
    text,
    config,
    resolved_device,
    batch_size,
    entities,
):
    """
    Write one ready entity document and its mentions.
    """
    existing_row = get_document_row(connection, cache_key)
    created_at = utc_now_text()
    if existing_row is not None:
        created_at = existing_row["created_at"]
    updated_at = utc_now_text()

    connection.execute("DELETE FROM entity_mentions WHERE cache_key = ?", (cache_key,))
    connection.execute(
        """
        INSERT OR REPLACE INTO entity_documents (
            cache_key,
            article_id,
            content_hash,
            text_hash,
            text_character_count,
            ner_backend,
            ner_model,
            ner_labels_json,
            ner_threshold,
            resolved_device,
            batch_size,
            status,
            error_text,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cache_key,
            article_id,
            content_hash,
            hash_text(text),
            len(str(text)),
            config["ner_backend"],
            config["ner_model"],
            json.dumps(list(config["ner_labels"]), ensure_ascii=False),
            float(config["ner_threshold"]),
            resolved_device,
            int(batch_size),
            "ready",
            "",
            created_at,
            updated_at,
        ),
    )

    for position, entity in enumerate(entities):
        connection.execute(
            """
            INSERT INTO entity_mentions (
                cache_key,
                mention_index,
                text,
                normalized_text,
                label,
                start,
                end,
                score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                position,
                entity["text"],
                entity["normalized_text"],
                entity["label"],
                int(entity["start"]),
                int(entity["end"]),
                float(entity["score"]),
            ),
        )

    connection.commit()


def write_entity_error(
    connection,
    cache_key,
    article_id,
    content_hash,
    text,
    config,
    resolved_device,
    batch_size,
    error_text,
):
    """
    Write one failed entity document.
    """
    existing_row = get_document_row(connection, cache_key)
    created_at = utc_now_text()
    if existing_row is not None:
        created_at = existing_row["created_at"]
    updated_at = utc_now_text()

    connection.execute("DELETE FROM entity_mentions WHERE cache_key = ?", (cache_key,))
    connection.execute(
        """
        INSERT OR REPLACE INTO entity_documents (
            cache_key,
            article_id,
            content_hash,
            text_hash,
            text_character_count,
            ner_backend,
            ner_model,
            ner_labels_json,
            ner_threshold,
            resolved_device,
            batch_size,
            status,
            error_text,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cache_key,
            article_id,
            content_hash,
            hash_text(text),
            len(str(text)),
            config["ner_backend"],
            config["ner_model"],
            json.dumps(list(config["ner_labels"]), ensure_ascii=False),
            float(config["ner_threshold"]),
            resolved_device,
            int(batch_size),
            "error",
            str(error_text),
            created_at,
            updated_at,
        ),
    )
    connection.commit()


def get_document_row(connection, cache_key):
    """
    Read one document row by cache key.
    """
    return connection.execute(
        """
        SELECT *
        FROM entity_documents
        WHERE cache_key = ?
        """,
        (cache_key,),
    ).fetchone()


def get_cached_entities(connection, cache_key):
    """
    Read ready entity mentions for one cache key.

    RETURNS:
    - List of entity dictionaries, or None when not ready
    """
    row = get_document_row(connection, cache_key)
    if row is None:
        return None

    if row["status"] != "ready":
        return None

    mention_rows = connection.execute(
        """
        SELECT text, normalized_text, label, start, end, score
        FROM entity_mentions
        WHERE cache_key = ?
        ORDER BY mention_index
        """,
        (cache_key,),
    ).fetchall()

    entities = []
    for mention_row in mention_rows:
        entities.append(
            {
                "text": mention_row["text"],
                "normalized_text": mention_row["normalized_text"],
                "label": mention_row["label"],
                "start": mention_row["start"],
                "end": mention_row["end"],
                "score": mention_row["score"],
            }
        )

    return entities
