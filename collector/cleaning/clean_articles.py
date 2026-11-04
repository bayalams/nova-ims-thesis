"""
Clean raw article JSON files into separate clean article JSON files.

Raw article files live in:
    shared_data/corpus/news/raw/articles/

Clean article files are written to:
    shared_data/corpus/news/clean/articles/

Raw files are never edited by this module. That keeps the raw scraping evidence
available for debugging and lets us re-run cleaner experiments later.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import datetime
from datetime import timezone
from pathlib import Path
import html
import json
import re

from collector.cleaning.cleaners import clean_and_enrich_text
from collector.cleaning.cleaners.utils import normalize_tags


RAW_ARTICLES_DIR = Path("shared_data/corpus/news/raw/articles")
CLEAN_ARTICLES_DIR = Path("shared_data/corpus/news/clean/articles")
DEFAULT_CLEAN_WORKERS = 8


def get_clean_output_path(article_id, clean_dir=CLEAN_ARTICLES_DIR):
    """
    Build the clean article JSON path for one article ID.

    PARAMETERS:
    - article_id: The raw article ID
    - clean_dir: Base clean articles folder

    RETURNS:
    - Path to the clean article JSON file
    """
    return clean_dir / f"{article_id}.json"


def load_json_file(file_path):
    """
    Load one JSON file.

    PARAMETERS:
    - file_path: Path to a JSON file

    RETURNS:
    - The parsed JSON dictionary

    RAISES:
    - Any JSON or file read exception
    """
    with file_path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def get_article_source(raw_article):
    """
    Read the article source from top-level data or metadata.

    PARAMETERS:
    - raw_article: Raw article dictionary

    RETURNS:
    - Source name string
    """
    metadata = raw_article.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    return raw_article.get("source", metadata.get("source", "UNKNOWN"))


def get_article_link(raw_article):
    """
    Read the article URL from top-level data or metadata.

    PARAMETERS:
    - raw_article: Raw article dictionary

    RETURNS:
    - Article URL string
    """
    metadata = raw_article.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    return raw_article.get("link", metadata.get("link", ""))


def make_clean_metadata(raw_article):
    """
    Build a metadata dictionary that cleaners can safely mutate.

    PARAMETERS:
    - raw_article: Raw article dictionary

    RETURNS:
    - Metadata dictionary with basic fallback fields
    """
    metadata = raw_article.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}
    else:
        metadata = dict(metadata)

    raw_tags = metadata.get("tags")

    if raw_tags is None:
        raw_tags = raw_article.get("tags")

    metadata["tags"] = normalize_tags(raw_tags)

    metadata["source"] = get_article_source(raw_article)
    metadata["link"] = get_article_link(raw_article)

    if "scraped_at" in raw_article:
        metadata["scraped_at"] = raw_article["scraped_at"]

    return metadata


def clean_summary_text(summary):
    """
    Convert RSS summary text into a plain text field for clean articles.

    PARAMETERS:
    - summary: Raw summary value from RSS metadata

    RETURNS:
    - Plain summary text, or an empty string
    """
    if summary is None:
        return ""

    text = html.unescape(str(summary))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text_for_cleaning(raw_article):
    """
    Choose the best available text input for the clean article.

    PARAMETERS:
    - raw_article: Raw article dictionary

    RETURNS:
    - text: Text to save or clean
    - source_kind: Where the text came from
    """
    legacy_text = raw_article.get("text", "")

    if isinstance(legacy_text, str) and legacy_text.strip() != "":
        return legacy_text, "legacy_text"

    scrapingbee = raw_article.get("scrapingbee", {})

    if not isinstance(scrapingbee, dict):
        scrapingbee = {}

    content = scrapingbee.get("content", "")

    if isinstance(content, str) and content.strip() != "":
        return content, "scrapingbee_content"

    body = scrapingbee.get("body", "")

    if isinstance(body, str) and body.strip() != "":
        return body, "scrapingbee_body"

    fallback_content = raw_article.get("content", "")

    if isinstance(fallback_content, str) and fallback_content.strip() != "":
        return fallback_content, "content"

    return "", "missing_content"


def build_clean_article(raw_article, raw_path, cleaned_text, metadata, cleaner_name, is_valid):
    """
    Build the clean article JSON shape.

    PARAMETERS:
    - raw_article: Raw article dictionary
    - raw_path: Path to the raw article file
    - cleaned_text: Cleaned article body text
    - metadata: Metadata dictionary after cleaner processing
    - cleaner_name: Name of the cleaner path used
    - is_valid: True when the cleaned text is usable

    RETURNS:
    - Clean article dictionary
    """
    article_id = raw_article.get("id", raw_path.stem)
    link = get_article_link(raw_article)
    source = get_article_source(raw_article)
    title = metadata.get("title", "")
    summary = clean_summary_text(metadata.get("summary", raw_article.get("summary", "")))

    return {
        "id": article_id,
        "link": link,
        "source": source,
        "title": title,
        "summary": summary,
        "text": cleaned_text,
        "metadata": metadata,
        "raw_article_path": str(raw_path),
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
        "cleaner": cleaner_name,
        "is_valid_article": is_valid,
    }


def save_clean_article(clean_article, clean_dir=CLEAN_ARTICLES_DIR):
    """
    Save one clean article JSON file.

    PARAMETERS:
    - clean_article: Clean article dictionary
    - clean_dir: Base clean articles folder

    RETURNS:
    - Path to the saved clean article file
    """
    output_path = get_clean_output_path(clean_article["id"], clean_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(clean_article, output_file, ensure_ascii=False, indent=2)

    return output_path


def source_is_selected(source_name, selected_source_names, include_unlisted_sources):
    """
    Decide whether a raw article belongs in this clean run.

    PARAMETERS:
    - source_name: Source name from the raw article
    - selected_source_names: Set of selected source names
    - include_unlisted_sources: True when the user selected all sources

    RETURNS:
    - True when the source should be processed
    - False otherwise
    """
    if source_name in selected_source_names:
        return True

    if include_unlisted_sources:
        return True

    return False


def build_clean_queue(
    selected_sources,
    raw_dir=RAW_ARTICLES_DIR,
    clean_dir=CLEAN_ARTICLES_DIR,
    overwrite_existing=False,
    limit=None,
    per_source=None,
    include_unlisted_sources=False,
):
    """
    Build the list of raw article files that need cleaning.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries
    - raw_dir: Base raw articles folder
    - clean_dir: Base clean articles folder
    - overwrite_existing: True when existing clean files can be replaced
    - limit: Maximum total articles to clean, or None
    - per_source: Maximum articles per source, or None
    - include_unlisted_sources: True when unknown legacy sources are allowed

    RETURNS:
    - queue: List of work dictionaries
    - counts: Dictionary of inspected, skipped, and selected counts
    """
    queue = []
    selected_source_names = set()
    selected_count_by_source = {}
    counts = {
        "raw_files": 0,
        "invalid_json": 0,
        "skipped_source": 0,
        "skipped_existing": 0,
        "skipped_per_source": 0,
        "selected": 0,
    }

    for source in selected_sources:
        selected_source_names.add(source["name"])

    if not raw_dir.exists():
        print(f"[WARNING] Raw articles directory does not exist: {raw_dir}")
        return queue, counts

    raw_files = sorted(raw_dir.glob("*.json"))
    counts["raw_files"] = len(raw_files)

    for raw_path in raw_files:
        if raw_path.name.startswith("._"):
            continue

        try:
            raw_article = load_json_file(raw_path)
        except Exception as error:
            counts["invalid_json"] = counts["invalid_json"] + 1
            print(f"[WARNING] Could not read raw article JSON: {raw_path}")
            print(f"[WARNING] Error: {error}")
            continue

        source_name = get_article_source(raw_article)

        if not source_is_selected(source_name, selected_source_names, include_unlisted_sources):
            counts["skipped_source"] = counts["skipped_source"] + 1
            continue

        article_id = raw_article.get("id", raw_path.stem)
        output_path = get_clean_output_path(article_id, clean_dir)

        if output_path.exists() and not overwrite_existing:
            counts["skipped_existing"] = counts["skipped_existing"] + 1
            continue

        selected_for_source = selected_count_by_source.get(source_name, 0)

        if per_source is not None and selected_for_source >= per_source:
            counts["skipped_per_source"] = counts["skipped_per_source"] + 1
            continue

        queue.append(
            {
                "raw_path": raw_path,
                "article_id": article_id,
                "source": source_name,
            }
        )
        selected_count_by_source[source_name] = selected_for_source + 1
        counts["selected"] = counts["selected"] + 1

        if limit is not None and counts["selected"] >= limit:
            return queue, counts

    return queue, counts


def clean_one_article(item, clean_dir=CLEAN_ARTICLES_DIR):
    """
    Clean one raw article file and save one clean article file.

    PARAMETERS:
    - item: Work dictionary from build_clean_queue
    - clean_dir: Base clean articles folder

    RETURNS:
    - A result dictionary for progress and summaries
    """
    raw_path = item["raw_path"]
    article_id = item["article_id"]
    source = item["source"]

    try:
        raw_article = load_json_file(raw_path)
        raw_text, text_source = extract_text_for_cleaning(raw_article)
        metadata = make_clean_metadata(raw_article)

        if text_source == "legacy_text":
            cleaned_text = raw_text.strip()
            cleaner_name = "legacy_text"
        elif raw_text.strip() == "":
            cleaned_text = ""
            cleaner_name = "missing_content"
        else:
            cleaned_text = clean_and_enrich_text(raw_text, metadata).strip()
            cleaner_name = "legacy_dispatcher"

        is_valid = cleaned_text.strip() != ""
        clean_article = build_clean_article(
            raw_article,
            raw_path,
            cleaned_text,
            metadata,
            cleaner_name,
            is_valid,
        )
        output_path = save_clean_article(clean_article, clean_dir)

        if is_valid:
            status = "CLEANED"
        else:
            status = "FILTERED"

        return {
            "article_id": article_id,
            "source": source,
            "status": status,
            "output_path": str(output_path),
            "error": None,
        }

    except Exception as error:
        return {
            "article_id": article_id,
            "source": source,
            "status": "ERROR",
            "output_path": None,
            "error": str(error),
        }


def print_clean_result(position, total_articles, result):
    """
    Print progress for one cleaned article.

    PARAMETERS:
    - position: Completed article number
    - total_articles: Total queued articles
    - result: Result dictionary from clean_one_article

    RETURNS:
    - None
    """
    status = result["status"]
    source = result["source"]
    article_id = result["article_id"]

    if status == "CLEANED":
        print(f"[{position}/{total_articles}] CLEANED {source}: {article_id}")
        return

    if status == "FILTERED":
        print(f"[{position}/{total_articles}] FILTERED {source}: empty clean text {article_id}")
        return

    if status == "ERROR":
        print(f"[{position}/{total_articles}] ERROR {source}: {result['error']}")
        return

    print(f"[{position}/{total_articles}] {status} {source}: {article_id}")


def run_cleaning(queue, clean_dir=CLEAN_ARTICLES_DIR, workers=DEFAULT_CLEAN_WORKERS):
    """
    Clean queued articles sequentially or with worker threads.

    PARAMETERS:
    - queue: List of work dictionaries
    - clean_dir: Base clean articles folder
    - workers: Number of worker threads; 1 means sequential mode

    RETURNS:
    - A list of result dictionaries
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")

    results = []
    total_articles = len(queue)

    print(f"[INFO] Articles queued for cleaning: {total_articles}")
    print(f"[INFO] Workers: {workers}")

    if workers == 1:
        for position, item in enumerate(queue, start=1):
            result = clean_one_article(item, clean_dir)
            print_clean_result(position, total_articles, result)
            results.append(result)

        return results

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_item = {}

        for item in queue:
            future = executor.submit(clean_one_article, item, clean_dir)
            future_to_item[future] = item

        completed_count = 0

        for future in as_completed(future_to_item):
            completed_count = completed_count + 1
            item = future_to_item[future]

            try:
                result = future.result()
            except Exception as error:
                result = {
                    "article_id": item["article_id"],
                    "source": item["source"],
                    "status": "ERROR",
                    "output_path": None,
                    "error": str(error),
                }

            print_clean_result(completed_count, total_articles, result)
            results.append(result)

    return results


