"""
Analyze one raw/clean article pair for the corpus inspector.
"""

from datetime import datetime
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import hashlib
import re

from collector.cleaning.clean_articles import extract_text_for_cleaning
from collector.cleaning.clean_articles import get_article_link
from collector.cleaning.clean_articles import get_article_source


DEFAULT_MINIMUM_TEXT_CHARACTERS = 300
DEFAULT_EXCERPT_CHARACTERS = 500

BOILERPLATE_PHRASES = [
    "accept cookies",
    "cookie policy",
    "cookies policy",
    "privacy policy",
    "subscribe to our newsletter",
    "newsletter",
    "sign up for our newsletter",
    "advertisement",
    "ad choices",
    "publicidade",
    "política de cookies",
    "politica de cookies",
    "política de privacidade",
    "politica de privacidade",
    "subscreva a nossa newsletter",
    "assine a nossa newsletter",
    "boletim informativo",
    "aceitar cookies",
]

ERROR_ISSUES = [
    "missing_raw_file",
    "missing_clean_file",
    "invalid_raw_json",
    "invalid_clean_json",
    "empty_clean_text",
    "clean_marked_invalid",
]


def normalize_source_name(source_name):
    """
    Normalize a source name for deterministic comparisons.
    """
    if source_name is None:
        return "UNKNOWN"

    normalized = str(source_name).strip().upper()

    if normalized == "":
        return "UNKNOWN"

    return normalized


def normalize_text_for_hash(text):
    """
    Normalize text before hashing so whitespace-only differences do not matter.
    """
    if text is None:
        return ""

    normalized = str(text).lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def create_text_hash(text):
    """
    Return a SHA-256 hash for normalized text, or blank for blank text.
    """
    normalized = normalize_text_for_hash(text)

    if normalized == "":
        return ""

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def shorten_text(text, max_characters):
    """
    Cap long text excerpts and mark the excerpt as truncated.
    """
    if text is None:
        text = ""

    text = str(text)

    if len(text) <= max_characters:
        return text

    return text[:max_characters] + "\n\n[TRUNCATED]"


