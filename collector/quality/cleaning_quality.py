"""
Passive quality checks for cleaned news articles.

This module compares raw article files from:
    shared_data/corpus/news/raw/articles/

Against cleaned article files from:
    shared_data/corpus/news/clean/articles/

It writes quality-control reports to:
    shared_data/quality_reports/news_cleaning/

The checks are passive. They report problems, but they do not modify raw files,
clean files, or stop the corpus pipeline.
"""

from datetime import datetime
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import html
import hashlib
import json
import random
import re

from collector.cleaning.clean_articles import CLEAN_ARTICLES_DIR
from collector.cleaning.clean_articles import RAW_ARTICLES_DIR
from collector.cleaning.clean_articles import extract_text_for_cleaning
from collector.cleaning.clean_articles import get_article_link
from collector.cleaning.clean_articles import get_article_source


QUALITY_REPORTS_DIR = Path("shared_data/quality_reports/news_cleaning")
DEFAULT_SAMPLE_PER_SOURCE = 10
DEFAULT_SAMPLE_MODE = "suspicious"
DEFAULT_RANDOM_SEED = 42
DEFAULT_MINIMUM_TEXT_CHARACTERS = 300
DEFAULT_MAX_EXCERPT_CHARACTERS = 3000
DEFAULT_REVIEW_EXCERPT_CHARACTERS = 500
VALID_SAMPLE_MODES = ["suspicious", "random", "newest", "shortest", "longest"]

HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9]*(\s+[^>]*)?>")
WHITESPACE_PATTERN = re.compile(r"\s+")
WORD_PATTERN = re.compile(r"\b[\wÀ-ÿ'-]+\b", re.UNICODE)
SENTENCE_PATTERN = re.compile(r"[.!?]+")

BOILERPLATE_PHRASES = [
    "accept cookies",
    "aceitar cookies",
    "cookie policy",
    "politica de cookies",
    "política de cookies",
    "privacy policy",
    "politica de privacidade",
    "política de privacidade",
    "subscreva",
    "subscribe to our newsletter",
    "newsletter",
    "all rights reserved",
    "todos os direitos reservados",
    "publicidade",
    "advertisement",
    "related articles",
    "leia tambem",
    "leia também",
]


def make_report_id():
    """
    Create a timestamp folder name for one quality run.

    PARAMETERS:
    - None

    RETURNS:
    - Timestamp text like 20260509T123000Z
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json_file(file_path):
    """
    Load one JSON file.

    PARAMETERS:
    - file_path: Path to a JSON file

    RETURNS:
    - Parsed JSON dictionary

    RAISES:
    - Any JSON or file read error
    """
    with file_path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def save_json_file(data, output_path):
    """
    Save one dictionary as a JSON file.

    PARAMETERS:
    - data: Dictionary to save
    - output_path: Destination file path

    RETURNS:
    - None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(data, output_file, ensure_ascii=False, indent=2)


