"""
Build and inspect the corpus inspector SQLite index.
"""

import json
import sqlite3
from datetime import datetime
from datetime import timezone
from pathlib import Path

from collector.cleaning.clean_articles import CLEAN_ARTICLES_DIR
from collector.cleaning.clean_articles import get_article_link
from collector.cleaning.clean_articles import get_article_source
from collector.cleaning.clean_articles import RAW_ARTICLES_DIR
from explorer.webapps.corpus_inspector.analyzer import analyze_article_pair
from explorer.webapps.corpus_inspector.analyzer import recommended_action_for_issues
from explorer.webapps.corpus_inspector.analyzer import severity_for_issues


DEFAULT_INDEX_PATH = Path("shared_data/explorer/corpus_inspector/index.sqlite")

ARTICLE_COLUMNS = [
    "article_id",
    "source",
    "title",
    "link",
    "summary",
    "raw_article_path",
    "clean_article_path",
    "has_raw_file",
    "has_clean_file",
    "raw_json_valid",
    "clean_json_valid",
    "is_valid_article",
    "cleaner",
    "published_at",
    "published_at_epoch",
    "scraped_at",
    "scraped_at_epoch",
    "indexed_at",
    "indexed_at_epoch",
    "cleaned_at",
    "cleaned_at_epoch",
    "latest_known_at_epoch",
    "raw_characters",
    "clean_characters",
    "raw_word_count",
    "clean_word_count",
    "clean_to_raw_ratio",
    "clean_sentence_count",
    "clean_average_sentence_length",
    "language_hint",
    "language_confidence",
    "clean_text_hash",
    "duplicate_group_size",
    "html_tag_count",
    "boilerplate_phrase_count",
    "issue_count",
    "severity",
    "severity_score",
    "recommended_action",
    "passed_deterministic_checks",
    "raw_excerpt",
    "clean_excerpt",
    "raw_file_modified_at",
    "clean_file_modified_at",
]


