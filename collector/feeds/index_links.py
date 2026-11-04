"""
RSS link indexing.

This file reads RSS feeds and saves article links into:
    shared_data/corpus/news/raw/links/<SOURCE>/<timestamp>.jsonl

The code is intentionally explicit. Each source can be processed independently,
so the command can run sequentially for debugging or with threads for speed.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
import hashlib
import json

import feedparser


OUTPUT_DIR = Path("shared_data/corpus/news/raw/links")
DEFAULT_WORKERS = 8
DEFAULT_MAX_AGE_DAYS = 90


def create_fingerprint(title, link, published):
    """
    Create a stable duplicate-detection fingerprint for one RSS entry.

    PARAMETERS:
    - title: The article title
    - link: The article URL
    - published: The RSS published date text

    RETURNS:
    - A 64-character SHA-256 fingerprint string
    """
    fingerprint_text = title + "|" + link + "|" + published
    fingerprint_bytes = fingerprint_text.encode("utf-8")

    return hashlib.sha256(fingerprint_bytes).hexdigest()


def get_entry_value(entry, key, default_value):
    """
    Read one value from a feedparser entry.

    PARAMETERS:
    - entry: A feedparser entry or plain dictionary
    - key: The field name to read
    - default_value: The value to use when the field is missing

    RETURNS:
    - The entry value, or the default value when missing
    """
    try:
        value = entry.get(key, default_value)
    except AttributeError:
        value = default_value

    if value is None:
        return default_value

    return value


def is_article_fresh(published_parsed, max_age_days, now=None):
    """
    Decide whether an RSS entry is recent enough to keep.

    PARAMETERS:
    - published_parsed: A parsed RSS date tuple from feedparser
    - max_age_days: Maximum article age allowed
    - now: Optional datetime used by tests for stable results

    RETURNS:
    - True when the article should be kept
    - False when the article is older than max_age_days
    """
    # Missing dates are kept because many feeds have incomplete metadata.
    if published_parsed is None:
        return True

    try:
        published_datetime = datetime(
            published_parsed[0],
            published_parsed[1],
            published_parsed[2],
            published_parsed[3],
            published_parsed[4],
            published_parsed[5],
            tzinfo=timezone.utc,
        )

        if now is None:
            now = datetime.now(timezone.utc)

        article_age = now - published_datetime
        max_age = timedelta(days=max_age_days)

        if article_age > max_age:
            return False

        return True

    except Exception as error:
        print(f"[WARNING] Could not parse article date. Keeping article. Error: {error}")
        return True


def article_from_entry(entry, source_name, indexed_at):
    """
    Convert one RSS entry into the JSON shape used by this repo.

    PARAMETERS:
    - entry: A feedparser entry or plain dictionary
    - source_name: Canonical source name, such as PUBLICO
    - indexed_at: ISO timestamp for this indexing run

    RETURNS:
    - A plain dictionary ready to write as one JSONL line
    """
    title = get_entry_value(entry, "title", "")
    link = get_entry_value(entry, "link", "")
    published = get_entry_value(entry, "published", "")

    article = {
        "source": source_name,
        "title": title,
        "link": link,
        "published": published,
        "summary": get_entry_value(entry, "summary", ""),
        "author": get_entry_value(entry, "author", ""),
        "authors": get_entry_value(entry, "authors", []),
        "tags": get_entry_value(entry, "tags", []),
        "media_content": get_entry_value(entry, "media_content", []),
        "media_thumbnail": get_entry_value(entry, "media_thumbnail", []),
        "content": get_entry_value(entry, "content", []),
        "updated": get_entry_value(entry, "updated", ""),
        "feed_id": get_entry_value(entry, "id", ""),
        "fingerprint": create_fingerprint(title, link, published),
        "indexed_at": indexed_at,
    }

    return article


def parse_feed(source, max_age_days, indexed_at, now=None):
    """
    Parse one RSS feed and return fresh article dictionaries.

    PARAMETERS:
    - source: Source dictionary from collector.feeds.sources
    - max_age_days: Maximum article age allowed
    - indexed_at: ISO timestamp for this indexing run
    - now: Optional datetime used by tests for stable freshness checks

    RETURNS:
    - A result dictionary with parsed articles and skipped-stale counts
    """
    source_name = source["name"]
    feed_url = source["url"]

    print(f"[INFO] Parsing feed: {source_name}")
    print(f"       URL: {feed_url}")

    parsed_feed = feedparser.parse(feed_url)
    entries = get_entry_value(parsed_feed, "entries", [])
    status = get_entry_value(parsed_feed, "status", None)
    bozo = get_entry_value(parsed_feed, "bozo", False)
    bozo_exception = get_entry_value(parsed_feed, "bozo_exception", None)

    status_number = None

    if status is not None:
        try:
            status_number = int(status)
        except (TypeError, ValueError):
            status_number = None

    if status_number is not None and status_number >= 400:
        raise ValueError(f"Feed parse failed for {source_name}: HTTP status {status_number}")

    if bozo and len(entries) == 0:
        if bozo_exception is None:
            raise ValueError(f"Feed parse failed for {source_name}: bozo parse error")

        raise ValueError(f"Feed parse failed for {source_name}: {bozo_exception}")

    if bozo:
        print(f"[WARNING] Feed parser warning for {source_name}: {bozo_exception}")

    articles = []
    skipped_stale = 0

    for entry in entries:
        published_parsed = get_entry_value(entry, "published_parsed", None)
        published = get_entry_value(entry, "published", "")

        if published_parsed is None and published != "":
            print(
                f"[WARNING] Could not parse published date for {source_name}. "
                f"Keeping article. Published text: {published}"
            )

        if is_article_fresh(published_parsed, max_age_days, now):
            article = article_from_entry(entry, source_name, indexed_at)
            articles.append(article)
        else:
            skipped_stale = skipped_stale + 1

    result = {
        "source": source_name,
        "status": "PARSED",
        "articles": articles,
        "article_count": len(articles),
        "skipped_stale": skipped_stale,
        "error": None,
    }

    return result


def get_source_output_path(source_name, timestamp_text, output_dir=OUTPUT_DIR):
    """
    Build the JSONL output path for one source.

    PARAMETERS:
    - source_name: Canonical source name, such as PUBLICO
    - timestamp_text: Timestamp text for the current run
    - output_dir: Base output folder

    RETURNS:
    - A pathlib Path ending in <SOURCE>/<timestamp>.jsonl
    """
    return output_dir / source_name / f"{timestamp_text}.jsonl"


def write_articles_to_jsonl(articles, output_path, overwrite_existing):
    """
    Write article dictionaries as JSONL.

    PARAMETERS:
    - articles: List of article dictionaries
    - output_path: Path where the JSONL file should be written
    - overwrite_existing: True when existing files can be replaced

    RETURNS:
    - True when the file was written
    - False when an existing file was skipped
    """
    if output_path.exists() and not overwrite_existing:
        print(f"[WARNING] Output already exists, skipping: {output_path}")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output_file:
        for article in articles:
            json_text = json.dumps(article, ensure_ascii=False)
            output_file.write(json_text + "\n")

    return True


def index_one_source(
    source,
    overwrite_existing,
    max_age_days,
    output_dir,
    timestamp_text,
    indexed_at,
):
    """
    Parse and save RSS links for one source.

    PARAMETERS:
    - source: Source dictionary from collector.feeds.sources
    - overwrite_existing: True when existing files can be replaced
    - max_age_days: Maximum article age allowed
    - output_dir: Base output folder
    - timestamp_text: Timestamp text used in output filenames
    - indexed_at: ISO timestamp stored in each article

    RETURNS:
    - A result dictionary used by the main summary
    """
    source_name = source["name"]
    output_path = get_source_output_path(source_name, timestamp_text, output_dir)

    try:
        parsed_result = parse_feed(source, max_age_days, indexed_at)
        articles = parsed_result["articles"]

        if len(articles) == 0:
            return {
                "source": source_name,
                "status": "NO_ARTICLES",
                "article_count": 0,
                "output_path": str(output_path),
                "skipped_stale": parsed_result["skipped_stale"],
                "error": None,
            }

        did_write = write_articles_to_jsonl(
            articles,
            output_path,
            overwrite_existing,
        )

        if did_write:
            status = "SAVED"
        else:
            status = "SKIPPED"

        return {
            "source": source_name,
            "status": status,
            "article_count": len(articles),
            "output_path": str(output_path),
            "skipped_stale": parsed_result["skipped_stale"],
            "error": None,
        }

    except Exception as error:
        return {
            "source": source_name,
            "status": "ERROR",
            "article_count": 0,
            "output_path": str(output_path),
            "skipped_stale": 0,
            "error": str(error),
        }


def print_source_result(position, total_sources, result):
    """
    Print the result for one completed source.

    PARAMETERS:
    - position: Completion number
    - total_sources: Total selected sources
    - result: Result dictionary from index_one_source

    RETURNS:
    - None
    """
    source_name = result["source"]
    status = result["status"]

    if status == "SAVED":
        print(
            f"[{position}/{total_sources}] SAVED {source_name}: "
            f"{result['article_count']} articles -> {result['output_path']}"
        )
        return

    if status == "SKIPPED":
        print(
            f"[{position}/{total_sources}] SKIPPED {source_name}: "
            f"output already exists -> {result['output_path']}"
        )
        return

    if status == "NO_ARTICLES":
        print(f"[{position}/{total_sources}] NO_ARTICLES {source_name}: no fresh articles found")
        return

    if status == "ERROR":
        print(f"[{position}/{total_sources}] ERROR {source_name}: {result['error']}")
        return

    print(f"[{position}/{total_sources}] {status} {source_name}")


def run_indexing(
    selected_sources,
    overwrite_existing=False,
    workers=DEFAULT_WORKERS,
    max_age_days=DEFAULT_MAX_AGE_DAYS,
    output_dir=OUTPUT_DIR,
    timestamp_text=None,
    indexed_at=None,
):
    """
    Index all selected RSS sources.

    PARAMETERS:
    - selected_sources: List of source dictionaries
    - overwrite_existing: True when existing files can be replaced
    - workers: Number of worker threads; 1 means sequential mode
    - max_age_days: Maximum article age allowed
    - output_dir: Base output folder
    - timestamp_text: Optional fixed filename timestamp for tests
    - indexed_at: Optional fixed article timestamp for tests

    RETURNS:
    - A list of result dictionaries
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")

    run_started_at = datetime.now(timezone.utc)

    if timestamp_text is None:
        timestamp_text = run_started_at.strftime("%Y%m%d_%H%M%S")

    if indexed_at is None:
        indexed_at = run_started_at.isoformat()

    total_sources = len(selected_sources)
    results = []

    print("[INFO] Collector step: index RSS links")
    if overwrite_existing:
        print("[INFO] overwrite existing files: yes")
    else:
        print("[INFO] overwrite existing files: no")
    print(f"[INFO] Sources selected: {total_sources}")
    print(f"[INFO] Workers: {workers}")
    print(f"[INFO] Max article age: {max_age_days} days")

    if workers == 1:
        for position, source in enumerate(selected_sources, start=1):
            print(f"[{position}/{total_sources}] Starting source: {source['name']}")
            result = index_one_source(
                source,
                overwrite_existing,
                max_age_days,
                output_dir,
                timestamp_text,
                indexed_at,
            )
            print_source_result(position, total_sources, result)
            results.append(result)

        return results

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_source = {}

        for source in selected_sources:
            future = executor.submit(
                index_one_source,
                source,
                overwrite_existing,
                max_age_days,
                output_dir,
                timestamp_text,
                indexed_at,
            )
            future_to_source[future] = source

        completed_count = 0

        for future in as_completed(future_to_source):
            completed_count = completed_count + 1
            source = future_to_source[future]

            try:
                result = future.result()
            except Exception as error:
                result = {
                    "source": source["name"],
                    "status": "ERROR",
                    "article_count": 0,
                    "output_path": None,
                    "skipped_stale": 0,
                    "error": str(error),
                }

            print_source_result(completed_count, total_sources, result)
            results.append(result)

    return results


