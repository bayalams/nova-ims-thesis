"""
Raw article fetching.

This file reads indexed RSS links from:
    shared_data/corpus/news/raw/links/

Then it fetches raw article pages through ScrapingBee and saves them into:
    shared_data/corpus/news/raw/articles/

The code is intentionally explicit for junior developers:
- simple functions
- visible progress logging
- basic try/except
- optional ThreadPoolExecutor for faster independent article requests
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import datetime
from datetime import timezone
from pathlib import Path
import hashlib
import json
import os

import requests


LINKS_DIR = Path("shared_data/corpus/news/raw/links")
ARTICLES_DIR = Path("shared_data/corpus/news/raw/articles")
SCRAPINGBEE_URL = "https://app.scrapingbee.com/api/v1"
DEFAULT_ARTICLE_WORKERS = 8


def create_article_id(link):
    """
    Create a stable article ID from the article link.

    PARAMETERS:
    - link: The article URL

    RETURNS:
    - A 64-character SHA-256 hash string
    """
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def get_article_output_path(article_id, articles_dir=ARTICLES_DIR):
    """
    Build the raw article JSON path for one article ID.

    PARAMETERS:
    - article_id: The SHA-256 article ID
    - articles_dir: Base raw article folder

    RETURNS:
    - Path to the raw article JSON file
    """
    return articles_dir / f"{article_id}.json"


def get_tag_texts(article):
    """
    Convert RSS tag metadata into simple text labels.

    PARAMETERS:
    - article: RSS article dictionary

    RETURNS:
    - A list of tag strings
    """
    tag_values = article.get("tags", [])
    tag_texts = []

    if tag_values is None:
        return tag_texts

    for tag in tag_values:
        if isinstance(tag, dict):
            tag_text = tag.get("term", "")
        else:
            tag_text = str(tag)

        tag_text = tag_text.strip()

        if tag_text != "":
            tag_texts.append(tag_text)

    return tag_texts


def load_articles_from_jsonl(jsonl_path):
    """
    Load article link dictionaries from one JSONL file.

    PARAMETERS:
    - jsonl_path: Path to a JSONL link snapshot

    RETURNS:
    - A list of article dictionaries
    """
    print(f"[INFO] Loading links from: {jsonl_path}")
    articles = []

    try:
        with jsonl_path.open("r", encoding="utf-8") as input_file:
            for line in input_file:
                line = line.strip()

                if line == "":
                    continue

                article = json.loads(line)
                articles.append(article)

    except Exception as error:
        print(f"[WARNING] Could not load JSONL file: {jsonl_path}")
        print(f"[WARNING] Error: {error}")

    print(f"[INFO]   Loaded {len(articles)} link records")
    return articles


def find_link_files(selected_sources, links_dir=LINKS_DIR):
    """
    Find JSONL link snapshots for selected RSS sources.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries
    - links_dir: Base raw links folder

    RETURNS:
    - A sorted list of JSONL paths
    """
    link_files = []

    if not links_dir.exists():
        print(f"[WARNING] Links directory does not exist: {links_dir}")
        return link_files

    for source in selected_sources:
        source_name = source["name"]
        source_dir = links_dir / source_name

        if not source_dir.exists():
            print(f"[WARNING] No link folder found for source: {source_name}")
            continue

        for jsonl_path in sorted(source_dir.glob("*.jsonl")):
            if jsonl_path.name.startswith("._"):
                continue

            link_files.append(jsonl_path)

    return link_files


def should_scrape(article):
    """
    Decide whether one article should be fetched before spending an API call.

    PARAMETERS:
    - article: RSS article dictionary

    RETURNS:
    - True when the article should be fetched
    - False when the article should be skipped
    """
    source = article.get("source", "").upper()
    link = article.get("link", "")
    tags = get_tag_texts(article)

    # Step 1: globally skip videos, podcasts, multimedia, and galleries.
    skipped_tag_words = ["vídeo", "videos", "podcast", "multimédia", "galeria"]
    for tag in tags:
        tag_lower = tag.lower()

        for skipped_word in skipped_tag_words:
            if skipped_word in tag_lower:
                return False

    video_patterns = [
        "/video/",
        "/videos/",
        "/cmtv/",
        "www.nytimes.com/video",
        "/podcasts/",
        "multimedia",
    ]
    for pattern in video_patterns:
        if pattern in link:
            return False

    # Step 2: keep only relevant Expresso tags and old mapped tags.
    if "EXPRESSO" in source:
        target_categories = ["Política", "Sociedade", "Internacional", "Boa Cama Boa Mesa"]
        tag_map = {
            "Presidenciais 2026": "Política",
            "Governo": "Política",
            "Parlamento": "Política",
            "Partidos": "Política",
            "Justiça": "Política",
            "Venezuela": "Internacional",
            "Guerra na Ucrânia": "Internacional",
            "Médio Oriente": "Internacional",
            "América Latina": "Internacional",
            "União Europeia": "Internacional",
            "EUA": "Internacional",
            "Brasil": "Internacional",
            "Espanha": "Internacional",
            "França": "Internacional",
            "Reino Unido": "Internacional",
            "Mundo": "Internacional",
            "Europa": "Internacional",
            "Guerra Fria": "Internacional",
            "Saúde": "Sociedade",
            "Transportes": "Sociedade",
            "Meteorologia": "Sociedade",
            "Segurança": "Sociedade",
            "Imobiliário": "Sociedade",
            "Habitação": "Sociedade",
            "Lisboa": "Sociedade",
        }
        effective_tags = []

        for tag in tags:
            clean_tag = tag.strip()
            effective_tags.append(clean_tag)

            if clean_tag in tag_map:
                effective_tags.append(tag_map[clean_tag])

        is_allowed = False

        for effective_tag in effective_tags:
            for target_category in target_categories:
                if effective_tag.lower() == target_category.lower():
                    is_allowed = True

        if not is_allowed:
            return False

    # Step 3: skip Observador formats that are not normal articles.
    if "OBSERVADOR" in source:
        exclude_tags = ["Rádio Observador", "Observador Lab", "Newsletter"]

        for tag in tags:
            for exclude_tag in exclude_tags:
                if exclude_tag in tag:
                    return False

    # Step 4: keep only Sapo travel URLs.
    if source == "SAPO_VIAGENS":
        if "viagens.sapo.pt" not in link and "travelmagg.sapo.pt" not in link:
            return False

    # Step 5: keep only Eco tourism, aviation, and hospitality business items.
    if source == "ECO_SAPO":
        keywords = [
            "turismo",
            "hotel",
            "aviacao",
            "aeroporto",
            "tap",
            "ryanair",
            "easyjet",
            "alojamento",
            "viajar",
            "hospedagem",
            "companhia-aerea",
            "voos",
            "greve",
            "sata",
            "ana-aeroportos",
            "nave",
        ]
        link_lower = link.lower()
        found_keyword = False

        for keyword in keywords:
            if keyword in link_lower:
                found_keyword = True

        if not found_keyword:
            for tag in tags:
                tag_lower = tag.lower()

                for keyword in keywords:
                    if keyword in tag_lower:
                        found_keyword = True

        if not found_keyword:
            return False

    # Step 6: keep the old Telegraph deprecation rule.
    if source == "TELEGRAPH":
        return False

    return True


def build_fetch_queue(
    selected_sources,
    links_dir=LINKS_DIR,
    articles_dir=ARTICLES_DIR,
    overwrite_existing=False,
    use_filters=True,
    limit=None,
    per_source=None,
):
    """
    Build the list of article fetch work from all selected link snapshots.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries
    - links_dir: Base raw links folder
    - articles_dir: Base raw articles folder
    - overwrite_existing: True when existing article JSON can be replaced
    - use_filters: True when pre-scrape filters should run
    - limit: Maximum total articles to fetch, or None
    - per_source: Maximum articles per source, or None

    RETURNS:
    - queue: List of work dictionaries
    - counts: Dictionary of skipped and selected counts
    """
    link_files = find_link_files(selected_sources, links_dir)
    queue = []
    seen_links = set()
    selected_count_by_source = {}
    counts = {
        "link_files": len(link_files),
        "loaded": 0,
        "missing_link": 0,
        "duplicates": 0,
        "skipped_existing": 0,
        "skipped_filter": 0,
        "skipped_per_source": 0,
        "selected": 0,
    }

    print(f"[INFO] Found {len(link_files)} link snapshot files")

    for jsonl_path in link_files:
        articles = load_articles_from_jsonl(jsonl_path)
        fallback_source = jsonl_path.parent.name

        for article in articles:
            counts["loaded"] = counts["loaded"] + 1
            link = article.get("link", "")

            if link == "":
                counts["missing_link"] = counts["missing_link"] + 1
                continue

            if link in seen_links:
                counts["duplicates"] = counts["duplicates"] + 1
                continue

            seen_links.add(link)

            if use_filters and not should_scrape(article):
                counts["skipped_filter"] = counts["skipped_filter"] + 1
                continue

            source_name = article.get("source", fallback_source)
            article_id = create_article_id(link)
            output_path = get_article_output_path(article_id, articles_dir)

            if output_path.exists() and not overwrite_existing:
                counts["skipped_existing"] = counts["skipped_existing"] + 1
                continue

            selected_for_source = selected_count_by_source.get(source_name, 0)

            if per_source is not None and selected_for_source >= per_source:
                counts["skipped_per_source"] = counts["skipped_per_source"] + 1
                continue

            queue.append(
                {
                    "article": article,
                    "article_id": article_id,
                    "source": source_name,
                }
            )
            selected_count_by_source[source_name] = selected_for_source + 1
            counts["selected"] = counts["selected"] + 1

            if limit is not None and counts["selected"] >= limit:
                return queue, counts

    return queue, counts


def get_api_key():
    """
    Read the ScrapingBee API key from the environment.

    PARAMETERS:
    - None

    RETURNS:
    - API key string, or None when missing
    """
    return os.environ.get("SCRAPINGBEE_API_KEY")


def scrape_article(api_key, url):
    """
    Scrape one article URL through ScrapingBee.

    PARAMETERS:
    - api_key: ScrapingBee API key
    - url: Article URL

    RETURNS:
    - A scraping result dictionary
    """
    print(f"[INFO]   Scraping URL preview: {url[:80]}")

    params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true",
        "return_page_markdown": "true",
    }

    try:
        response = requests.get(SCRAPINGBEE_URL, params=params, timeout=30)
        result = {
            "success": response.ok,
            "status_code": response.status_code,
            "content": response.text,
            "headers": dict(response.headers),
        }

        if response.ok:
            print(f"[INFO]   Success! Got {len(response.text)} characters")
        else:
            print(f"[WARNING]   Failed with status code: {response.status_code}")

        return result
    except requests.RequestException as error:
        print(f"[ERROR]   Request failed: {error}")
        return {
            "success": False,
            "error": str(error),
        }


def save_article(article_data, articles_dir=ARTICLES_DIR):
    """
    Save one raw article JSON file.

    PARAMETERS:
    - article_data: Raw article dictionary
    - articles_dir: Base raw articles folder

    RETURNS:
    - Path to the saved JSON file
    """
    article_id = article_data["id"]
    output_path = get_article_output_path(article_id, articles_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(article_data, output_file, ensure_ascii=False, indent=2)

    return output_path


def fetch_one_article(article, article_id, source, api_key, articles_dir=ARTICLES_DIR):
    """
    Fetch and save one raw article.

    PARAMETERS:
    - article: RSS article metadata dictionary
    - article_id: Stable article ID
    - source: Canonical source name
    - api_key: ScrapingBee API key
    - articles_dir: Base raw articles folder

    RETURNS:
    - A result dictionary for progress and summaries
    """
    output_path = get_article_output_path(article_id, articles_dir)

    try:
        link = article["link"]
        scrape_result = scrape_article(api_key, link)
        article_data = {
            "id": article_id,
            "link": link,
            "source": source,
            "metadata": article,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "scrapingbee": scrape_result,
        }
        save_article(article_data, articles_dir)

        if scrape_result.get("success"):
            status = "SAVED"
        else:
            status = "FAILED"

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
            "output_path": str(output_path),
            "error": str(error),
        }


def print_article_result(position, total_articles, result):
    """
    Print progress for one fetched article.

    PARAMETERS:
    - position: Completed article number
    - total_articles: Total queued articles
    - result: Result dictionary from fetch_one_article

    RETURNS:
    - None
    """
    status = result["status"]
    source = result["source"]
    article_id = result["article_id"]

    if status == "SAVED":
        print(f"[{position}/{total_articles}] SAVED {source}: {article_id}")
        return

    if status == "FAILED":
        print(f"[{position}/{total_articles}] FAILED {source}: saved failed result {article_id}")
        return

    if status == "ERROR":
        print(f"[{position}/{total_articles}] ERROR {source}: {result['error']}")
        return

    print(f"[{position}/{total_articles}] {status} {source}: {article_id}")


def run_fetching(queue, api_key, articles_dir=ARTICLES_DIR, workers=DEFAULT_ARTICLE_WORKERS):
    """
    Fetch queued articles sequentially or with worker threads.

    PARAMETERS:
    - queue: List of work dictionaries
    - api_key: ScrapingBee API key
    - articles_dir: Base raw articles folder
    - workers: Number of worker threads; 1 means sequential mode

    RETURNS:
    - A list of result dictionaries
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")

    total_articles = len(queue)
    results = []

    print(f"[INFO] Articles queued: {total_articles}")
    print(f"[INFO] Workers: {workers}")
    print("[INFO] JavaScript rendering: enabled")

    if workers == 1:
        for position, item in enumerate(queue, start=1):
            result = fetch_one_article(
                item["article"],
                item["article_id"],
                item["source"],
                api_key,
                articles_dir,
            )
            print_article_result(position, total_articles, result)
            results.append(result)

        return results

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_item = {}

        for item in queue:
            future = executor.submit(
                fetch_one_article,
                item["article"],
                item["article_id"],
                item["source"],
                api_key,
                articles_dir,
            )
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

            print_article_result(completed_count, total_articles, result)
            results.append(result)

    return results