def save_jsonl_file(rows, output_path):
    """
    Save a list of dictionaries as JSONL.

    PARAMETERS:
    - rows: List of dictionaries
    - output_path: Destination file path

    RETURNS:
    - None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, ensure_ascii=False))
            output_file.write("\n")


def normalize_source_name(source_name):
    """
    Normalize source text for comparisons.

    PARAMETERS:
    - source_name: Source name from raw or clean article data

    RETURNS:
    - Uppercase source name
    """
    if source_name is None:
        return "UNKNOWN"

    return str(source_name).strip().upper()


def get_clean_article_path(article_id, clean_dir=CLEAN_ARTICLES_DIR):
    """
    Build the expected clean article path for one article ID.

    PARAMETERS:
    - article_id: Article ID from the raw file
    - clean_dir: Clean articles folder

    RETURNS:
    - Path to the expected clean article JSON file
    """
    return clean_dir / f"{article_id}.json"


def shorten_text(text, max_characters=DEFAULT_MAX_EXCERPT_CHARACTERS):
    """
    Make a text excerpt for reports and LLM judge queues.

    PARAMETERS:
    - text: Full text
    - max_characters: Maximum characters to keep

    RETURNS:
    - Shortened text
    """
    if not isinstance(text, str):
        return ""

    stripped_text = text.strip()

    if len(stripped_text) <= max_characters:
        return stripped_text

    return stripped_text[:max_characters] + "\n\n[TRUNCATED]"


def normalize_text_for_hash(text):
    """
    Normalize text before duplicate hashing.

    PARAMETERS:
    - text: Article text

    RETURNS:
    - Lowercase text with repeated whitespace collapsed
    """
    if not isinstance(text, str):
        return ""

    collapsed_text = WHITESPACE_PATTERN.sub(" ", text)
    return collapsed_text.strip().lower()


def create_text_hash(text):
    """
    Create a stable hash for cleaned article text.

    PARAMETERS:
    - text: Clean article text

    RETURNS:
    - SHA-256 hash string, or an empty string for blank text
    """
    normalized_text = normalize_text_for_hash(text)

    if normalized_text == "":
        return ""

    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def get_metadata_dictionary(article):
    """
    Safely read the metadata dictionary from an article.

    PARAMETERS:
    - article: Raw or clean article dictionary

    RETURNS:
    - Metadata dictionary, or an empty dictionary
    """
    metadata = article.get("metadata", {})

    if isinstance(metadata, dict):
        return metadata

    return {}


def get_first_text_value(article, keys):
    """
    Read the first non-empty text value from top-level fields or metadata.

    PARAMETERS:
    - article: Raw or clean article dictionary
    - keys: Field names to try

    RETURNS:
    - First non-empty string, or an empty string
    """
    metadata = get_metadata_dictionary(article)

    for key in keys:
        value = article.get(key, "")

        if isinstance(value, str) and value.strip() != "":
            return value.strip()

        metadata_value = metadata.get(key, "")

        if isinstance(metadata_value, str) and metadata_value.strip() != "":
            return metadata_value.strip()

    return ""


def get_article_title_for_quality(raw_article, clean_article=None):
    """
    Choose the best title available for quality reports.

    PARAMETERS:
    - raw_article: Raw article dictionary
    - clean_article: Clean article dictionary, or None

    RETURNS:
    - Article title string
    """
    title_keys = ["title", "headline", "name"]

    if isinstance(clean_article, dict):
        clean_title = get_first_text_value(clean_article, title_keys)

        if clean_title != "":
            return clean_title

    return get_first_text_value(raw_article, title_keys)


def get_published_at(raw_article):
    """
    Read a best-effort published timestamp from raw article data.

    PARAMETERS:
    - raw_article: Raw article dictionary

    RETURNS:
    - Timestamp text, or an empty string
    """
    return get_first_text_value(
        raw_article,
        [
            "published_at",
            "published",
            "published_date",
            "updated_at",
            "updated",
            "date",
        ],
    )


def get_scraped_at(raw_article):
    """
    Read the scrape timestamp from raw article data.

    PARAMETERS:
    - raw_article: Raw article dictionary

    RETURNS:
    - Timestamp text, or an empty string
    """
    return get_first_text_value(raw_article, ["scraped_at", "fetched_at"])


def get_cleaned_at(clean_article):
    """
    Read the clean timestamp from clean article data.

    PARAMETERS:
    - clean_article: Clean article dictionary

    RETURNS:
    - Timestamp text, or an empty string
    """
    if not isinstance(clean_article, dict):
        return ""

    return get_first_text_value(clean_article, ["cleaned_at"])


def parse_timestamp_to_epoch(timestamp_text):
    """
    Convert common timestamp text into a numeric epoch value.

    PARAMETERS:
    - timestamp_text: Timestamp text from RSS, scrape, or clean metadata

    RETURNS:
    - POSIX epoch seconds, or 0 when parsing fails
    """
    if not isinstance(timestamp_text, str) or timestamp_text.strip() == "":
        return 0

    clean_text = timestamp_text.strip()

    try:
        parsed_datetime = datetime.fromisoformat(clean_text.replace("Z", "+00:00"))

        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)

        return parsed_datetime.timestamp()
    except Exception:
        pass

    try:
        parsed_datetime = parsedate_to_datetime(clean_text)

        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)

        return parsed_datetime.timestamp()
    except Exception:
        return 0


def get_latest_known_epoch(published_epoch, scraped_epoch, cleaned_epoch):
    """
    Pick the latest available article timestamp.

    PARAMETERS:
    - published_epoch: Parsed published timestamp
    - scraped_epoch: Parsed scraped timestamp
    - cleaned_epoch: Parsed cleaned timestamp

    RETURNS:
    - Largest timestamp value
    """
    return max(published_epoch, scraped_epoch, cleaned_epoch)


def count_words(text):
    """
    Count words in a simple, language-agnostic way.

    PARAMETERS:
    - text: Text to inspect

    RETURNS:
    - Number of word-like tokens
    """
    if not isinstance(text, str):
        return 0

    return len(WORD_PATTERN.findall(text))


def count_sentences(text):
    """
    Count sentences using simple punctuation markers.

    PARAMETERS:
    - text: Text to inspect

    RETURNS:
    - Number of sentence-like segments
    """
    if not isinstance(text, str):
        return 0

    stripped_text = text.strip()

    if stripped_text == "":
        return 0

    matches = SENTENCE_PATTERN.findall(stripped_text)

    if len(matches) == 0:
        return 1

    return len(matches)


def calculate_average_sentence_length(word_count, sentence_count):
    """
    Calculate average sentence length in words.

    PARAMETERS:
    - word_count: Number of words
    - sentence_count: Number of sentences

    RETURNS:
    - Average words per sentence, or 0
    """
    if sentence_count <= 0:
        return 0

    return round(word_count / sentence_count, 2)


def count_html_tags(text):
    """
    Count HTML-like tags in text.

    PARAMETERS:
    - text: Text to inspect

    RETURNS:
    - Number of HTML-like tags
    """
    if not isinstance(text, str):
        return 0

    return len(HTML_TAG_PATTERN.findall(text))


def detect_language_hint(text):
    """
    Guess a rough language hint without external libraries.

    PARAMETERS:
    - text: Text to inspect

    RETURNS:
    - language_hint: Rough language label
    - language_confidence: Low-confidence score from 0 to 1
    """
    if not isinstance(text, str) or text.strip() == "":
        return "unknown", 0

    lower_text = text.lower()
    portuguese_score = 0
    english_score = 0
    portuguese_accent_characters = "ãõáéíóúçàâêô"
    portuguese_markers = [
        "ção",
        "ções",
        " que ",
        " não ",
        " para ",
        " uma ",
        " com ",
        " por ",
        " dos ",
        " das ",
        " está ",
    ]
    english_markers = [
        " the ",
        " and ",
        " that ",
        " with ",
        " for ",
        " from ",
        " this ",
        " are ",
        " was ",
        " have ",
    ]

    for marker in portuguese_markers:
        if marker in lower_text:
            portuguese_score = portuguese_score + 1

    for character in portuguese_accent_characters:
        if character in lower_text:
            portuguese_score = portuguese_score + 1
            break

    for marker in english_markers:
        if marker in lower_text:
            english_score = english_score + 1

    if portuguese_score == 0 and english_score == 0:
        return "unknown", 0

    total_score = portuguese_score + english_score

    if portuguese_score >= english_score:
        return "pt", round(portuguese_score / total_score, 2)

    return "en", round(english_score / total_score, 2)


def text_has_html_tags(text):
    """
    Check if text still appears to contain HTML tags.

    PARAMETERS:
    - text: Clean article text

    RETURNS:
    - True when HTML tags are found
    - False otherwise
    """
    if not isinstance(text, str):
        return False

    match = HTML_TAG_PATTERN.search(text)

    if match is None:
        return False

    return True


def find_boilerplate_phrases(text):
    """
    Find common cookie, newsletter, and navigation phrases.

    PARAMETERS:
    - text: Clean article text

    RETURNS:
    - List of detected boilerplate phrases
    """
    found_phrases = []

    if not isinstance(text, str):
        return found_phrases

    lower_text = text.lower()

    for phrase in BOILERPLATE_PHRASES:
        if phrase in lower_text:
            found_phrases.append(phrase)

    return found_phrases


def get_issue_severity(issues):
    """
    Convert issue names into an overall severity.

    PARAMETERS:
    - issues: List of deterministic issue names

    RETURNS:
    - severity: pass, warning, or error
    - severity_score: 0 for pass, 1 for warning, 2 for error
    """
    error_issues = [
        "missing_clean_file",
        "invalid_clean_json",
        "empty_clean_text",
        "clean_marked_invalid",
    ]

    for issue in issues:
        if issue in error_issues:
            return "error", 2

    if len(issues) > 0:
        return "warning", 1

    return "pass", 0


def get_recommended_action(issues):
    """
    Suggest a simple next action for a human operator.

    PARAMETERS:
    - issues: List of deterministic issue names

    RETURNS:
    - Recommended action text
    """
    if "missing_clean_file" in issues:
        return "reclean"

    if "invalid_clean_json" in issues:
        return "reclean"

    if "empty_clean_text" in issues or "clean_marked_invalid" in issues:
        return "refetch_or_reclean"

    if "contains_html_tags" in issues or "contains_boilerplate" in issues:
        return "inspect_source_cleaner"

    if "duplicate_clean_text" in issues:
        return "inspect_duplicate"

    if "short_clean_text" in issues:
        return "inspect_article"

    if len(issues) > 0:
        return "inspect_article"

    return "none"


def source_is_selected(source_name, selected_source_names, include_unlisted_sources):
    """
    Decide whether a source belongs in the quality run.

    PARAMETERS:
    - source_name: Source from the raw article
    - selected_source_names: Set of selected source names
    - include_unlisted_sources: True when all legacy sources are allowed

    RETURNS:
    - True when the article should be checked
    - False otherwise
    """
    normalized_source = normalize_source_name(source_name)

    if normalized_source in selected_source_names:
        return True

    if include_unlisted_sources:
        return True

    return False


def make_empty_source_stats():
    """
    Create an empty source statistics dictionary.

    PARAMETERS:
    - None

    RETURNS:
    - Dictionary with zeroed counters
    """
    return {
        "raw_articles": 0,
        "clean_articles": 0,
        "missing_clean_articles": 0,
        "invalid_clean_articles": 0,
        "checked_articles": 0,
        "passed_articles": 0,
        "articles_with_issues": 0,
        "sampled_for_llm_judge": 0,
        "clean_coverage_rate": 0,
        "deterministic_pass_rate": 0,
        "missing_clean_rate": 0,
        "invalid_clean_rate": 0,
        "issue_rate": 0,
        "llm_sample_rate": 0,
    }


def get_source_stats(source_stats, source_name):
    """
    Get or create statistics for one source.

    PARAMETERS:
    - source_stats: Dictionary keyed by source name
    - source_name: Source name

    RETURNS:
    - Statistics dictionary for the source
    """
    normalized_source = normalize_source_name(source_name)

    if normalized_source not in source_stats:
        source_stats[normalized_source] = make_empty_source_stats()

    return source_stats[normalized_source]


def check_clean_article(
    raw_article,
    clean_article,
    raw_path,
    clean_path,
    minimum_text_characters=DEFAULT_MINIMUM_TEXT_CHARACTERS,
):
    """
    Compare one raw article and one clean article.

    PARAMETERS:
    - raw_article: Raw article dictionary
    - clean_article: Clean article dictionary
    - raw_path: Path to the raw article JSON
    - clean_path: Path to the clean article JSON
    - minimum_text_characters: Minimum clean text length before warning

    RETURNS:
    - Quality check dictionary for this article
    """
    article_id = raw_article.get("id", raw_path.stem)
    raw_source = normalize_source_name(get_article_source(raw_article))
    clean_source = normalize_source_name(clean_article.get("source", "UNKNOWN"))
    raw_link = get_article_link(raw_article)
    clean_link = clean_article.get("link", "")
    raw_text, raw_text_kind = extract_text_for_cleaning(raw_article)
    clean_text = clean_article.get("text", "")
    clean_title = get_first_text_value(clean_article, ["title", "headline", "name"])
    title = get_article_title_for_quality(raw_article, clean_article)
    cleaner = clean_article.get("cleaner", "")
    published_at = get_published_at(raw_article)
    scraped_at = get_scraped_at(raw_article)
    cleaned_at = get_cleaned_at(clean_article)
    quality_checked_at = datetime.now(timezone.utc).isoformat()
    published_at_epoch = parse_timestamp_to_epoch(published_at)
    scraped_at_epoch = parse_timestamp_to_epoch(scraped_at)
    cleaned_at_epoch = parse_timestamp_to_epoch(cleaned_at)
    quality_checked_at_epoch = parse_timestamp_to_epoch(quality_checked_at)
    latest_known_at_epoch = get_latest_known_epoch(
        published_at_epoch,
        scraped_at_epoch,
        cleaned_at_epoch,
    )
    issues = []
    boilerplate_phrases = find_boilerplate_phrases(clean_text)
    html_tag_count = count_html_tags(clean_text)

    if clean_source != raw_source:
        issues.append("source_mismatch")

    if raw_link != "" and clean_link != "" and raw_link != clean_link:
        issues.append("link_mismatch")

    if clean_link == "":
        issues.append("missing_clean_link")

    if clean_title == "":
        issues.append("missing_title")

    if clean_article.get("is_valid_article") is False:
        issues.append("clean_marked_invalid")

    if not isinstance(clean_text, str) or clean_text.strip() == "":
        issues.append("empty_clean_text")
    elif len(clean_text.strip()) < minimum_text_characters:
        issues.append("short_clean_text")

    if html_tag_count > 0:
        issues.append("contains_html_tags")

    if len(boilerplate_phrases) > 0:
        issues.append("contains_boilerplate")

    raw_characters = 0
    clean_characters = 0
    clean_to_raw_ratio = None
    raw_word_count = count_words(raw_text)
    clean_word_count = count_words(clean_text)
    clean_sentence_count = count_sentences(clean_text)
    clean_average_sentence_length = calculate_average_sentence_length(
        clean_word_count,
        clean_sentence_count,
    )
    language_hint, language_confidence = detect_language_hint(clean_text)

    if isinstance(raw_text, str):
        raw_characters = len(raw_text.strip())

    if isinstance(clean_text, str):
        clean_characters = len(clean_text.strip())

    if raw_characters > 0:
        clean_to_raw_ratio = clean_characters / raw_characters

    sample_priority = len(issues)

    if clean_to_raw_ratio is not None:
        if clean_to_raw_ratio < 0.05:
            sample_priority = sample_priority + 1
        elif clean_to_raw_ratio > 1.20:
            sample_priority = sample_priority + 1

    severity, severity_score = get_issue_severity(issues)

    return {
        "article_id": article_id,
        "source": raw_source,
        "title": title,
        "link": raw_link,
        "published_at": published_at,
        "scraped_at": scraped_at,
        "cleaned_at": cleaned_at,
        "quality_checked_at": quality_checked_at,
        "published_at_epoch": published_at_epoch,
        "scraped_at_epoch": scraped_at_epoch,
        "cleaned_at_epoch": cleaned_at_epoch,
        "quality_checked_at_epoch": quality_checked_at_epoch,
        "latest_known_at_epoch": latest_known_at_epoch,
        "cleaner": cleaner,
        "raw_article_path": str(raw_path),
        "clean_article_path": str(clean_path),
        "raw_text_kind": raw_text_kind,
        "raw_excerpt": shorten_text(raw_text, DEFAULT_REVIEW_EXCERPT_CHARACTERS),
        "clean_excerpt": shorten_text(clean_text, DEFAULT_REVIEW_EXCERPT_CHARACTERS),
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
        "issues": issues,
        "severity": severity,
        "severity_score": severity_score,
        "boilerplate_phrases": boilerplate_phrases,
        "boilerplate_phrase_count": len(boilerplate_phrases),
        "html_tag_count": html_tag_count,
        "duplicate_group_size": 1,
        "is_llm_judge_sample": False,
        "review_status": "unreviewed",
        "review_notes": "",
        "recommended_action": get_recommended_action(issues),
        "issue_count": len(issues),
        "passed_deterministic_checks": len(issues) == 0,
        "sample_priority": sample_priority,
        "clean_file_modified_at": get_file_modified_time(clean_path),
    }


def get_file_modified_time(file_path):
    """
    Read a file modification timestamp.

    PARAMETERS:
    - file_path: Path to inspect

    RETURNS:
    - POSIX timestamp, or 0 if unavailable
    """
    try:
        return file_path.stat().st_mtime
    except Exception:
        return 0


def make_missing_clean_result(raw_article, raw_path, clean_path):
    """
    Create a quality result for a missing clean article file.

    PARAMETERS:
    - raw_article: Raw article dictionary
    - raw_path: Path to the raw article JSON
    - clean_path: Expected clean article path

    RETURNS:
    - Quality check dictionary
    """
    article_id = raw_article.get("id", raw_path.stem)
    source = normalize_source_name(get_article_source(raw_article))
    link = get_article_link(raw_article)
    title = get_article_title_for_quality(raw_article)
    published_at = get_published_at(raw_article)
    scraped_at = get_scraped_at(raw_article)
    cleaned_at = ""
    quality_checked_at = datetime.now(timezone.utc).isoformat()
    published_at_epoch = parse_timestamp_to_epoch(published_at)
    scraped_at_epoch = parse_timestamp_to_epoch(scraped_at)
    cleaned_at_epoch = 0
    quality_checked_at_epoch = parse_timestamp_to_epoch(quality_checked_at)
    latest_known_at_epoch = get_latest_known_epoch(
        published_at_epoch,
        scraped_at_epoch,
        cleaned_at_epoch,
    )
    raw_text, raw_text_kind = extract_text_for_cleaning(raw_article)
    raw_characters = 0
    raw_word_count = count_words(raw_text)
    issues = ["missing_clean_file"]
    severity, severity_score = get_issue_severity(issues)

    if isinstance(raw_text, str):
        raw_characters = len(raw_text.strip())

    return {
        "article_id": article_id,
        "source": source,
        "title": title,
        "link": link,
        "published_at": published_at,
        "scraped_at": scraped_at,
        "cleaned_at": cleaned_at,
        "quality_checked_at": quality_checked_at,
        "published_at_epoch": published_at_epoch,
        "scraped_at_epoch": scraped_at_epoch,
        "cleaned_at_epoch": cleaned_at_epoch,
        "quality_checked_at_epoch": quality_checked_at_epoch,
        "latest_known_at_epoch": latest_known_at_epoch,
        "cleaner": "",
        "raw_article_path": str(raw_path),
        "clean_article_path": str(clean_path),
        "raw_text_kind": raw_text_kind,
        "raw_excerpt": shorten_text(raw_text, DEFAULT_REVIEW_EXCERPT_CHARACTERS),
        "clean_excerpt": "",
        "raw_characters": raw_characters,
        "clean_characters": 0,
        "clean_to_raw_ratio": 0,
        "raw_word_count": raw_word_count,
        "clean_word_count": 0,
        "clean_sentence_count": 0,
        "clean_average_sentence_length": 0,
        "language_hint": "unknown",
        "language_confidence": 0,
        "clean_text_hash": "",
        "issues": issues,
        "severity": severity,
        "severity_score": severity_score,
        "boilerplate_phrases": [],
        "boilerplate_phrase_count": 0,
        "html_tag_count": 0,
        "duplicate_group_size": 0,
        "is_llm_judge_sample": False,
        "review_status": "unreviewed",
        "review_notes": "",
        "recommended_action": get_recommended_action(issues),
        "issue_count": 1,
        "passed_deterministic_checks": False,
        "sample_priority": 2,
        "clean_file_modified_at": 0,
    }


def make_invalid_clean_json_result(raw_article, raw_path, clean_path, error):
    """
    Create a quality result for an unreadable clean article file.

    PARAMETERS:
    - raw_article: Raw article dictionary
    - raw_path: Path to the raw article JSON
    - clean_path: Path to the invalid clean article JSON
    - error: Error raised while reading JSON

    RETURNS:
    - Quality check dictionary
    """
    result = make_missing_clean_result(raw_article, raw_path, clean_path)
    result["issues"] = ["invalid_clean_json"]
    result["issue_count"] = 1
    result["severity"], result["severity_score"] = get_issue_severity(result["issues"])
    result["recommended_action"] = get_recommended_action(result["issues"])
    result["error"] = str(error)
    return result


def add_duplicate_text_issues(article_results):
    """
    Mark articles that have the same cleaned text hash.

    PARAMETERS:
    - article_results: List of article quality dictionaries

    RETURNS:
    - None. The dictionaries are updated in place.
    """
    articles_by_hash = {}

    for result in article_results:
        text_hash = result.get("clean_text_hash", "")

        if text_hash == "":
            continue

        if text_hash not in articles_by_hash:
            articles_by_hash[text_hash] = []

        articles_by_hash[text_hash].append(result)

    for text_hash in articles_by_hash:
        duplicates = articles_by_hash[text_hash]

        if len(duplicates) <= 1:
            continue

        duplicate_ids = []

        for duplicate in duplicates:
            duplicate_ids.append(duplicate["article_id"])

        for duplicate in duplicates:
            if "duplicate_clean_text" not in duplicate["issues"]:
                duplicate["issues"].append("duplicate_clean_text")

            duplicate["issue_count"] = len(duplicate["issues"])
            duplicate["passed_deterministic_checks"] = False
            duplicate["duplicate_article_ids"] = duplicate_ids
            duplicate["duplicate_group_size"] = len(duplicate_ids)
            duplicate["severity"], duplicate["severity_score"] = get_issue_severity(
                duplicate["issues"]
            )
            duplicate["recommended_action"] = get_recommended_action(duplicate["issues"])
            duplicate["sample_priority"] = duplicate["sample_priority"] + 1


def build_article_quality_results(
    selected_sources,
    raw_dir=RAW_ARTICLES_DIR,
    clean_dir=CLEAN_ARTICLES_DIR,
    include_unlisted_sources=False,
    minimum_text_characters=DEFAULT_MINIMUM_TEXT_CHARACTERS,
):
    """
    Build deterministic quality results for selected sources.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries
    - raw_dir: Raw article folder
    - clean_dir: Clean article folder
    - include_unlisted_sources: True when unknown legacy sources are allowed
    - minimum_text_characters: Minimum clean text length before warning

    RETURNS:
    - article_results: List of quality result dictionaries
    - source_stats: Source-level statistics
    - counts: Overall counters
    """
    article_results = []
    source_stats = {}
    selected_source_names = set()
    counts = {
        "raw_files_seen": 0,
        "raw_files_selected": 0,
        "invalid_raw_json": 0,
        "skipped_source": 0,
        "clean_files_seen": 0,
        "missing_clean_files": 0,
        "invalid_clean_json": 0,
    }

    for source in selected_sources:
        selected_source_names.add(normalize_source_name(source["name"]))

    if not raw_dir.exists():
        print(f"[WARNING] Raw article directory does not exist: {raw_dir}")
        return article_results, source_stats, counts

    for raw_path in sorted(raw_dir.glob("*.json")):
        if raw_path.name.startswith("._"):
            continue

        counts["raw_files_seen"] = counts["raw_files_seen"] + 1

        try:
            raw_article = load_json_file(raw_path)
        except Exception as error:
            counts["invalid_raw_json"] = counts["invalid_raw_json"] + 1
            print(f"[WARNING] Could not read raw JSON: {raw_path}")
            print(f"[WARNING] Error: {error}")
            continue

        source_name = normalize_source_name(get_article_source(raw_article))

        if not source_is_selected(source_name, selected_source_names, include_unlisted_sources):
            counts["skipped_source"] = counts["skipped_source"] + 1
            continue

        counts["raw_files_selected"] = counts["raw_files_selected"] + 1
        stats = get_source_stats(source_stats, source_name)
        stats["raw_articles"] = stats["raw_articles"] + 1
        article_id = raw_article.get("id", raw_path.stem)
        clean_path = get_clean_article_path(article_id, clean_dir)

        if not clean_path.exists():
            counts["missing_clean_files"] = counts["missing_clean_files"] + 1
            stats["missing_clean_articles"] = stats["missing_clean_articles"] + 1
            result = make_missing_clean_result(raw_article, raw_path, clean_path)
            article_results.append(result)
            continue

        try:
            clean_article = load_json_file(clean_path)
        except Exception as error:
            counts["invalid_clean_json"] = counts["invalid_clean_json"] + 1
            stats["invalid_clean_articles"] = stats["invalid_clean_articles"] + 1
            result = make_invalid_clean_json_result(raw_article, raw_path, clean_path, error)
            article_results.append(result)
            continue

        counts["clean_files_seen"] = counts["clean_files_seen"] + 1
        stats["clean_articles"] = stats["clean_articles"] + 1
        result = check_clean_article(
            raw_article,
            clean_article,
            raw_path,
            clean_path,
            minimum_text_characters=minimum_text_characters,
        )
        article_results.append(result)

    add_duplicate_text_issues(article_results)
    refresh_source_stats_from_results(source_stats, article_results)

    return article_results, source_stats, counts


def refresh_source_stats_from_results(source_stats, article_results):
    """
    Fill pass/fail counters after all article checks are complete.

    PARAMETERS:
    - source_stats: Source-level statistics dictionary
    - article_results: Article quality result dictionaries

    RETURNS:
    - None. The source_stats dictionary is updated in place.
    """
    for result in article_results:
        stats = get_source_stats(source_stats, result["source"])
        stats["checked_articles"] = stats["checked_articles"] + 1

        if result["passed_deterministic_checks"]:
            stats["passed_articles"] = stats["passed_articles"] + 1
        else:
            stats["articles_with_issues"] = stats["articles_with_issues"] + 1


def group_results_by_source(article_results):
    """
    Group article quality results by source.

    PARAMETERS:
    - article_results: List of quality result dictionaries

    RETURNS:
    - Dictionary where keys are sources and values are lists of results
    """
    grouped_results = {}

    for result in article_results:
        source = result["source"]

        if source not in grouped_results:
            grouped_results[source] = []

        grouped_results[source].append(result)

    return grouped_results


def sort_results_for_sample(results, sample_mode, random_generator):
    """
    Sort article results for one sampling mode.

    PARAMETERS:
    - results: List of article quality dictionaries
    - sample_mode: suspicious, random, newest, shortest, or longest
    - random_generator: Random object with a fixed seed

    RETURNS:
    - Sorted list of article quality dictionaries
    """
    sorted_results = list(results)

    if sample_mode == "random":
        random_generator.shuffle(sorted_results)
    elif sample_mode == "newest":
        sorted_results.sort(key=get_newest_sort_value, reverse=True)
    elif sample_mode == "shortest":
        sorted_results.sort(key=get_shortest_sort_value)
    elif sample_mode == "longest":
        sorted_results.sort(key=get_longest_sort_value, reverse=True)
    else:
        sorted_results.sort(key=get_suspicious_sort_value, reverse=True)

    return sorted_results


def get_suspicious_sort_value(result):
    """
    Build a sort value for suspicious sampling.

    PARAMETERS:
    - result: Article quality dictionary

    RETURNS:
    - Tuple used by list.sort
    """
    return (
        result.get("sample_priority", 0),
        result.get("issue_count", 0),
        result.get("raw_characters", 0),
    )


def get_newest_sort_value(result):
    """
    Build a sort value for newest sampling.

    PARAMETERS:
    - result: Article quality dictionary

    RETURNS:
    - Latest known article timestamp
    """
    return result.get("latest_known_at_epoch", result.get("clean_file_modified_at", 0))


def get_shortest_sort_value(result):
    """
    Build a sort value for shortest cleaned articles.

    PARAMETERS:
    - result: Article quality dictionary

    RETURNS:
    - Clean text character count
    """
    return result.get("clean_characters", 0)


def get_longest_sort_value(result):
    """
    Build a sort value for longest cleaned articles.

    PARAMETERS:
    - result: Article quality dictionary

    RETURNS:
    - Clean text character count
    """
    return result.get("clean_characters", 0)


def choose_llm_judge_sample(
    article_results,
    sample_per_source=DEFAULT_SAMPLE_PER_SOURCE,
    sample_mode=DEFAULT_SAMPLE_MODE,
    random_seed=DEFAULT_RANDOM_SEED,
):
    """
    Choose articles to inspect with an LLM judge.

    PARAMETERS:
    - article_results: Article quality result dictionaries
    - sample_per_source: Maximum articles to sample per source
    - sample_mode: suspicious, random, newest, shortest, or longest
    - random_seed: Seed used for stable random samples

    RETURNS:
    - List of selected quality result dictionaries
    """
    sample = []
    grouped_results = group_results_by_source(article_results)
    random_generator = random.Random(random_seed)

    for source in sorted(grouped_results.keys()):
        source_results = grouped_results[source]
        sorted_results = sort_results_for_sample(source_results, sample_mode, random_generator)
        selected_count = 0

        for result in sorted_results:
            if selected_count >= sample_per_source:
                break

            sample.append(result)
            selected_count = selected_count + 1

    return sample


def build_llm_judge_prompt(raw_article, clean_article, quality_result):
    """
    Build one LLM-as-judge task.

    PARAMETERS:
    - raw_article: Raw article dictionary
    - clean_article: Clean article dictionary, or None when missing
    - quality_result: Deterministic quality result

    RETURNS:
    - Dictionary that can be saved to JSONL and sent to an LLM later
    """
    raw_text, raw_text_kind = extract_text_for_cleaning(raw_article)
    clean_text = ""

    if isinstance(clean_article, dict):
        clean_text = clean_article.get("text", "")

    return {
        "article_id": quality_result["article_id"],
        "source": quality_result["source"],
        "title": quality_result.get("title", ""),
        "link": quality_result.get("link", ""),
        "raw_article_path": quality_result["raw_article_path"],
        "clean_article_path": quality_result["clean_article_path"],
        "deterministic_issues": quality_result["issues"],
        "severity": quality_result.get("severity", "pass"),
        "recommended_action": quality_result.get("recommended_action", "none"),
        "raw_text_kind": raw_text_kind,
        "raw_excerpt": quality_result.get("raw_excerpt", shorten_text(raw_text)),
        "clean_excerpt": quality_result.get("clean_excerpt", shorten_text(clean_text)),
        "judge_instruction": (
            "Compare the raw article evidence with the cleaned text. "
            "Judge whether the cleaned text keeps the main article body, "
            "removes navigation/cookies/ads, avoids HTML noise, and does not "
            "drop important article content. Return only JSON."
        ),
        "expected_response_json": {
            "article_id": quality_result["article_id"],
            "source": quality_result["source"],
            "is_good_cleaning": True,
            "score": 4,
            "kept_main_article": True,
            "removed_boilerplate": True,
            "lost_important_content": False,
            "contains_html_or_noise": False,
            "notes": "Short explanation.",
        },
    }


def build_llm_judge_queue(sample_results):
    """
    Build JSONL rows for future LLM judging.

    PARAMETERS:
    - sample_results: Sampled quality result dictionaries

    RETURNS:
    - List of LLM judge task dictionaries
    """
    judge_rows = []

    for result in sample_results:
        try:
            raw_article = load_json_file(Path(result["raw_article_path"]))
        except Exception as error:
            print(f"[WARNING] Could not load raw article for judge queue: {result['raw_article_path']}")
            print(f"[WARNING] Error: {error}")
            continue

        clean_article = None
        clean_path = Path(result["clean_article_path"])

        if clean_path.exists():
            try:
                clean_article = load_json_file(clean_path)
            except Exception as error:
                print(f"[WARNING] Could not load clean article for judge queue: {clean_path}")
                print(f"[WARNING] Error: {error}")

        judge_row = build_llm_judge_prompt(raw_article, clean_article, result)
        judge_rows.append(judge_row)

    return judge_rows


def mark_llm_judge_samples(sample_results):
    """
    Mark sampled article result dictionaries in place.

    PARAMETERS:
    - sample_results: Article quality results selected for LLM judging

    RETURNS:
    - None
    """
    for result in sample_results:
        result["is_llm_judge_sample"] = True


def calculate_rate(numerator, denominator):
    """
    Calculate a rounded rate while avoiding divide-by-zero errors.

    PARAMETERS:
    - numerator: Top number
    - denominator: Bottom number

    RETURNS:
    - Rate between 0 and 1
    """
    if denominator <= 0:
        return 0

    return round(numerator / denominator, 4)


def add_source_rates(source_stats):
    """
    Add rate fields to every source statistics dictionary.

    PARAMETERS:
    - source_stats: Source-level statistics

    RETURNS:
    - None. The source_stats dictionary is updated in place.
    """
    for source in source_stats:
        stats = source_stats[source]
        raw_articles = stats["raw_articles"]
        checked_articles = stats["checked_articles"]

        stats["clean_coverage_rate"] = calculate_rate(stats["clean_articles"], raw_articles)
        stats["deterministic_pass_rate"] = calculate_rate(
            stats["passed_articles"],
            checked_articles,
        )
        stats["missing_clean_rate"] = calculate_rate(
            stats["missing_clean_articles"],
            raw_articles,
        )
        stats["invalid_clean_rate"] = calculate_rate(
            stats["invalid_clean_articles"],
            raw_articles,
        )
        stats["issue_rate"] = calculate_rate(stats["articles_with_issues"], checked_articles)
        stats["llm_sample_rate"] = calculate_rate(
            stats["sampled_for_llm_judge"],
            checked_articles,
        )


def build_total_rates(total_passed, total_with_issues, sample_count, counts):
    """
    Build overall quality rates for the run.

    PARAMETERS:
    - total_passed: Number of articles that passed deterministic checks
    - total_with_issues: Number of articles with deterministic issues
    - sample_count: Number of articles sampled for LLM judging
    - counts: Overall scan counters

    RETURNS:
    - Dictionary of run-level rates
    """
    selected_articles = counts["raw_files_selected"]
    checked_articles = total_passed + total_with_issues

    return {
        "clean_coverage_rate": calculate_rate(counts["clean_files_seen"], selected_articles),
        "deterministic_pass_rate": calculate_rate(total_passed, checked_articles),
        "missing_clean_rate": calculate_rate(counts["missing_clean_files"], selected_articles),
        "invalid_clean_rate": calculate_rate(counts["invalid_clean_json"], selected_articles),
        "issue_rate": calculate_rate(total_with_issues, checked_articles),
        "llm_sample_rate": calculate_rate(sample_count, checked_articles),
    }


def build_summary(article_results, source_stats, counts, sample_results, report_dir):
    """
    Build a run summary dictionary.

    PARAMETERS:
    - article_results: All article quality result dictionaries
    - source_stats: Source-level statistics
    - counts: Overall scan counters
    - sample_results: Articles sampled for LLM judging
    - report_dir: Output report folder

    RETURNS:
    - Summary dictionary
    """
    total_passed = 0
    total_with_issues = 0

    for result in article_results:
        if result["passed_deterministic_checks"]:
            total_passed = total_passed + 1
        else:
            total_with_issues = total_with_issues + 1

    for result in sample_results:
        stats = get_source_stats(source_stats, result["source"])
        stats["sampled_for_llm_judge"] = stats["sampled_for_llm_judge"] + 1

    add_source_rates(source_stats)
    total_rates = build_total_rates(
        total_passed,
        total_with_issues,
        len(sample_results),
        counts,
    )

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report_dir": str(report_dir),
        "totals": {
            "checked_articles": len(article_results),
            "passed_articles": total_passed,
            "articles_with_issues": total_with_issues,
            "sampled_for_llm_judge": len(sample_results),
            "rates": total_rates,
        },
        "scan_counts": counts,
        "sources": source_stats,
    }


def write_markdown_report(summary, output_path):
    """
    Write a small human-readable Markdown report.

    PARAMETERS:
    - summary: Summary dictionary
    - output_path: Destination Markdown path

    RETURNS:
    - None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    totals = summary["totals"]
    sources = summary["sources"]

    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write("# News Cleaning Quality Report\n\n")
        output_file.write(f"Created at: `{summary['created_at']}`\n\n")
        output_file.write("## Totals\n\n")
        output_file.write(f"- Checked articles: {totals['checked_articles']}\n")
        output_file.write(f"- Passed deterministic checks: {totals['passed_articles']}\n")
        output_file.write(f"- Articles with issues: {totals['articles_with_issues']}\n")
        output_file.write(f"- Sampled for LLM judge: {totals['sampled_for_llm_judge']}\n\n")
        output_file.write("## Rates\n\n")
        output_file.write(
            f"- Clean coverage rate: {format_rate_for_display(totals['rates']['clean_coverage_rate'])}\n"
        )
        output_file.write(
            f"- Deterministic pass rate: {format_rate_for_display(totals['rates']['deterministic_pass_rate'])}\n"
        )
        output_file.write(
            f"- Missing clean rate: {format_rate_for_display(totals['rates']['missing_clean_rate'])}\n"
        )
        output_file.write(f"- Issue rate: {format_rate_for_display(totals['rates']['issue_rate'])}\n\n")
        output_file.write("## Sources\n\n")
        output_file.write(
            "| Source | Raw | Clean | Missing Clean | Invalid Clean | Checked | Issues | Coverage | Pass Rate | Missing Rate | Invalid Rate | Issue Rate | LLM Sample |\n"
        )
        output_file.write(
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        )

        for source in sorted(sources.keys()):
            stats = sources[source]
            output_file.write(
                "| "
                + source
                + " | "
                + str(stats["raw_articles"])
                + " | "
                + str(stats["clean_articles"])
                + " | "
                + str(stats["missing_clean_articles"])
                + " | "
                + str(stats["invalid_clean_articles"])
                + " | "
                + str(stats["checked_articles"])
                + " | "
                + str(stats["articles_with_issues"])
                + " | "
                + format_rate_for_display(stats["clean_coverage_rate"])
                + " | "
                + format_rate_for_display(stats["deterministic_pass_rate"])
                + " | "
                + format_rate_for_display(stats["missing_clean_rate"])
                + " | "
                + format_rate_for_display(stats["invalid_clean_rate"])
                + " | "
                + format_rate_for_display(stats["issue_rate"])
                + " | "
                + str(stats["sampled_for_llm_judge"])
                + " |\n"
            )


