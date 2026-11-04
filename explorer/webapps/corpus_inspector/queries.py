"""
SQLite query helpers for the corpus inspector.
"""

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote

from explorer.webapps.corpus_inspector.analyzer import shorten_text


MAX_PAGE_SIZE = 200
DETAIL_PREVIEW_CHARACTERS = 20000

ALLOWED_SORTS = {
    "article_id": "article_id",
    "source": "source",
    "published_at": "published_at_epoch",
    "cleaned_at": "cleaned_at_epoch",
    "severity": "severity_score",
    "issue_count": "issue_count",
    "clean_characters": "clean_characters",
    "clean_to_raw_ratio": "clean_to_raw_ratio",
    "cleaner": "cleaner",
}

LIST_COLUMNS = [
    "article_id",
    "source",
    "title",
    "link",
    "published_at",
    "cleaned_at",
    "severity",
    "severity_score",
    "issue_count",
    "recommended_action",
    "cleaner",
    "raw_characters",
    "clean_characters",
    "clean_to_raw_ratio",
    "has_raw_file",
    "has_clean_file",
    "passed_deterministic_checks",
]


def connect(index_path):
    """
    Open the SQLite index with row dictionaries enabled.
    """
    connection = sqlite3.connect(index_path)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row):
    """
    Convert a SQLite row into a plain dictionary.
    """
    return dict(row)


def safe_int(value, default_value):
    """
    Parse an integer, returning a default when parsing fails.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def safe_float(value):
    """
    Parse a float, returning None when parsing fails.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def add_filter(clauses, values, field, operator, value):
    """
    Add a simple parameterized SQL filter.
    """
    clauses.append(field + " " + operator + " ?")
    values.append(value)


def build_filters(params):
    """
    Build a WHERE clause and parameter list from request-style filters.
    """
    if params is None:
        params = {}

    clauses = []
    values = []
    exact_filters = [
        "source",
        "severity",
        "cleaner",
        "language_hint",
        "recommended_action",
    ]

    for field in exact_filters:
        value = params.get(field)
        if value is not None and str(value).strip() != "":
            add_filter(clauses, values, field, "=", str(value).strip())

    bool_filters = [
        "has_clean_file",
        "has_raw_file",
        "is_valid_article",
    ]

    for field in bool_filters:
        value = params.get(field)
        if value == "0" or value == "1":
            add_filter(clauses, values, field, "=", int(value))

    issue = params.get("issue")
    if issue is not None and str(issue).strip() != "":
        clauses.append(
            """
            article_id IN (
                SELECT article_id
                FROM article_issues
                WHERE issue_name = ?
            )
            """
        )
        values.append(str(issue).strip())

    numeric_filters = [
        ("published_from", "published_at_epoch", ">="),
        ("published_to", "published_at_epoch", "<="),
        ("cleaned_from", "cleaned_at_epoch", ">="),
        ("cleaned_to", "cleaned_at_epoch", "<="),
        ("min_clean_characters", "clean_characters", ">="),
        ("max_clean_characters", "clean_characters", "<="),
        ("min_clean_to_raw_ratio", "clean_to_raw_ratio", ">="),
        ("max_clean_to_raw_ratio", "clean_to_raw_ratio", "<="),
    ]

    for param_name, field, operator in numeric_filters:
        value = safe_float(params.get(param_name))
        if value is not None:
            add_filter(clauses, values, field, operator, value)

    search = params.get("search")
    if search is not None and str(search).strip() != "":
        search_value = "%" + str(search).strip().lower() + "%"
        clauses.append(
            """
            (
                lower(article_id) LIKE ?
                OR lower(title) LIKE ?
                OR lower(link) LIKE ?
                OR lower(source) LIKE ?
                OR lower(clean_excerpt) LIKE ?
            )
            """
        )
        values.append(search_value)
        values.append(search_value)
        values.append(search_value)
        values.append(search_value)
        values.append(search_value)

    where_sql = ""
    if len(clauses) > 0:
        where_sql = "WHERE " + " AND ".join(clauses)

    return where_sql, values