def print_indexing_summary(results):
    """
    Print the final indexing summary.

    PARAMETERS:
    - results: List of result dictionaries from run_indexing

    RETURNS:
    - None
    """
    saved_sources = 0
    skipped_sources = 0
    error_sources = 0
    total_articles = 0

    for result in results:
        status = result["status"]

        if status == "SAVED":
            saved_sources = saved_sources + 1

        if status == "SKIPPED" or status == "NO_ARTICLES":
            skipped_sources = skipped_sources + 1

        if status == "ERROR":
            error_sources = error_sources + 1

        total_articles = total_articles + result.get("article_count", 0)

    print("[INFO] Indexing summary")
    print(f"    total sources selected: {len(results)}")
    print(f"    saved sources: {saved_sources}")
    print(f"    skipped sources: {skipped_sources}")
    print(f"    error sources: {error_sources}")
    print(f"    total articles indexed: {total_articles}")


def index_links(
    selected_sources,
    overwrite_existing=False,
    workers=DEFAULT_WORKERS,
    max_age_days=DEFAULT_MAX_AGE_DAYS,
):
    """
    Public entry point used by collector/cli.py.

    PARAMETERS:
    - selected_sources: List of source dictionaries from sources.py
    - overwrite_existing: True when existing files can be replaced
    - workers: Number of worker threads; 1 means sequential mode
    - max_age_days: Maximum article age allowed

    RETURNS:
    - 0 when at least one source did not error
    - 1 when every selected source errored
    """
    results = run_indexing(
        selected_sources,
        overwrite_existing=overwrite_existing,
        workers=workers,
        max_age_days=max_age_days,
    )
    print_indexing_summary(results)

    non_error_sources = 0

    for result in results:
        if result["status"] != "ERROR":
            non_error_sources = non_error_sources + 1

    if len(results) == 0:
        return 1

    if non_error_sources == 0:
        return 1

    return 0