def html_escape(value):
    """
    Escape a value so it is safe to place inside HTML.

    PARAMETERS:
    - value: Any value that should be displayed in HTML

    RETURNS:
    - Escaped text
    """
    if value is None:
        return ""

    return html.escape(str(value), quote=True)


def get_absolute_file_path(file_path):
    """
    Convert a report file path into an absolute local file path.

    PARAMETERS:
    - file_path: Raw or clean article path from a quality result

    RETURNS:
    - Absolute file path as text, or an empty string when no path is available
    """
    if file_path is None:
        return ""

    file_path_text = str(file_path).strip()

    if file_path_text == "":
        return ""

    path = Path(file_path_text).expanduser()

    if not path.is_absolute():
        path = path.resolve()

    return str(path)


def get_file_uri(file_path):
    """
    Build a browser file link for a local path.

    PARAMETERS:
    - file_path: Raw or clean article path from a quality result

    RETURNS:
    - file:// URL, or an empty string when no path is available
    """
    absolute_path = get_absolute_file_path(file_path)

    if absolute_path == "":
        return ""

    return Path(absolute_path).as_uri()


def get_sublime_uri(file_path):
    """
    Build a Sublime Text URL for a local path.

    PARAMETERS:
    - file_path: Raw or clean article path from a quality result

    RETURNS:
    - subl:// URL, or an empty string when no path is available
    """
    file_uri = get_file_uri(file_path)

    if file_uri == "":
        return ""

    return "subl://open?url=" + file_uri