def print_fetch_summary(results, counts):
    """
    Print the final article fetching summary.

    PARAMETERS:
    - results: Result dictionaries from run_fetching
    - counts: Queue-building counts

    RETURNS:
    - None
    """
    saved_count = 0
    failed_count = 0
    error_count = 0

    for result in results:
        status = result["status"]

        if status == "SAVED":
            saved_count = saved_count + 1

        if status == "FAILED":
            failed_count = failed_count + 1

        if status == "ERROR":
            error_count = error_count + 1

    print("[INFO] Article fetching summary")
    print(f"    link files scanned: {counts.get('link_files', 0)}")
    print(f"    link records loaded: {counts.get('loaded', 0)}")
    print(f"    selected for fetching: {counts.get('selected', 0)}")
    print(f"    duplicates skipped: {counts.get('duplicates', 0)}")
    print(f"    existing skipped: {counts.get('skipped_existing', 0)}")
    print(f"    filter skipped: {counts.get('skipped_filter', 0)}")
    print(f"    per-source skipped: {counts.get('skipped_per_source', 0)}")
    print(f"    saved successfully: {saved_count}")
    print(f"    saved failed scrapes: {failed_count}")
    print(f"    local errors: {error_count}")


def all_results_are_errors(results):
    """
    Decide whether every queued item failed before producing raw JSON.

    PARAMETERS:
    - results: Result dictionaries from run_fetching

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


def fetch_articles(
    selected_sources,
    overwrite_existing=False,
    workers=DEFAULT_ARTICLE_WORKERS,
    limit=None,
    per_source=None,
    use_filters=True,
    links_dir=LINKS_DIR,
    articles_dir=ARTICLES_DIR,
):
    """
    Public entry point used by collector/cli.py for normal article fetching.

    PARAMETERS:
    - selected_sources: List of source dictionaries from sources.py
    - overwrite_existing: True when existing article JSON can be replaced
    - workers: Number of worker threads; 1 means sequential mode
    - limit: Maximum total articles to fetch, or None
    - per_source: Maximum articles per source, or None
    - use_filters: True when pre-scrape filters should run
    - links_dir: Base raw links folder
    - articles_dir: Base raw articles folder

    RETURNS:
    - 0 when the command completes useful work or finds nothing new
    - 1 when input or setup prevents safe processing
    """
    print("[INFO] Collector step: fetch raw articles")
    print(f"[INFO] Sources selected: {len(selected_sources)}")
    print(f"[INFO] overwrite existing files: {overwrite_existing}")
    print(f"[INFO] Workers: {workers}")
    print(f"[INFO] Global limit: {limit}")
    print(f"[INFO] Per-source limit: {per_source}")
    print(f"[INFO] Pre-scrape filters enabled: {use_filters}")

    if workers < 1:
        print("[ERROR] workers must be at least 1")
        return 1

    api_key = get_api_key()

    if api_key is None or api_key == "":
        print("[ERROR] ScrapingBee API key not found.")
        print("[ERROR] Set SCRAPINGBEE_API_KEY before fetching articles.")
        return 1

    queue, counts = build_fetch_queue(
        selected_sources,
        links_dir=links_dir,
        articles_dir=articles_dir,
        overwrite_existing=overwrite_existing,
        use_filters=use_filters,
        limit=limit,
        per_source=per_source,
    )

    if counts["link_files"] == 0:
        print("[ERROR] No link files found for the selected sources.")
        return 1

    if len(queue) == 0:
        print("[INFO] No new articles to fetch.")
        print_fetch_summary([], counts)
        return 0

    results = run_fetching(
        queue,
        api_key,
        articles_dir=articles_dir,
        workers=workers,
    )
    print_fetch_summary(results, counts)

    if all_results_are_errors(results):
        return 1

    return 0


def find_failed_articles(
    selected_sources,
    articles_dir=ARTICLES_DIR,
    limit=None,
    per_source=None,
):
    """
    Find saved raw article files where ScrapingBee previously failed.

    PARAMETERS:
    - selected_sources: List of selected source dictionaries
    - articles_dir: Base raw articles folder
    - limit: Maximum total failed articles to retry, or None
    - per_source: Maximum failed articles per source, or None

    RETURNS:
    - A retry queue in the same shape used by run_fetching
    """
    failed_articles = []
    selected_source_names = set()
    selected_count_by_source = {}

    for source in selected_sources:
        selected_source_names.add(source["name"])

    if not articles_dir.exists():
        print(f"[WARNING] Raw articles directory does not exist: {articles_dir}")
        return failed_articles

    for article_path in sorted(articles_dir.glob("*.json")):
        if article_path.name.startswith("._"):
            continue

        try:
            with article_path.open("r", encoding="utf-8") as input_file:
                article_data = json.load(input_file)
        except Exception as error:
            print(f"[WARNING] Could not inspect raw article file: {article_path}")
            print(f"[WARNING] Error: {error}")
            continue

        scrapingbee_result = article_data.get("scrapingbee", {})

        if scrapingbee_result.get("success") is not False:
            continue

        metadata = article_data.get("metadata", {})

        if not isinstance(metadata, dict):
            metadata = {}

        link = article_data.get("link", metadata.get("link", ""))
        source_name = article_data.get("source", metadata.get("source", "UNKNOWN"))

        if source_name not in selected_source_names:
            continue

        selected_for_source = selected_count_by_source.get(source_name, 0)

        if per_source is not None and selected_for_source >= per_source:
            continue

        if link == "":
            continue

        metadata["link"] = link
        metadata["source"] = source_name
        article_id = article_data.get("id", create_article_id(link))

        failed_articles.append(
            {
                "article": metadata,
                "article_id": article_id,
                "source": source_name,
            }
        )
        selected_count_by_source[source_name] = selected_for_source + 1

        if limit is not None and len(failed_articles) >= limit:
            return failed_articles

    return failed_articles


def retry_failed_articles(
    selected_sources,
    workers=DEFAULT_ARTICLE_WORKERS,
    limit=None,
    per_source=None,
    articles_dir=ARTICLES_DIR,
):
    """
    Public entry point used by collector/cli.py to retry failed raw scrapes.

    PARAMETERS:
    - selected_sources: List of source dictionaries from sources.py
    - workers: Number of worker threads; 1 means sequential mode
    - limit: Maximum total failed articles to retry, or None
    - per_source: Maximum failed articles per source, or None
    - articles_dir: Base raw articles folder

    RETURNS:
    - 0 when retry completes or there is nothing to retry
    - 1 when setup prevents safe processing
    """
    print("[INFO] Collector step: retry failed raw articles")
    print(f"[INFO] Sources selected: {len(selected_sources)}")
    print(f"[INFO] Workers: {workers}")
    print(f"[INFO] Global limit: {limit}")
    print(f"[INFO] Per-source limit: {per_source}")

    if workers < 1:
        print("[ERROR] workers must be at least 1")
        return 1

    api_key = get_api_key()

    if api_key is None or api_key == "":
        print("[ERROR] ScrapingBee API key not found.")
        print("[ERROR] Set SCRAPINGBEE_API_KEY before retrying articles.")
        return 1

    queue = find_failed_articles(
        selected_sources,
        articles_dir=articles_dir,
        limit=limit,
        per_source=per_source,
    )

    if len(queue) == 0:
        print("[INFO] No failed articles found for selected sources.")
        return 0

    counts = {
        "link_files": 0,
        "loaded": len(queue),
        "selected": len(queue),
        "duplicates": 0,
        "skipped_existing": 0,
        "skipped_filter": 0,
        "skipped_per_source": 0,
    }
    results = run_fetching(
        queue,
        api_key,
        articles_dir=articles_dir,
        workers=workers,
    )
    print_fetch_summary(results, counts)

    if all_results_are_errors(results):
        return 1

    return 0