def calculate_rate(count, total):
    """
    Return a simple rate for summary cards.
    """
    if total == 0:
        return 0

    return count / total


def get_summary(index_path):
    """
    Return corpus-level counts and rates.
    """
    connection = connect(index_path)

    try:
        total_articles = connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        raw_file_count = connection.execute("SELECT COUNT(*) FROM articles WHERE has_raw_file = 1").fetchone()[0]
        clean_file_count = connection.execute("SELECT COUNT(*) FROM articles WHERE has_clean_file = 1").fetchone()[0]
        invalid_raw_count = connection.execute("SELECT COUNT(*) FROM articles WHERE raw_json_valid = 0").fetchone()[0]
        invalid_clean_count = connection.execute("SELECT COUNT(*) FROM articles WHERE clean_json_valid = 0").fetchone()[0]
        missing_raw_count = connection.execute("SELECT COUNT(*) FROM articles WHERE has_raw_file = 0").fetchone()[0]
        missing_clean_count = connection.execute("SELECT COUNT(*) FROM articles WHERE has_clean_file = 0").fetchone()[0]
        passed_count = connection.execute("SELECT COUNT(*) FROM articles WHERE passed_deterministic_checks = 1").fetchone()[0]
        issue_count = connection.execute("SELECT COUNT(*) FROM article_issues").fetchone()[0]
        duplicate_article_count = connection.execute("SELECT COUNT(*) FROM articles WHERE duplicate_group_size > 1").fetchone()[0]
        source_count = connection.execute("SELECT COUNT(DISTINCT source) FROM articles WHERE source IS NOT NULL AND source != ''").fetchone()[0]
        cleaner_count = connection.execute("SELECT COUNT(DISTINCT cleaner) FROM articles WHERE cleaner IS NOT NULL AND cleaner != ''").fetchone()[0]
        articles_with_issues = connection.execute("SELECT COUNT(*) FROM articles WHERE issue_count > 0").fetchone()[0]
    finally:
        connection.close()

    return {
        "total_articles": total_articles,
        "raw_file_count": raw_file_count,
        "clean_file_count": clean_file_count,
        "invalid_raw_count": invalid_raw_count,
        "invalid_clean_count": invalid_clean_count,
        "missing_raw_count": missing_raw_count,
        "missing_clean_count": missing_clean_count,
        "passed_count": passed_count,
        "issue_count": issue_count,
        "duplicate_article_count": duplicate_article_count,
        "source_count": source_count,
        "cleaner_count": cleaner_count,
        "clean_coverage_rate": calculate_rate(clean_file_count, total_articles),
        "pass_rate": calculate_rate(passed_count, total_articles),
        "issue_rate": calculate_rate(articles_with_issues, total_articles),
    }


def get_article_page(index_path, params):
    """
    Return one filtered and sorted page of article rows.
    """
    if params is None:
        params = {}

    page = safe_int(params.get("page"), 1)
    page_size = safe_int(params.get("page_size"), 50)
    sort = params.get("sort", "article_id")
    direction = str(params.get("direction", "asc")).lower()

    if page < 1:
        page = 1

    if page_size < 1:
        page_size = 50

    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    if sort not in ALLOWED_SORTS:
        raise ValueError("Unknown sort field: " + str(sort))

    if direction != "asc" and direction != "desc":
        raise ValueError("Unknown sort direction: " + str(direction))

    where_sql, values = build_filters(params)
    offset = (page - 1) * page_size
    select_sql = ", ".join(LIST_COLUMNS)
    sort_column = ALLOWED_SORTS[sort]
    connection = connect(index_path)

    try:
        total_row = connection.execute(
            "SELECT COUNT(*) FROM articles " + where_sql,
            values,
        ).fetchone()
        rows = connection.execute(
            """
            SELECT """ + select_sql + """
            FROM articles
            """ + where_sql + """
            ORDER BY """ + sort_column + """ IS NULL ASC,
                """ + sort_column + " " + direction.upper() + """,
                article_id ASC
            LIMIT ? OFFSET ?
            """,
            values + [page_size, offset],
        ).fetchall()
    finally:
        connection.close()

    return {
        "page": page,
        "page_size": page_size,
        "total": total_row[0],
        "rows": [row_to_dict(row) for row in rows],
    }