def format_ratio_for_display(ratio):
    """
    Format a clean-to-raw ratio for reports.

    PARAMETERS:
    - ratio: Number or None

    RETURNS:
    - Short display string
    """
    if ratio is None:
        return ""

    try:
        return f"{float(ratio):.2f}"
    except Exception:
        return ""


def format_rate_for_display(rate):
    """
    Format a 0-to-1 rate as a percentage.

    PARAMETERS:
    - rate: Number between 0 and 1

    RETURNS:
    - Percentage display string
    """
    try:
        return f"{float(rate) * 100:.1f}%"
    except Exception:
        return ""


def format_epoch_for_table(epoch_value):
    """
    Format an epoch timestamp for compact table display.

    PARAMETERS:
    - epoch_value: Timestamp in POSIX seconds

    RETURNS:
    - Compact UTC timestamp text, or an empty string when unavailable
    """
    try:
        epoch_number = float(epoch_value)
    except Exception:
        return ""

    if epoch_number <= 0:
        return ""

    try:
        timestamp = datetime.fromtimestamp(epoch_number, timezone.utc)
        return timestamp.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ""


def write_html_file_actions(output_file, label, file_path):
    """
    Write open/copy actions for one local article JSON file.

    PARAMETERS:
    - output_file: Open HTML file handle
    - label: Human label such as Raw or Clean
    - file_path: File path to the local JSON file

    RETURNS:
    - None
    """
    copy_path = get_absolute_file_path(file_path)
    file_uri = get_file_uri(file_path)
    sublime_uri = get_sublime_uri(file_path)

    output_file.write("<div class=\"file-actions\"><strong>" + html_escape(label) + "</strong><br>")
    output_file.write("<code>" + html_escape(file_path) + "</code>")

    if copy_path == "":
        output_file.write("</div>")
        return

    output_file.write("<div class=\"file-action-row\">")
    output_file.write(
        "<a href=\""
        + html_escape(file_uri)
        + "\" target=\"_blank\" rel=\"noreferrer\">open file</a>"
    )
    output_file.write(
        "<a href=\""
        + html_escape(sublime_uri)
        + "\">open in Sublime</a>"
    )
    output_file.write(
        "<button type=\"button\" class=\"copy-path\" data-copy=\""
        + html_escape(copy_path)
        + "\">copy path</button>"
    )
    output_file.write("</div></div>")


