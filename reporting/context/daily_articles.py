"""
Load and filter clean articles for report generation.
"""

import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


def parse_report_datetime(value):
    """
    Parse a report date or datetime as UTC.
    """
    if not value:
        return datetime.now(timezone.utc)

    raw = str(value).strip()

    if len(raw) == 10:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
        return parsed.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_article_datetime(article):
    """
    Parse the best available article timestamp.
    """
    metadata = article.get("metadata", {}) or {}
    candidates = [
        article.get("published_at", ""),
        article.get("date", ""),
        article.get("published", ""),
        article.get("updated", ""),
        metadata.get("published_at", ""),
        metadata.get("date", ""),
        metadata.get("published", ""),
        metadata.get("updated", ""),
    ]

    for value in candidates:
        if not value:
            continue
        raw = str(value).strip()
        try:
            return parse_report_datetime(raw)
        except Exception:
            try:
                parsed = parsedate_to_datetime(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except Exception:
                continue

    return None


def load_clean_articles(input_folder):
    """
    Load clean article JSON files from one folder.
    """
    input_path = Path(input_folder)
    articles = []

    if not input_path.exists():
        return articles

    for article_path in sorted(input_path.glob("*.json")):
        try:
            text = article_path.read_text(encoding="utf-8")
            article = json.loads(text)
            article["_input_path"] = str(article_path)
            articles.append(article)
        except Exception as error:
            print(f"[WARNING] Skipping unreadable article {article_path}: {error}")

    return articles


def get_selected_row_datetime(row):
    """
    Return the parsed timestamp from one selected article row.
    """
    return row["article_time"]


def select_articles_for_window(articles, report_datetime, hours):
    """
    Keep articles inside the report look-back window.
    """
    report_time = parse_report_datetime(report_datetime)
    window_start = report_time - timedelta(hours=hours)
    selected_rows = []

    for article in articles:
        article_time = parse_article_datetime(article)
        if article_time is None:
            continue
        if window_start <= article_time <= report_time:
            selected_rows.append({"article_time": article_time, "article": article})

    selected_rows.sort(key=get_selected_row_datetime, reverse=True)

    selected = []
    for row in selected_rows:
        selected.append(row["article"])

    return selected


def select_articles_for_report_day(articles, report_datetime):
    """
    Keep articles from the selected report calendar day only.
    """
    report_time = parse_report_datetime(report_datetime)
    report_date = report_time.date()
    selected_rows = []

    for article in articles:
        article_time = parse_article_datetime(article)
        if article_time is None:
            continue
        if article_time.date() == report_date and article_time <= report_time:
            selected_rows.append({"article_time": article_time, "article": article})

    selected_rows.sort(key=get_selected_row_datetime, reverse=True)

    selected = []
    for row in selected_rows:
        selected.append(row["article"])

    return selected


def get_article_id(article):
    """
    Return a stable article id for manifests and source numbering.
    """
    for key in ["id", "article_id", "fingerprint"]:
        value = article.get(key)
        if value:
            return str(value)

    metadata = article.get("metadata", {}) or {}
    for key in ["id", "fingerprint", "link", "url"]:
        value = metadata.get(key)
        if value:
            return str(value)

    input_path = article.get("_input_path", "")
    if input_path:
        return Path(input_path).stem

    return "unknown_article"


def get_article_text(article):
    """
    Return the best text field for report context.
    """
    metadata = article.get("metadata", {}) or {}
    candidates = [
        article.get("text", ""),
        article.get("clean_text", ""),
        article.get("content", ""),
        metadata.get("summary", ""),
    ]

    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()

    return "(no content available)"