def count_field(connection, field, where_sql, values):
    """
    Return grouped counts for one article field, excluding blank values.
    """
    rows = connection.execute(
        """
        SELECT """ + field + """ AS value, COUNT(*) AS count
        FROM articles
        """ + where_sql + """
        GROUP BY """ + field + """
        ORDER BY count DESC, value ASC
        """,
        values,
    ).fetchall()
    counts = {}

    for row in rows:
        value = row["value"]
        if value is not None and str(value).strip() != "":
            counts[value] = row["count"]

    return counts


def get_facets(index_path, params):
    """
    Return grouped counts for filtered article rows.
    """
    where_sql, values = build_filters(params)
    connection = connect(index_path)

    try:
        facets = {
            "sources": count_field(connection, "source", where_sql, values),
            "severities": count_field(connection, "severity", where_sql, values),
            "cleaners": count_field(connection, "cleaner", where_sql, values),
            "language_hints": count_field(connection, "language_hint", where_sql, values),
            "recommended_actions": count_field(connection, "recommended_action", where_sql, values),
            "issues": {},
        }
        issue_rows = connection.execute(
            """
            SELECT issue_name, COUNT(*) AS count
            FROM article_issues
            WHERE article_id IN (
                SELECT article_id
                FROM articles
                """ + where_sql + """
            )
            GROUP BY issue_name
            ORDER BY count DESC, issue_name ASC
            """,
            values,
        ).fetchall()
    finally:
        connection.close()

    for row in issue_rows:
        if row["issue_name"] is not None and str(row["issue_name"]).strip() != "":
            facets["issues"][row["issue_name"]] = row["count"]

    return facets


def load_json_text(path):
    """
    Load article text from JSON and shorten it for detail previews.
    """
    if path is None or str(path).strip() == "":
        return ""

    try:
        with Path(path).open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return ""

    if not isinstance(data, dict):
        return ""

    scrapingbee = data.get("scrapingbee", {})
    candidates = [
        data.get("text"),
        data.get("content"),
        data.get("body"),
    ]

    if isinstance(scrapingbee, dict):
        candidates.append(scrapingbee.get("content"))
        candidates.append(scrapingbee.get("body"))

    text = ""
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip() != "":
            text = candidate
            break

    return shorten_text(text, DETAIL_PREVIEW_CHARACTERS)


def get_article_detail(index_path, article_id):
    """
    Return one article row with issues, boilerplate phrases, and file previews.
    """
    article_id = unquote(str(article_id))
    connection = connect(index_path)

    try:
        article_row = connection.execute(
            "SELECT * FROM articles WHERE article_id = ?",
            (article_id,),
        ).fetchone()

        if article_row is None:
            raise KeyError(article_id)

        article = row_to_dict(article_row)
        issue_rows = connection.execute(
            """
            SELECT issue_name
            FROM article_issues
            WHERE article_id = ?
            ORDER BY issue_name ASC
            """,
            (article_id,),
        ).fetchall()
        phrase_rows = connection.execute(
            """
            SELECT phrase
            FROM article_boilerplate_phrases
            WHERE article_id = ?
            ORDER BY phrase ASC
            """,
            (article_id,),
        ).fetchall()
    finally:
        connection.close()

    issues = []
    for row in issue_rows:
        issues.append(row["issue_name"])

    boilerplate_phrases = []
    for row in phrase_rows:
        boilerplate_phrases.append(row["phrase"])

    return {
        "article": article,
        "issues": issues,
        "boilerplate_phrases": boilerplate_phrases,
        "raw_preview": load_json_text(article.get("raw_article_path")),
        "clean_preview": load_json_text(article.get("clean_article_path")),
    }