def get_all_issue_names(article_results):
    """
    Collect every issue name found in article quality results.

    PARAMETERS:
    - article_results: Article quality result dictionaries

    RETURNS:
    - Sorted list of issue names
    """
    issue_names = set()

    for result in article_results:
        for issue in result.get("issues", []):
            issue_names.add(issue)

    return sorted(issue_names)


def get_sampled_article_ids(sample_results):
    """
    Collect sampled article IDs.

    PARAMETERS:
    - sample_results: Article quality results selected for LLM judging

    RETURNS:
    - Set of article IDs
    """
    sampled_ids = set()

    for result in sample_results:
        sampled_ids.add(result["article_id"])

    return sampled_ids


def write_html_report(summary, article_results, sample_results, output_path):
    """
    Write an interactive self-contained HTML quality report.

    PARAMETERS:
    - summary: Summary dictionary
    - article_results: Article quality result dictionaries
    - sample_results: Articles selected for LLM judge review
    - output_path: Destination HTML path

    RETURNS:
    - None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    totals = summary["totals"]
    sources = summary["sources"]
    issue_names = get_all_issue_names(article_results)
    sampled_ids = get_sampled_article_ids(sample_results)

    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write("<!doctype html>\n")
        output_file.write("<html lang=\"en\">\n")
        output_file.write("<head>\n")
        output_file.write("  <meta charset=\"utf-8\">\n")
        output_file.write(
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        )
        output_file.write("  <title>News Cleaning Quality Report</title>\n")
        output_file.write("  <style>\n")
        output_file.write(
            "    :root { color-scheme: light; --bg: #f7f7f4; --text: #1f2933; "
            "--muted: #64748b; --line: #d9ded7; --panel: #ffffff; "
            "--accent: #2563eb; --good: #15803d; --bad: #b91c1c; --warn: #b45309; }\n"
        )
        output_file.write(
            "    * { box-sizing: border-box; } body { margin: 0; background: var(--bg); "
            "color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "
            "'Segoe UI', sans-serif; font-size: 15px; line-height: 1.45; }\n"
        )
        output_file.write(
            "    header { padding: 28px 32px 18px; border-bottom: 1px solid var(--line); "
            "background: #eef2ee; } main { padding: 24px 32px 40px; }\n"
        )
        output_file.write(
            "    h1 { margin: 0 0 6px; font-size: 28px; letter-spacing: 0; } "
            "h2 { margin: 28px 0 12px; font-size: 18px; letter-spacing: 0; }\n"
        )
        output_file.write(
            "    .muted { color: var(--muted); } .grid { display: grid; "
            "grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }\n"
        )
        output_file.write(
            "    .card { background: var(--panel); border: 1px solid var(--line); "
            "border-radius: 8px; padding: 14px; } .number { font-size: 26px; "
            "font-weight: 700; margin-top: 4px; }\n"
        )
        output_file.write(
            "    .controls { display: grid; grid-template-columns: repeat(auto-fit, "
            "minmax(180px, 1fr)); gap: 12px; align-items: end; margin: 18px 0; }\n"
        )
        output_file.write(
            "    label { display: block; font-size: 12px; color: var(--muted); "
            "margin-bottom: 4px; } input, select { width: 100%; padding: 9px 10px; "
            "border: 1px solid var(--line); border-radius: 6px; background: white; "
            "font: inherit; }\n"
        )
        output_file.write(
            "    button { border: 1px solid var(--line); border-radius: 6px; "
            "background: #ffffff; color: var(--accent); font: inherit; "
            "font-size: 13px; padding: 5px 8px; cursor: pointer; }\n"
        )
        output_file.write(
            "    table { width: 100%; border-collapse: collapse; background: var(--panel); "
            "border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }\n"
        )
        output_file.write(
            "    th, td { padding: 9px 10px; border-bottom: 1px solid var(--line); "
            "vertical-align: top; text-align: left; } th { position: sticky; top: 0; "
            "background: #eef2ee; z-index: 1; font-size: 13px; }\n"
        )
        output_file.write(
            "    tr.hidden { display: none; } tr.issue-row { background: #fff8f1; } "
            "tr.pass-row { background: #f8fff9; }\n"
        )
        output_file.write(
            "    .badge { display: inline-block; padding: 2px 7px; border-radius: 999px; "
            "font-size: 12px; margin: 1px 3px 1px 0; border: 1px solid var(--line); "
            "background: #f8fafc; } .badge.good { color: var(--good); } "
            ".badge.bad { color: var(--bad); } .badge.warn { color: var(--warn); }\n"
        )
        output_file.write(
            "    details { max-width: 560px; } summary { cursor: pointer; color: "
            "var(--accent); } code { white-space: pre-wrap; word-break: break-word; "
            "font-size: 12px; color: #334155; }\n"
        )
        output_file.write(
            "    .source-table { max-width: 1100px; } .article-count { margin: 8px 0 12px; "
            "color: var(--muted); }\n"
        )
        output_file.write(
            "    .title-cell { min-width: 220px; max-width: 360px; } "
            ".timestamp-cell { min-width: 130px; max-width: 170px; } "
            ".excerpt { margin-top: 8px; padding: 8px; background: #f8fafc; "
            "border: 1px solid var(--line); border-radius: 6px; max-height: 180px; "
            "overflow: auto; }\n"
        )
        output_file.write(
            "    .file-actions { margin-top: 10px; } .file-action-row { display: flex; "
            "flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 6px; } "
            ".file-action-row a { color: var(--accent); font-size: 13px; }\n"
        )
        output_file.write("  </style>\n")
        output_file.write("</head>\n")
        output_file.write("<body>\n")
        output_file.write("<header>\n")
        output_file.write("  <h1>News Cleaning Quality Report</h1>\n")
        output_file.write(
            "  <div class=\"muted\">Created at "
            + html_escape(summary["created_at"])
            + "</div>\n"
        )
        output_file.write("</header>\n")
        output_file.write("<main>\n")
        output_file.write("  <section class=\"grid\">\n")
        output_file.write(
            "    <div class=\"card\"><div class=\"muted\">Checked Articles</div><div class=\"number\">"
            + html_escape(totals["checked_articles"])
            + "</div></div>\n"
        )
        output_file.write(
            "    <div class=\"card\"><div class=\"muted\">Passed Checks</div><div class=\"number\">"
            + html_escape(totals["passed_articles"])
            + "</div></div>\n"
        )
        output_file.write(
            "    <div class=\"card\"><div class=\"muted\">With Issues</div><div class=\"number\">"
            + html_escape(totals["articles_with_issues"])
            + "</div></div>\n"
        )
        output_file.write(
            "    <div class=\"card\"><div class=\"muted\">LLM Judge Sample</div><div class=\"number\">"
            + html_escape(totals["sampled_for_llm_judge"])
            + "</div></div>\n"
        )
        output_file.write(
            "    <div class=\"card\"><div class=\"muted\">Clean Coverage</div><div class=\"number\">"
            + html_escape(format_rate_for_display(totals["rates"]["clean_coverage_rate"]))
            + "</div></div>\n"
        )
        output_file.write(
            "    <div class=\"card\"><div class=\"muted\">Pass Rate</div><div class=\"number\">"
            + html_escape(format_rate_for_display(totals["rates"]["deterministic_pass_rate"]))
            + "</div></div>\n"
        )
        output_file.write("  </section>\n")
        output_file.write("  <h2>Source Summary</h2>\n")
        output_file.write("  <table class=\"source-table\">\n")
        output_file.write(
            "    <thead><tr><th>Source</th><th>Raw</th><th>Clean</th>"
            "<th>Missing Clean</th><th>Invalid Clean</th><th>Checked</th><th>Issues</th>"
            "<th>Coverage</th><th>Pass Rate</th><th>Missing Rate</th><th>Invalid Rate</th><th>Issue Rate</th>"
            "<th>LLM Sample</th></tr></thead>\n"
        )
        output_file.write("    <tbody>\n")

        for source in sorted(sources.keys()):
            stats = sources[source]
            output_file.write("      <tr>\n")
            output_file.write("        <td>" + html_escape(source) + "</td>\n")
            output_file.write("        <td>" + html_escape(stats["raw_articles"]) + "</td>\n")
            output_file.write("        <td>" + html_escape(stats["clean_articles"]) + "</td>\n")
            output_file.write(
                "        <td>" + html_escape(stats["missing_clean_articles"]) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(stats["invalid_clean_articles"]) + "</td>\n"
            )
            output_file.write("        <td>" + html_escape(stats["checked_articles"]) + "</td>\n")
            output_file.write(
                "        <td>" + html_escape(stats["articles_with_issues"]) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(format_rate_for_display(stats["clean_coverage_rate"])) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(format_rate_for_display(stats["deterministic_pass_rate"])) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(format_rate_for_display(stats["missing_clean_rate"])) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(format_rate_for_display(stats["invalid_clean_rate"])) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(format_rate_for_display(stats["issue_rate"])) + "</td>\n"
            )
            output_file.write(
                "        <td>" + html_escape(stats["sampled_for_llm_judge"]) + "</td>\n"
            )
            output_file.write("      </tr>\n")

        output_file.write("    </tbody>\n")
        output_file.write("  </table>\n")
        output_file.write("  <h2>Article Review</h2>\n")
        output_file.write("  <div class=\"controls\">\n")
        output_file.write("    <div><label for=\"sourceFilter\">Source</label><select id=\"sourceFilter\">\n")
        output_file.write("      <option value=\"all\">All sources</option>\n")

        for source in sorted(sources.keys()):
            output_file.write(
                "      <option value=\""
                + html_escape(source)
                + "\">"
                + html_escape(source)
                + "</option>\n"
            )

        output_file.write("    </select></div>\n")
        output_file.write("    <div><label for=\"issueFilter\">Issue</label><select id=\"issueFilter\">\n")
        output_file.write("      <option value=\"all\">All issues</option>\n")
        output_file.write("      <option value=\"passed\">Passed only</option>\n")
        output_file.write("      <option value=\"any_issue\">Any issue</option>\n")

        for issue_name in issue_names:
            output_file.write(
                "      <option value=\""
                + html_escape(issue_name)
                + "\">"
                + html_escape(issue_name)
                + "</option>\n"
            )

        output_file.write("    </select></div>\n")
        output_file.write(
            "    <div><label for=\"sampleFilter\">LLM Sample</label><select id=\"sampleFilter\">"
            "<option value=\"all\">All articles</option><option value=\"sampled\">Sampled only</option>"
            "</select></div>\n"
        )
        output_file.write(
            "    <div><label for=\"severityFilter\">Severity</label><select id=\"severityFilter\">"
            "<option value=\"all\">All severities</option><option value=\"error\">Error</option>"
            "<option value=\"warning\">Warning</option><option value=\"pass\">Pass</option>"
            "</select></div>\n"
        )
        output_file.write(
            "    <div><label for=\"actionFilter\">Action</label><select id=\"actionFilter\">"
            "<option value=\"all\">All actions</option><option value=\"none\">none</option>"
            "<option value=\"reclean\">reclean</option><option value=\"refetch_or_reclean\">refetch_or_reclean</option>"
            "<option value=\"inspect_source_cleaner\">inspect_source_cleaner</option>"
            "<option value=\"inspect_duplicate\">inspect_duplicate</option>"
            "<option value=\"inspect_article\">inspect_article</option></select></div>\n"
        )
        output_file.write(
            "    <div><label for=\"sortFieldFilter\">Sort by</label><select id=\"sortFieldFilter\">"
            "<option value=\"latest\">Latest known timestamp</option>"
            "<option value=\"published\">Published timestamp</option>"
            "<option value=\"scraped\">Scraped timestamp</option>"
            "<option value=\"cleaned\">Cleaned timestamp</option>"
            "<option value=\"quality\">Quality check timestamp</option>"
            "<option value=\"severityScore\">Severity</option>"
            "<option value=\"issueCount\">Issue count</option>"
            "<option value=\"cleanChars\">Clean text length</option>"
            "</select></div>\n"
        )
        output_file.write(
            "    <div><label for=\"sortDirectionFilter\">Direction</label>"
            "<select id=\"sortDirectionFilter\">"
            "<option value=\"desc\">Descending</option>"
            "<option value=\"asc\">Ascending</option>"
            "</select></div>\n"
        )
        output_file.write(
            "    <div><label for=\"searchBox\">Search</label>"
            "<input id=\"searchBox\" type=\"search\" placeholder=\"Title, URL, article ID, path, issue\"></div>\n"
        )
        output_file.write("  </div>\n")
        output_file.write("  <div class=\"article-count\" id=\"visibleCount\"></div>\n")
        output_file.write("  <table id=\"articleTable\">\n")
        output_file.write(
            "    <thead><tr><th>Status</th><th>Source</th><th>Article</th>"
            "<th>Collected</th><th>Cleaned</th><th>Issues</th>"
            "<th>Cleaner</th><th>Metrics</th><th>Review</th></tr></thead>\n"
        )
        output_file.write("    <tbody>\n")

        for result in article_results:
            write_html_article_row(output_file, result, sampled_ids)

        output_file.write("    </tbody>\n")
        output_file.write("  </table>\n")
        output_file.write("</main>\n")
        output_file.write("<script>\n")
        output_file.write(
            "const sourceFilter = document.getElementById('sourceFilter');\n"
            "const issueFilter = document.getElementById('issueFilter');\n"
            "const sampleFilter = document.getElementById('sampleFilter');\n"
            "const severityFilter = document.getElementById('severityFilter');\n"
            "const actionFilter = document.getElementById('actionFilter');\n"
            "const sortFieldFilter = document.getElementById('sortFieldFilter');\n"
            "const sortDirectionFilter = document.getElementById('sortDirectionFilter');\n"
            "const searchBox = document.getElementById('searchBox');\n"
            "const visibleCount = document.getElementById('visibleCount');\n"
            "const tableBody = document.querySelector('#articleTable tbody');\n"
            "const rows = Array.from(document.querySelectorAll('#articleTable tbody tr'));\n"
            "const timestampFields = ['latest', 'published', 'scraped', 'cleaned', 'quality'];\n"
            "function numericValue(row, key) {\n"
            "  const value = Number(row.dataset[key] || 0);\n"
            "  if (Number.isNaN(value)) { return 0; }\n"
            "  return value;\n"
            "}\n"
            "function timestampIsMissing(sortField, value) {\n"
            "  return timestampFields.includes(sortField) && value <= 0;\n"
            "}\n"
            "function applySort() {\n"
            "  const sortField = sortFieldFilter.value;\n"
            "  const sortDirection = sortDirectionFilter.value;\n"
            "  const sortedRows = rows.slice().sort(function(left, right) {\n"
            "    const leftValue = numericValue(left, sortField);\n"
            "    const rightValue = numericValue(right, sortField);\n"
            "    const leftMissing = timestampIsMissing(sortField, leftValue);\n"
            "    const rightMissing = timestampIsMissing(sortField, rightValue);\n"
            "    if (leftMissing && !rightMissing) { return 1; }\n"
            "    if (!leftMissing && rightMissing) { return -1; }\n"
            "    if (sortDirection === 'asc') { return leftValue - rightValue; }\n"
            "    return rightValue - leftValue;\n"
            "  });\n"
            "  sortedRows.forEach(function(row) { tableBody.appendChild(row); });\n"
            "}\n"
            "function setCopyButtonText(button, text) {\n"
            "  const originalText = button.dataset.originalText || button.textContent;\n"
            "  button.dataset.originalText = originalText;\n"
            "  button.textContent = text;\n"
            "  window.setTimeout(function() { button.textContent = originalText; }, 1200);\n"
            "}\n"
            "function fallbackCopyText(text) {\n"
            "  const textarea = document.createElement('textarea');\n"
            "  textarea.value = text;\n"
            "  textarea.setAttribute('readonly', 'readonly');\n"
            "  textarea.style.position = 'fixed';\n"
            "  textarea.style.left = '-9999px';\n"
            "  document.body.appendChild(textarea);\n"
            "  textarea.select();\n"
            "  const copied = document.execCommand('copy');\n"
            "  document.body.removeChild(textarea);\n"
            "  return copied;\n"
            "}\n"
            "function copyPath(button) {\n"
            "  const text = button.dataset.copy || '';\n"
            "  if (text === '') { return; }\n"
            "  if (navigator.clipboard && window.isSecureContext) {\n"
            "    navigator.clipboard.writeText(text).then(function() {\n"
            "      setCopyButtonText(button, 'copied');\n"
            "    }).catch(function() {\n"
            "      if (fallbackCopyText(text)) { setCopyButtonText(button, 'copied'); }\n"
            "      else { setCopyButtonText(button, 'copy failed'); }\n"
            "    });\n"
            "    return;\n"
            "  }\n"
            "  if (fallbackCopyText(text)) { setCopyButtonText(button, 'copied'); }\n"
            "  else { setCopyButtonText(button, 'copy failed'); }\n"
            "}\n"
            "function rowMatches(row) {\n"
            "  const sourceValue = sourceFilter.value;\n"
            "  const issueValue = issueFilter.value;\n"
            "  const sampleValue = sampleFilter.value;\n"
            "  const severityValue = severityFilter.value;\n"
            "  const actionValue = actionFilter.value;\n"
            "  const searchValue = searchBox.value.trim().toLowerCase();\n"
            "  if (sourceValue !== 'all' && row.dataset.source !== sourceValue) { return false; }\n"
            "  if (sampleValue === 'sampled' && row.dataset.sampled !== 'yes') { return false; }\n"
            "  if (severityValue !== 'all' && row.dataset.severity !== severityValue) { return false; }\n"
            "  if (actionValue !== 'all' && row.dataset.action !== actionValue) { return false; }\n"
            "  if (issueValue === 'passed' && row.dataset.passed !== 'yes') { return false; }\n"
            "  if (issueValue === 'any_issue' && row.dataset.passed === 'yes') { return false; }\n"
            "  if (issueValue !== 'all' && issueValue !== 'passed' && issueValue !== 'any_issue') {\n"
            "    if (!row.dataset.issues.split(',').includes(issueValue)) { return false; }\n"
            "  }\n"
            "  if (searchValue !== '' && !row.dataset.search.includes(searchValue)) { return false; }\n"
            "  return true;\n"
            "}\n"
            "function applyFilters() {\n"
            "  applySort();\n"
            "  let shown = 0;\n"
            "  rows.forEach(function(row) {\n"
            "    if (rowMatches(row)) { row.classList.remove('hidden'); shown += 1; }\n"
            "    else { row.classList.add('hidden'); }\n"
            "  });\n"
            "  visibleCount.textContent = shown + ' of ' + rows.length + ' articles visible';\n"
            "}\n"
            "[sourceFilter, issueFilter, sampleFilter, severityFilter, actionFilter, sortFieldFilter, sortDirectionFilter, searchBox].forEach(function(element) {\n"
            "  element.addEventListener('input', applyFilters);\n"
            "});\n"
            "document.querySelectorAll('.copy-path').forEach(function(button) {\n"
            "  button.addEventListener('click', function() { copyPath(button); });\n"
            "});\n"
            "applyFilters();\n"
        )
        output_file.write("</script>\n")
        output_file.write("</body>\n")
        output_file.write("</html>\n")


def write_html_article_row(output_file, result, sampled_ids):
    """
    Write one article row in the HTML quality report.

    PARAMETERS:
    - output_file: Open HTML file handle
    - result: Article quality result dictionary
    - sampled_ids: Set of article IDs selected for LLM judging

    RETURNS:
    - None
    """
    article_id = result["article_id"]
    source = result["source"]
    title = result.get("title", "")
    link = result.get("link", "")
    issues = result.get("issues", [])
    severity = result.get("severity", "pass")
    recommended_action = result.get("recommended_action", "none")
    passed = result.get("passed_deterministic_checks", False)
    sampled = article_id in sampled_ids
    status_class = "pass-row"
    status_badge = "<span class=\"badge good\">passed</span>"

    if severity == "error":
        status_class = "issue-row"
        status_badge = "<span class=\"badge bad\">error</span>"
    elif severity == "warning":
        status_class = "issue-row"
        status_badge = "<span class=\"badge warn\">warning</span>"

    if sampled:
        status_badge = status_badge + " <span class=\"badge warn\">LLM sample</span>"

    issue_html = ""

    if len(issues) == 0:
        issue_html = "<span class=\"badge good\">none</span>"
    else:
        for issue in issues:
            issue_html = issue_html + "<span class=\"badge bad\">" + html_escape(issue) + "</span>"

    raw_characters = result.get("raw_characters", 0)
    clean_characters = result.get("clean_characters", 0)
    raw_word_count = result.get("raw_word_count", 0)
    clean_word_count = result.get("clean_word_count", 0)
    language_hint = result.get("language_hint", "unknown")
    cleaner = result.get("cleaner", "")
    ratio = format_ratio_for_display(result.get("clean_to_raw_ratio"))
    collected_display = format_epoch_for_table(result.get("scraped_at_epoch", 0))
    cleaned_display = format_epoch_for_table(result.get("cleaned_at_epoch", 0))
    collected_title = result.get("scraped_at", "")
    cleaned_title = result.get("cleaned_at", "")
    raw_path = result.get("raw_article_path", "")
    clean_path = result.get("clean_article_path", "")

    if collected_display == "":
        collected_display = collected_title

    if cleaned_display == "":
        cleaned_display = cleaned_title

    if collected_display == "":
        collected_display = "missing"

    if cleaned_display == "":
        cleaned_display = "missing"

    search_text = (
        article_id
        + " "
        + source
        + " "
        + title
        + " "
        + link
        + " "
        + " ".join(issues)
        + " "
        + severity
        + " "
        + recommended_action
        + " "
        + raw_path
        + " "
        + clean_path
    ).lower()

    output_file.write(
        "      <tr class=\""
        + status_class
        + "\" data-source=\""
        + html_escape(source)
        + "\" data-issues=\""
        + html_escape(",".join(issues))
        + "\" data-passed=\""
        + ("yes" if passed else "no")
        + "\" data-sampled=\""
        + ("yes" if sampled else "no")
        + "\" data-severity=\""
        + html_escape(severity)
        + "\" data-action=\""
        + html_escape(recommended_action)
        + "\" data-latest=\""
        + html_escape(result.get("latest_known_at_epoch", 0))
        + "\" data-published=\""
        + html_escape(result.get("published_at_epoch", 0))
        + "\" data-scraped=\""
        + html_escape(result.get("scraped_at_epoch", 0))
        + "\" data-cleaned=\""
        + html_escape(result.get("cleaned_at_epoch", 0))
        + "\" data-quality=\""
        + html_escape(result.get("quality_checked_at_epoch", 0))
        + "\" data-severity-score=\""
        + html_escape(result.get("severity_score", 0))
        + "\" data-issue-count=\""
        + html_escape(result.get("issue_count", 0))
        + "\" data-clean-chars=\""
        + html_escape(clean_characters)
        + "\" data-search=\""
        + html_escape(search_text)
        + "\">\n"
    )
    output_file.write("        <td>" + status_badge + "</td>\n")
    output_file.write("        <td>" + html_escape(source) + "</td>\n")
    output_file.write("        <td class=\"title-cell\">")
    output_file.write("<strong>" + html_escape(title) + "</strong><br>")
    output_file.write("<code>" + html_escape(article_id) + "</code>")

    if link != "":
        output_file.write(
            "<br><a href=\""
            + html_escape(link)
            + "\" target=\"_blank\" rel=\"noreferrer\">open article</a>"
        )

    output_file.write("</td>\n")
    output_file.write(
        "        <td class=\"timestamp-cell\"><code title=\""
        + html_escape(collected_title)
        + "\">"
        + html_escape(collected_display)
        + "</code></td>\n"
    )
    output_file.write(
        "        <td class=\"timestamp-cell\"><code title=\""
        + html_escape(cleaned_title)
        + "\">"
        + html_escape(cleaned_display)
        + "</code></td>\n"
    )
    output_file.write("        <td>" + issue_html + "</td>\n")
    output_file.write("        <td>" + html_escape(cleaner) + "</td>\n")
    output_file.write(
        "        <td>raw chars "
        + html_escape(raw_characters)
        + "<br>clean chars "
        + html_escape(clean_characters)
        + "<br>raw words "
        + html_escape(raw_word_count)
        + "<br>clean words "
        + html_escape(clean_word_count)
        + "<br>ratio "
        + html_escape(ratio)
        + "<br>language "
        + html_escape(language_hint)
        + "</td>\n"
    )
    output_file.write("        <td>")
    output_file.write("<div><strong>Action</strong><br>" + html_escape(recommended_action) + "</div>")
    output_file.write("<div><strong>Status</strong><br>" + html_escape(result.get("review_status", "")) + "</div>")
    output_file.write("<details><summary>details</summary>")
    output_file.write(
        "<div><strong>Published</strong><br><code>"
        + html_escape(result.get("published_at", ""))
        + "</code></div>"
    )
    output_file.write(
        "<div><strong>Scraped</strong><br><code>"
        + html_escape(result.get("scraped_at", ""))
        + "</code></div>"
    )
    output_file.write(
        "<div><strong>Cleaned</strong><br><code>"
        + html_escape(result.get("cleaned_at", ""))
        + "</code></div>"
    )
    output_file.write(
        "<div><strong>Raw Excerpt</strong><div class=\"excerpt\">"
        + html_escape(result.get("raw_excerpt", ""))
        + "</div></div>"
    )
    output_file.write(
        "<div><strong>Clean Excerpt</strong><div class=\"excerpt\">"
        + html_escape(result.get("clean_excerpt", ""))
        + "</div></div>"
    )
    write_html_file_actions(output_file, "Raw", raw_path)
    write_html_file_actions(output_file, "Clean", clean_path)

    if "duplicate_article_ids" in result:
        duplicate_ids = ", ".join(result["duplicate_article_ids"])
        output_file.write(
            "<div><strong>Duplicate IDs</strong><br><code>"
            + html_escape(duplicate_ids)
            + "</code></div>"
        )

    output_file.write("</details></td>\n")
    output_file.write("      </tr>\n")


def print_quality_summary(summary):
    """
    Print a concise quality summary for the terminal.

    PARAMETERS:
    - summary: Summary dictionary

    RETURNS:
    - None
    """
    totals = summary["totals"]

    print("[INFO] Cleaning quality summary")
    print(f"    checked articles: {totals['checked_articles']}")
    print(f"    passed deterministic checks: {totals['passed_articles']}")
    print(f"    articles with issues: {totals['articles_with_issues']}")
    print(f"    sampled for LLM judge: {totals['sampled_for_llm_judge']}")
    print(f"    report folder: {summary['report_dir']}")


def quality_cleaning(
    selected_sources,
    raw_dir=RAW_ARTICLES_DIR,
    clean_dir=CLEAN_ARTICLES_DIR,
    output_dir=None,
    include_unlisted_sources=False,
    sample_per_source=DEFAULT_SAMPLE_PER_SOURCE,
    sample_mode=DEFAULT_SAMPLE_MODE,
    random_seed=DEFAULT_RANDOM_SEED,
    minimum_text_characters=DEFAULT_MINIMUM_TEXT_CHARACTERS,
):
    """
    Run passive quality control for cleaned articles.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries
    - raw_dir: Raw article folder
    - clean_dir: Clean article folder
    - output_dir: Optional report folder. If None, create a timestamp folder.
    - include_unlisted_sources: True when all legacy sources are allowed
    - sample_per_source: Number of articles to sample per source for LLM judging
    - sample_mode: suspicious, random, newest, shortest, or longest
    - random_seed: Seed for stable random samples
    - minimum_text_characters: Minimum clean text length before warning

    RETURNS:
    - 0 when the passive report was written
    """
    print("[INFO] Collector step: quality-cleaning")
    print(f"[INFO] Sources selected: {len(selected_sources)}")
    print(f"[INFO] include unlisted legacy sources: {include_unlisted_sources}")
    print(f"[INFO] sample per source: {sample_per_source}")
    print(f"[INFO] sample mode: {sample_mode}")
    print(f"[INFO] minimum text characters: {minimum_text_characters}")

    if output_dir is None:
        report_dir = QUALITY_REPORTS_DIR / make_report_id()
    else:
        report_dir = Path(output_dir)

    article_results, source_stats, counts = build_article_quality_results(
        selected_sources,
        raw_dir=raw_dir,
        clean_dir=clean_dir,
        include_unlisted_sources=include_unlisted_sources,
        minimum_text_characters=minimum_text_characters,
    )
    sample_results = choose_llm_judge_sample(
        article_results,
        sample_per_source=sample_per_source,
        sample_mode=sample_mode,
        random_seed=random_seed,
    )
    mark_llm_judge_samples(sample_results)
    judge_rows = build_llm_judge_queue(sample_results)
    summary = build_summary(article_results, source_stats, counts, sample_results, report_dir)

    save_json_file(summary, report_dir / "summary.json")
    save_jsonl_file(article_results, report_dir / "article_checks.jsonl")
    save_jsonl_file(judge_rows, report_dir / "llm_judge_queue.jsonl")
    write_markdown_report(summary, report_dir / "report.md")
    write_html_report(summary, article_results, sample_results, report_dir / "report.html")
    print_quality_summary(summary)

    return 0