def print_clean_summary(results, counts):
    """
    Print the final cleaning summary.

    PARAMETERS:
    - results: Result dictionaries from run_cleaning
    - counts: Queue-building counts

    RETURNS:
    - None
    """
    cleaned_count = 0
    filtered_count = 0
    error_count = 0

    for result in results:
        if result["status"] == "CLEANED":
            cleaned_count = cleaned_count + 1

        if result["status"] == "FILTERED":
            filtered_count = filtered_count + 1

        if result["status"] == "ERROR":
            error_count = error_count + 1

    print("[INFO] Cleaning summary")
    print(f"    raw files scanned: {counts.get('raw_files', 0)}")
    print(f"    selected for cleaning: {counts.get('selected', 0)}")
    print(f"    existing skipped: {counts.get('skipped_existing', 0)}")
    print(f"    source skipped: {counts.get('skipped_source', 0)}")
    print(f"    per-source skipped: {counts.get('skipped_per_source', 0)}")
    print(f"    invalid raw JSON files: {counts.get('invalid_json', 0)}")
    print(f"    cleaned successfully: {cleaned_count}")
    print(f"    filtered as invalid: {filtered_count}")
    print(f"    local errors: {error_count}")


def all_results_are_errors(results):
    """
    Decide whether every queued article failed before writing clean JSON.

    PARAMETERS:
    - results: Result dictionaries from run_cleaning

    RETURNS:
    - True when every result has status ERROR
    - False otherwise
    """
    if len(results) == 0:
        return False

    for result in results:
        if result["status"] != "ERROR":
            return False

    return True