def count_words(text):
    """
    Count words, including accented words and words with apostrophes.
    """
    if text is None:
        return 0

    matches = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+(?:'[0-9A-Za-zÀ-ÖØ-öø-ÿ]+)?", str(text))
    return len(matches)


def count_sentences(text):
    """
    Count sentence endings in text.
    """
    if text is None:
        return 0

    matches = re.findall(r"[.!?]+", str(text))
    return len(matches)


def calculate_average_sentence_length(word_count, sentence_count):
    """
    Calculate average words per sentence.
    """
    if sentence_count == 0:
        return None

    return round(word_count / sentence_count, 2)


def parse_timestamp_to_epoch(value):
    """
    Parse common article timestamp formats to Unix epoch seconds.
    """
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        iso_text = text
        if iso_text.endswith("Z"):
            iso_text = iso_text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def get_first_text_value(article, keys):
    """
    Return the first nonblank string value from an article dictionary.
    """
    if not isinstance(article, dict):
        return ""

    for key in keys:
        value = article.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()

    return ""


def get_metadata_value(article, key):
    """
    Return one value from article metadata if metadata is present.
    """
    if not isinstance(article, dict):
        return ""

    metadata = article.get("metadata", {})

    if not isinstance(metadata, dict):
        return ""

    value = metadata.get(key, "")

    if value is None:
        return ""

    return value


def get_title(raw_article, clean_article):
    """
    Prefer the clean article title, then raw top-level and metadata titles.
    """
    clean_title = get_first_text_value(clean_article, ["title", "headline", "name"])

    if clean_title != "":
        return clean_title

    raw_title = get_first_text_value(raw_article, ["title", "headline", "name"])

    if raw_title != "":
        return raw_title

    metadata_title = get_metadata_value(raw_article, "title")

    if metadata_title is None:
        return ""

    return str(metadata_title).strip()


def get_published_at(raw_article, clean_article):
    """
    Read the best available published timestamp.
    """
    value = get_first_text_value(clean_article, ["published_at", "published"])

    if value != "":
        return value

    value = get_first_text_value(raw_article, ["published_at", "published"])

    if value != "":
        return value

    value = get_metadata_value(raw_article, "published")

    if value == "":
        value = get_metadata_value(raw_article, "published_at")

    if value is None:
        return ""

    return str(value).strip()


def get_indexed_at(raw_article, clean_article):
    """
    Read the best available indexed timestamp.
    """
    value = get_first_text_value(clean_article, ["indexed_at"])

    if value != "":
        return value

    value = get_first_text_value(raw_article, ["indexed_at"])

    if value != "":
        return value

    value = get_metadata_value(raw_article, "indexed_at")

    if value is None:
        return ""

    return str(value).strip()


def get_scraped_at(raw_article):
    """
    Read the raw scrape timestamp.
    """
    value = get_first_text_value(raw_article, ["scraped_at"])

    if value != "":
        return value

    value = get_metadata_value(raw_article, "scraped_at")

    if value is None:
        return ""

    return str(value).strip()


def get_cleaned_at(clean_article):
    """
    Read the clean article timestamp.
    """
    value = get_first_text_value(clean_article, ["cleaned_at"])

    if value != "":
        return value

    value = get_metadata_value(clean_article, "cleaned_at")

    if value is None:
        return ""

    return str(value).strip()


def get_latest_epoch(*values):
    """
    Return the latest non-empty epoch value.
    """
    latest = None

    for value in values:
        if value is not None:
            if latest is None or value > latest:
                latest = value

    return latest


def count_html_tags(text):
    """
    Count simple HTML-looking tags in text.
    """
    if text is None:
        return 0

    matches = re.findall(r"<\s*/?\s*[A-Za-z][^>]*>", str(text))
    return len(matches)


def find_boilerplate_phrases(text):
    """
    Find known boilerplate phrases in text.
    """
    if text is None:
        return []

    lower_text = str(text).lower()
    found = []

    for phrase in BOILERPLATE_PHRASES:
        if phrase.lower() in lower_text:
            found.append(phrase)

    return found


def detect_language_hint(text):
    """
    Return a simple deterministic language hint.
    """
    if text is None or str(text).strip() == "":
        return "unknown", 0.0

    lower_text = str(text).lower()
    portuguese_markers = ["ção", "ções", "que", "para", "com", "não", "uma", "dos", "das"]
    english_markers = ["the", "and", "with", "for", "that", "this", "hotel", "visitors"]
    portuguese_count = 0
    english_count = 0

    for marker in portuguese_markers:
        if re.search(r"\b" + re.escape(marker) + r"\b", lower_text):
            portuguese_count = portuguese_count + 1

    for marker in english_markers:
        if re.search(r"\b" + re.escape(marker) + r"\b", lower_text):
            english_count = english_count + 1

    if portuguese_count > english_count and portuguese_count > 0:
        return "pt", 0.8

    if english_count > 0:
        return "en", 1.0

    return "unknown", 0.0


def severity_for_issues(issues):
    """
    Convert issue names to a severity and numeric score.
    """
    if len(issues) == 0:
        return "pass", 0

    for issue in issues:
        if issue in ERROR_ISSUES:
            return "error", 2

    return "warning", 1


def recommended_action_for_issues(issues):
    """
    Choose the next action for a human inspector.
    """
    if len(issues) == 0:
        return "none"

    for issue in issues:
        if issue in ["missing_clean_file", "invalid_clean_json", "clean_marked_invalid"]:
            return "reclean"

    for issue in issues:
        if issue in ["empty_clean_text", "short_clean_text"]:
            return "inspect_cleaner"

    return "review"


def get_file_modified_time(path):
    """
    Return file modified time as epoch seconds, or None when unavailable.
    """
    if path is None:
        return None

    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def analyze_article_pair(
    raw_article,
    clean_article,
    raw_path,
    clean_path,
    minimum_text_characters=DEFAULT_MINIMUM_TEXT_CHARACTERS,
):
    """
    Analyze one raw/clean article pair and return a flat dictionary for indexing.
    """
    if not isinstance(raw_article, dict):
        raw_article = {}

    if not isinstance(clean_article, dict):
        clean_article = {}

    raw_text, raw_text_kind = extract_text_for_cleaning(raw_article)
    clean_text = get_first_text_value(clean_article, ["text", "content", "body"])
    raw_source = get_article_source(raw_article)
    clean_source = get_article_source(clean_article)
    source = normalize_source_name(raw_source)
    raw_link = get_article_link(raw_article)
    clean_link = str(get_article_link(clean_article) or "").strip()
    link = clean_link

    if link == "":
        link = str(raw_link or "").strip()

    title = get_title(raw_article, clean_article)
    summary = get_first_text_value(clean_article, ["summary", "description"])
    published_at = get_published_at(raw_article, clean_article)
    indexed_at = get_indexed_at(raw_article, clean_article)
    scraped_at = get_scraped_at(raw_article)
    cleaned_at = get_cleaned_at(clean_article)
    published_at_epoch = parse_timestamp_to_epoch(published_at)
    indexed_at_epoch = parse_timestamp_to_epoch(indexed_at)
    scraped_at_epoch = parse_timestamp_to_epoch(scraped_at)
    cleaned_at_epoch = parse_timestamp_to_epoch(cleaned_at)
    raw_characters = len(raw_text)
    clean_characters = len(clean_text)
    raw_word_count = count_words(raw_text)
    clean_word_count = count_words(clean_text)
    clean_sentence_count = count_sentences(clean_text)
    clean_average_sentence_length = calculate_average_sentence_length(
        clean_word_count,
        clean_sentence_count,
    )
    html_tag_count = count_html_tags(clean_text)
    boilerplate_phrases = find_boilerplate_phrases(clean_text)
    language_hint, language_confidence = detect_language_hint(clean_text)
    is_valid_article = clean_article.get("is_valid_article")
    issues = []

    if normalize_source_name(clean_source) != normalize_source_name(raw_source):
        issues.append("source_mismatch")

    if str(raw_link or "").strip() != "" and clean_link != "":
        if str(raw_link or "").strip() != clean_link:
            issues.append("link_mismatch")

    if clean_link == "":
        issues.append("missing_clean_link")

    if get_first_text_value(clean_article, ["title", "headline", "name"]) == "":
        issues.append("missing_title")

    if is_valid_article is False:
        issues.append("clean_marked_invalid")

    if clean_text.strip() == "":
        issues.append("empty_clean_text")
    elif len(clean_text) < minimum_text_characters:
        issues.append("short_clean_text")

    if html_tag_count > 0:
        issues.append("contains_html_tags")

    if len(boilerplate_phrases) > 0:
        issues.append("contains_boilerplate")

    severity, severity_score = severity_for_issues(issues)
    clean_to_raw_ratio = None

    if raw_characters > 0:
        clean_to_raw_ratio = round(clean_characters / raw_characters, 4)

    raw_article_id = str(raw_article.get("id", "") or "").strip()
    raw_path_stem = str(Path(raw_path).stem or "").strip()
    clean_article_id = str(clean_article.get("id", "") or "").strip()
    article_id = raw_article_id

    if article_id == "":
        article_id = raw_path_stem

    if article_id == "":
        article_id = clean_article_id

    return {
        "article_id": article_id,
        "source": source,
        "title": title,
        "link": link,
        "summary": summary,
        "published_at": published_at,
        "published_at_epoch": published_at_epoch,
        "scraped_at": scraped_at,
        "scraped_at_epoch": scraped_at_epoch,
        "indexed_at": indexed_at,
        "indexed_at_epoch": indexed_at_epoch,
        "cleaned_at": cleaned_at,
        "cleaned_at_epoch": cleaned_at_epoch,
        "latest_known_at_epoch": get_latest_epoch(
            published_at_epoch,
            scraped_at_epoch,
            indexed_at_epoch,
            cleaned_at_epoch,
        ),
        "cleaner": str(clean_article.get("cleaner", "") or ""),
        "raw_article_path": str(raw_path),
        "clean_article_path": str(clean_path),
        "has_raw_file": True,
        "has_clean_file": True,
        "raw_json_valid": True,
        "clean_json_valid": True,
        "is_valid_article": is_valid_article,
        "raw_text_kind": raw_text_kind,
        "raw_excerpt": shorten_text(raw_text, DEFAULT_EXCERPT_CHARACTERS),
        "clean_excerpt": shorten_text(clean_text, DEFAULT_EXCERPT_CHARACTERS),
        "raw_characters": raw_characters,
        "clean_characters": clean_characters,
        "clean_to_raw_ratio": clean_to_raw_ratio,
        "raw_word_count": raw_word_count,
        "clean_word_count": clean_word_count,
        "clean_sentence_count": clean_sentence_count,
        "clean_average_sentence_length": clean_average_sentence_length,
        "language_hint": language_hint,
        "language_confidence": language_confidence,
        "clean_text_hash": create_text_hash(clean_text),
        "duplicate_group_size": 1,
        "html_tag_count": html_tag_count,
        "boilerplate_phrases": boilerplate_phrases,
        "boilerplate_phrase_count": len(boilerplate_phrases),
        "issues": issues,
        "issue_count": len(issues),
        "severity": severity,
        "severity_score": severity_score,
        "recommended_action": recommended_action_for_issues(issues),
        "passed_deterministic_checks": len(issues) == 0,
        "raw_file_modified_at": get_file_modified_time(raw_path),
        "clean_file_modified_at": get_file_modified_time(clean_path),
    }