def load_json_file(path):
    """
    Load a UTF-8 JSON file.
    """
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def create_schema(connection):
    """
    Recreate the corpus inspector SQLite schema.
    """
    connection.execute("DROP TABLE IF EXISTS articles")
    connection.execute("DROP TABLE IF EXISTS article_issues")
    connection.execute("DROP TABLE IF EXISTS article_boilerplate_phrases")
    connection.execute("DROP TABLE IF EXISTS index_metadata")

    connection.execute(
        """
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            link TEXT,
            summary TEXT,
            raw_article_path TEXT,
            clean_article_path TEXT,
            has_raw_file INTEGER,
            has_clean_file INTEGER,
            raw_json_valid INTEGER,
            clean_json_valid INTEGER,
            is_valid_article INTEGER,
            cleaner TEXT,
            published_at TEXT,
            published_at_epoch REAL,
            scraped_at TEXT,
            scraped_at_epoch REAL,
            indexed_at TEXT,
            indexed_at_epoch REAL,
            cleaned_at TEXT,
            cleaned_at_epoch REAL,
            latest_known_at_epoch REAL,
            raw_characters INTEGER,
            clean_characters INTEGER,
            raw_word_count INTEGER,
            clean_word_count INTEGER,
            clean_to_raw_ratio REAL,
            clean_sentence_count INTEGER,
            clean_average_sentence_length REAL,
            language_hint TEXT,
            language_confidence REAL,
            clean_text_hash TEXT,
            duplicate_group_size INTEGER,
            html_tag_count INTEGER,
            boilerplate_phrase_count INTEGER,
            issue_count INTEGER,
            severity TEXT,
            severity_score INTEGER,
            recommended_action TEXT,
            passed_deterministic_checks INTEGER,
            raw_excerpt TEXT,
            clean_excerpt TEXT,
            raw_file_modified_at REAL,
            clean_file_modified_at REAL
        )
        """
    )
    connection.execute("CREATE TABLE article_issues (article_id TEXT, issue_name TEXT)")
    connection.execute("CREATE INDEX article_issues_issue_name ON article_issues (issue_name)")
    connection.execute("CREATE TABLE article_boilerplate_phrases (article_id TEXT, phrase TEXT)")
    connection.execute("CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("CREATE INDEX articles_source ON articles (source)")
    connection.execute("CREATE INDEX articles_severity ON articles (severity)")
    connection.execute("CREATE INDEX articles_cleaner ON articles (cleaner)")
    connection.execute("CREATE INDEX articles_published_at_epoch ON articles (published_at_epoch)")
    connection.execute("CREATE INDEX articles_cleaned_at_epoch ON articles (cleaned_at_epoch)")
    connection.execute("CREATE INDEX articles_clean_text_hash ON articles (clean_text_hash)")


def normalize_bool(value):
    """
    Convert Python boolean-like values into SQLite integer flags.
    """
    if value is None:
        return None

    if value:
        return 1

    return 0


def get_file_modified_time(path):
    """
    Return file modified time as epoch seconds, or None when unavailable.
    """
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def make_empty_article_result(article_id, raw_path, clean_path):
    """
    Return a complete article result with default values.
    """
    raw_exists = Path(raw_path).exists()
    clean_exists = Path(clean_path).exists()

    return {
        "article_id": article_id,
        "source": "UNKNOWN",
        "title": "Untitled",
        "link": "",
        "summary": "",
        "raw_article_path": str(raw_path),
        "clean_article_path": str(clean_path),
        "has_raw_file": raw_exists,
        "has_clean_file": clean_exists,
        "raw_json_valid": raw_exists,
        "clean_json_valid": clean_exists,
        "is_valid_article": None,
        "cleaner": "",
        "published_at": "",
        "published_at_epoch": None,
        "scraped_at": "",
        "scraped_at_epoch": None,
        "indexed_at": "",
        "indexed_at_epoch": None,
        "cleaned_at": "",
        "cleaned_at_epoch": None,
        "latest_known_at_epoch": None,
        "raw_characters": 0,
        "clean_characters": 0,
        "raw_word_count": 0,
        "clean_word_count": 0,
        "clean_to_raw_ratio": None,
        "clean_sentence_count": 0,
        "clean_average_sentence_length": None,
        "language_hint": "unknown",
        "language_confidence": 0.0,
        "clean_text_hash": "",
        "duplicate_group_size": 1,
        "html_tag_count": 0,
        "boilerplate_phrase_count": 0,
        "issue_count": 0,
        "severity": "pass",
        "severity_score": 0,
        "recommended_action": "none",
        "passed_deterministic_checks": True,
        "raw_excerpt": "",
        "clean_excerpt": "",
        "raw_file_modified_at": get_file_modified_time(raw_path),
        "clean_file_modified_at": get_file_modified_time(clean_path),
        "issues": [],
        "boilerplate_phrases": [],
    }


def set_result_issues(result, issues):
    """
    Store issue-derived fields on a result dictionary.
    """
    severity, severity_score = severity_for_issues(issues)
    result["issues"] = issues
    result["issue_count"] = len(issues)
    result["severity"] = severity
    result["severity_score"] = severity_score
    result["recommended_action"] = recommended_action_for_issues(issues)
    result["passed_deterministic_checks"] = len(issues) == 0
    return result


def make_missing_result(article_id, raw_path, clean_path, missing_issue):
    """
    Build an index result for an article with a missing raw or clean JSON file.
    """
    result = make_empty_article_result(article_id, raw_path, clean_path)
    return set_result_issues(result, [missing_issue])


def make_invalid_result(article_id, raw_path, clean_path, raw_valid, clean_valid):
    """
    Build an index result for an article with invalid raw or clean JSON.
    """
    issues = []
    result = make_empty_article_result(article_id, raw_path, clean_path)
    result["has_raw_file"] = Path(raw_path).exists()
    result["has_clean_file"] = Path(clean_path).exists()
    result["raw_json_valid"] = raw_valid
    result["clean_json_valid"] = clean_valid

    if not raw_valid:
        issues.append("invalid_raw_json")

    if not clean_valid:
        issues.append("invalid_clean_json")

    return set_result_issues(result, issues)


def make_raw_only_result(article_id, raw_article, raw_path, clean_path, minimum_text_characters):
    """
    Build an index result when raw JSON exists but clean JSON is missing.
    """
    if not isinstance(raw_article, dict):
        raw_article = {}

    result = analyze_article_pair(raw_article, {}, raw_path, clean_path, minimum_text_characters)
    result["article_id"] = article_id
    result["has_clean_file"] = False
    result["clean_json_valid"] = False
    result["clean_article_path"] = str(clean_path)
    result["clean_file_modified_at"] = get_file_modified_time(clean_path)
    return set_result_issues(result, ["missing_clean_file"])


def make_clean_only_result(article_id, clean_article, raw_path, clean_path, minimum_text_characters):
    """
    Build an index result when clean JSON exists but raw JSON is missing.
    """
    if not isinstance(clean_article, dict):
        clean_article = {}

    raw_stub = {
        "id": article_id,
        "source": get_article_source(clean_article),
        "link": get_article_link(clean_article),
        "metadata": clean_article.get("metadata", {}),
        "text": "",
    }
    result = analyze_article_pair(raw_stub, clean_article, raw_path, clean_path, minimum_text_characters)
    result["article_id"] = article_id
    result["has_raw_file"] = False
    result["raw_json_valid"] = False
    result["raw_article_path"] = str(raw_path)
    result["raw_characters"] = 0
    result["raw_word_count"] = 0
    result["raw_excerpt"] = ""
    result["raw_file_modified_at"] = get_file_modified_time(raw_path)
    return set_result_issues(result, ["missing_raw_file"])


def insert_article(connection, result):
    """
    Insert one analyzed article and its related issue rows.
    """
    bool_columns = [
        "has_raw_file",
        "has_clean_file",
        "raw_json_valid",
        "clean_json_valid",
        "is_valid_article",
        "passed_deterministic_checks",
    ]
    row = []

    for column in ARTICLE_COLUMNS:
        value = result.get(column)
        if column in bool_columns:
            value = normalize_bool(value)
        row.append(value)

    placeholders = ", ".join(["?"] * len(ARTICLE_COLUMNS))
    column_names = ", ".join(ARTICLE_COLUMNS)
    connection.execute(
        "INSERT INTO articles (" + column_names + ") VALUES (" + placeholders + ")",
        row,
    )

    issues = result.get("issues", [])
    for issue in issues:
        connection.execute(
            "INSERT INTO article_issues (article_id, issue_name) VALUES (?, ?)",
            (result["article_id"], issue),
        )

    phrases = result.get("boilerplate_phrases", [])
    for phrase in phrases:
        connection.execute(
            "INSERT INTO article_boilerplate_phrases (article_id, phrase) VALUES (?, ?)",
            (result["article_id"], phrase),
        )


def update_duplicate_groups(connection):
    """
    Mark duplicate clean text hash groups.
    """
    duplicate_rows = connection.execute(
        """
        SELECT clean_text_hash, COUNT(*) AS group_size
        FROM articles
        WHERE clean_text_hash IS NOT NULL AND clean_text_hash != ''
        GROUP BY clean_text_hash
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    for row in duplicate_rows:
        clean_text_hash = row[0]
        group_size = row[1]
        articles = connection.execute(
            "SELECT article_id FROM articles WHERE clean_text_hash = ?",
            (clean_text_hash,),
        ).fetchall()

        for article in articles:
            article_id = article[0]
            existing_issue = connection.execute(
                """
                SELECT 1 FROM article_issues
                WHERE article_id = ? AND issue_name = ?
                """,
                (article_id, "duplicate_clean_text"),
            ).fetchone()

            if existing_issue is None:
                connection.execute(
                    "INSERT INTO article_issues (article_id, issue_name) VALUES (?, ?)",
                    (article_id, "duplicate_clean_text"),
                )
                connection.execute(
                    """
                    UPDATE articles
                    SET issue_count = issue_count + 1
                    WHERE article_id = ?
                    """,
                    (article_id,),
                )

            connection.execute(
                """
                UPDATE articles
                SET duplicate_group_size = ?,
                    passed_deterministic_checks = 0
                WHERE article_id = ?
                """,
                (group_size, article_id),
            )
            connection.execute(
                """
                UPDATE articles
                SET severity = ?,
                    severity_score = ?,
                    recommended_action = ?
                WHERE article_id = ? AND severity = ?
                """,
                ("warning", 1, "review", article_id, "pass"),
            )


def write_metadata(connection, values):
    """
    Write index metadata values as strings.
    """
    for key in values:
        connection.execute(
            "INSERT INTO index_metadata (key, value) VALUES (?, ?)",
            (str(key), str(values[key])),
        )


def collect_json_paths(folder):
    """
    Return JSON files keyed by article id.
    """
    paths = {}

    if not folder.exists():
        return paths

    for path in folder.glob("*.json"):
        if path.name.startswith("._"):
            continue

        article_id = path.stem

        try:
            article = load_json_file(path)
            if isinstance(article, dict):
                file_article_id = str(article.get("id", "") or "").strip()
                if file_article_id != "":
                    article_id = file_article_id
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            article_id = path.stem

        paths[article_id] = path

    return paths


def read_json_if_present(path):
    """
    Read a JSON file and report whether it was valid.
    """
    if not path.exists():
        return None, False

    try:
        return load_json_file(path), True
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, False


def build_corpus_index(
    raw_dir=RAW_ARTICLES_DIR,
    clean_dir=CLEAN_ARTICLES_DIR,
    index_path=DEFAULT_INDEX_PATH,
    minimum_text_characters=300,
):
    """
    Build the SQLite index for raw and clean corpus article JSON files.
    """
    raw_dir = Path(raw_dir)
    clean_dir = Path(clean_dir)
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    print("[INFO] Building corpus inspector index")
    print("[INFO] Raw articles directory: " + str(raw_dir))
    print("[INFO] Clean articles directory: " + str(clean_dir))

    raw_paths = collect_json_paths(raw_dir)
    clean_paths = collect_json_paths(clean_dir)
    article_ids = sorted(set(raw_paths.keys()) | set(clean_paths.keys()))

    print("[INFO] Article ids found: " + str(len(article_ids)))

    connection = sqlite3.connect(index_path)
    article_count = 0

    try:
        create_schema(connection)

        for index in range(len(article_ids)):
            article_id = article_ids[index]
            raw_path = raw_paths.get(article_id, raw_dir / (article_id + ".json"))
            clean_path = clean_paths.get(article_id, clean_dir / (article_id + ".json"))

            if index == 0 or (index + 1) % 1000 == 0:
                print("[" + str(index + 1) + "/" + str(len(article_ids)) + "] Processing article: " + article_id)

            raw_article, raw_valid = read_json_if_present(raw_path)
            clean_article, clean_valid = read_json_if_present(clean_path)

            if not raw_path.exists() and not clean_path.exists():
                result = make_missing_result(article_id, raw_path, clean_path, "missing_raw_file")
            elif not raw_path.exists():
                if clean_valid:
                    result = make_clean_only_result(article_id, clean_article, raw_path, clean_path, minimum_text_characters)
                else:
                    result = make_missing_result(article_id, raw_path, clean_path, "missing_raw_file")
                    result = set_result_issues(result, ["missing_raw_file", "invalid_clean_json"])
                    result["clean_json_valid"] = False
            elif not clean_path.exists():
                if raw_valid:
                    result = make_raw_only_result(article_id, raw_article, raw_path, clean_path, minimum_text_characters)
                else:
                    result = make_missing_result(article_id, raw_path, clean_path, "missing_clean_file")
                    result = set_result_issues(result, ["missing_clean_file", "invalid_raw_json"])
                    result["raw_json_valid"] = False
            elif not raw_valid:
                result = make_invalid_result(article_id, raw_path, clean_path, False, clean_valid)
            elif not clean_valid:
                result = make_invalid_result(article_id, raw_path, clean_path, True, False)
            else:
                result = analyze_article_pair(
                    raw_article,
                    clean_article,
                    raw_path,
                    clean_path,
                    minimum_text_characters,
                )

            insert_article(connection, result)
            article_count = article_count + 1

        update_duplicate_groups(connection)
        article_count = connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        created_at = datetime.now(timezone.utc).isoformat()
        write_metadata(
            connection,
            {
                "created_at": created_at,
                "raw_dir": raw_dir,
                "clean_dir": clean_dir,
                "article_count": article_count,
                "raw_file_count": len(raw_paths),
                "clean_file_count": len(clean_paths),
                "minimum_text_characters": minimum_text_characters,
            },
        )
        connection.commit()
    finally:
        connection.close()

    print("[INFO] Corpus index written: " + str(index_path))

    return {
        "index_path": str(index_path),
        "article_count": article_count,
    }


def get_index_status(index_path=DEFAULT_INDEX_PATH):
    """
    Return basic index status.
    """
    index_path = Path(index_path)
    status = {
        "index_path": str(index_path),
        "exists": index_path.exists(),
        "article_count": 0,
    }

    if not index_path.exists():
        return status

    connection = sqlite3.connect(index_path)

    try:
        row = connection.execute("SELECT COUNT(*) FROM articles").fetchone()
        if row is not None:
            status["article_count"] = row[0]
    except sqlite3.Error:
        status["article_count"] = 0
    finally:
        connection.close()

    return status