def clean_articles(
    selected_sources,
    overwrite_existing=False,
    workers=DEFAULT_CLEAN_WORKERS,
    limit=None,
    per_source=None,
    include_unlisted_sources=False,
    raw_dir=RAW_ARTICLES_DIR,
    clean_dir=CLEAN_ARTICLES_DIR,
):
    """
    Public entry point used by collector/cli.py.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries from sources.py
    - overwrite_existing: True when existing clean files can be replaced
    - workers: Number of worker threads; 1 means sequential mode
    - limit: Maximum total articles to clean, or None
    - per_source: Maximum articles per source, or None
    - include_unlisted_sources: True when unknown legacy sources are allowed
    - raw_dir: Base raw articles folder
    - clean_dir: Base clean articles folder

    RETURNS:
    - 0 when cleaning completes or there is nothing new to clean
    - 1 when setup prevents safe processing
    """
    print("[INFO] Collector step: clean articles")
    print(f"[INFO] Sources selected: {len(selected_sources)}")
    print(f"[INFO] include unlisted legacy sources: {include_unlisted_sources}")
    print(f"[INFO] overwrite existing files: {overwrite_existing}")
    print(f"[INFO] Workers: {workers}")
    print(f"[INFO] Global limit: {limit}")
    print(f"[INFO] Per-source limit: {per_source}")

    if workers < 1:
        print("[ERROR] workers must be at least 1")
        return 1

    queue, counts = build_clean_queue(
        selected_sources,
        raw_dir=raw_dir,
        clean_dir=clean_dir,
        overwrite_existing=overwrite_existing,
        limit=limit,
        per_source=per_source,
        include_unlisted_sources=include_unlisted_sources,
    )

    if counts["raw_files"] == 0:
        print("[ERROR] No raw article JSON files found.")
        return 1

    if len(queue) == 0:
        print("[INFO] No new articles to clean.")
        print_clean_summary([], counts)
        return 0

    results = run_cleaning(queue, clean_dir=clean_dir, workers=workers)
    print_clean_summary(results, counts)

    if all_results_are_errors(results):
        return 1

    return 0
