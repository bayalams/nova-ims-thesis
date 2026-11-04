"""
Command-line interface for the collector folder.

Users run this CLI from the repo root:

    uv run collect list-sources
    uv run collect status
    uv run collect index-rss all
    uv run collect fetch-articles publico
    uv run collect clean-articles publico --overwrite-existing
    uv run collect quality-cleaning all --sample-per-source 10
"""

from pathlib import Path
import json
import sys

from collector.articles.fetch_articles import DEFAULT_ARTICLE_WORKERS
from collector.articles.fetch_articles import fetch_articles
from collector.articles.fetch_articles import retry_failed_articles
from collector.cleaning.clean_articles import DEFAULT_CLEAN_WORKERS
from collector.cleaning.clean_articles import clean_articles
from collector.feeds.index_links import DEFAULT_MAX_AGE_DAYS
from collector.feeds.index_links import DEFAULT_WORKERS
from collector.feeds.index_links import index_links
from collector.feeds.sources import get_cli_name
from collector.feeds.sources import get_enabled_sources
from collector.feeds.sources import select_sources
from collector.quality.cleaning_quality import DEFAULT_MINIMUM_TEXT_CHARACTERS
from collector.quality.cleaning_quality import DEFAULT_RANDOM_SEED
from collector.quality.cleaning_quality import DEFAULT_SAMPLE_MODE
from collector.quality.cleaning_quality import DEFAULT_SAMPLE_PER_SOURCE
from collector.quality.cleaning_quality import VALID_SAMPLE_MODES
from collector.quality.cleaning_quality import quality_cleaning


STATUS_LINKS_DIR = Path("shared_data/corpus/news/raw/links")
STATUS_RAW_ARTICLES_DIR = Path("shared_data/corpus/news/raw/articles")
STATUS_CLEAN_ARTICLES_DIR = Path("shared_data/corpus/news/clean/articles")


def print_help():
    """
    Print the available collector commands.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    print("Collector commands:")
    print("  uv run collect list-sources")
    print("  uv run collect status")
    print("  uv run collect index-rss all")
    print("  uv run collect index-rss publico bbc")
    print("  uv run collect index-rss all --workers 8")
    print("  uv run collect index-rss all --max-age-days 90")
    print("  uv run collect fetch-articles all")
    print("  uv run collect fetch-articles publico --limit 10 --workers 8")
    print("  uv run collect retry-failed-articles all")
    print("  uv run collect clean-articles all")
    print("  uv run collect clean-articles all --workers 8 --limit 100")
    print("  uv run collect quality-cleaning all")
    print("  uv run collect quality-cleaning all --sample-per-source 10")
    print("  Add --overwrite-existing to reprocess existing outputs.")


def make_source_count_dictionary(sources):
    """
    Create a source count dictionary with every enabled source set to zero.

    PARAMETERS:
    - sources: Source dictionaries from sources.py

    RETURNS:
    - Dictionary mapping source names to counts
    """
    counts_by_source = {}

    for source in sources:
        counts_by_source[source["name"]] = 0

    return counts_by_source


def count_link_snapshots_by_source(sources, links_dir=STATUS_LINKS_DIR):
    """
    Count RSS link snapshot JSONL files for each source.

    PARAMETERS:
    - sources: Source dictionaries from sources.py
    - links_dir: Base raw links folder

    RETURNS:
    - Dictionary mapping source names to link snapshot counts
    """
    counts_by_source = make_source_count_dictionary(sources)
    links_dir = Path(links_dir)

    if not links_dir.exists():
        return counts_by_source

    for source in sources:
        source_name = source["name"]
        source_dir = links_dir / source_name

        if not source_dir.exists():
            continue

        for jsonl_path in source_dir.glob("*.jsonl"):
            if jsonl_path.name.startswith("._"):
                continue

            if jsonl_path.is_file():
                counts_by_source[source_name] = counts_by_source[source_name] + 1

    return counts_by_source


def read_json_dictionary(file_path):
    """
    Read one JSON file and return a dictionary when possible.

    PARAMETERS:
    - file_path: Path to a JSON file

    RETURNS:
    - Parsed dictionary, or None when the file cannot be read as a dictionary
    """
    try:
        with file_path.open("r", encoding="utf-8") as input_file:
            loaded_value = json.load(input_file)
    except Exception as error:
        print(f"[WARNING] Could not read status JSON file: {file_path}")
        print(f"[WARNING] Error: {error}")
        return None

    if not isinstance(loaded_value, dict):
        return None

    return loaded_value


def get_article_source_name(article):
    """
    Read a source name from a raw or clean article dictionary.

    PARAMETERS:
    - article: Raw or clean article dictionary

    RETURNS:
    - Source name string, or UNKNOWN
    """
    source_name = article.get("source", "")

    if isinstance(source_name, str) and source_name.strip() != "":
        return source_name.strip()

    metadata = article.get("metadata", {})
    if not isinstance(metadata, dict):
        return "UNKNOWN"

    metadata_source = metadata.get("source", "")
    if isinstance(metadata_source, str) and metadata_source.strip() != "":
        return metadata_source.strip()

    return "UNKNOWN"


def count_article_json_by_source(sources, articles_dir):
    """
    Count raw or clean article JSON files by source.

    PARAMETERS:
    - sources: Source dictionaries from sources.py
    - articles_dir: Folder containing flat article JSON files

    RETURNS:
    - Dictionary mapping source names to article counts
    """
    counts_by_source = make_source_count_dictionary(sources)
    articles_dir = Path(articles_dir)

    if not articles_dir.exists():
        return counts_by_source

    for article_path in sorted(articles_dir.glob("*.json")):
        if article_path.name.startswith("._"):
            continue

        if not article_path.is_file():
            continue

        article = read_json_dictionary(article_path)
        if article is None:
            continue

        source_name = get_article_source_name(article)

        if source_name not in counts_by_source:
            counts_by_source[source_name] = 0

        counts_by_source[source_name] = counts_by_source[source_name] + 1

    return counts_by_source


def sum_counts(counts_by_source):
    """
    Sum the integer values in a count dictionary.

    PARAMETERS:
    - counts_by_source: Dictionary of counts

    RETURNS:
    - Total count
    """
    total = 0

    for source_name in counts_by_source:
        total = total + counts_by_source[source_name]

    return total


def split_overwrite_flag(arguments):
    """
    Separate the --overwrite-existing flag from source names.

    PARAMETERS:
    - arguments: Command arguments after the action name

    RETURNS:
    - source_arguments: The source names the user selected
    - overwrite_existing: True if --overwrite-existing was present
    """
    source_arguments = []
    overwrite_existing = False

    for argument in arguments:
        if argument == "--overwrite-existing":
            overwrite_existing = True
        else:
            source_arguments.append(argument)

    return source_arguments, overwrite_existing


def parse_positive_integer(option_name, value):
    """
    Parse a positive integer command option.

    PARAMETERS:
    - option_name: The option name, such as --workers
    - value: The text value from the command line

    RETURNS:
    - The parsed positive integer

    RAISES:
    - ValueError when the value is not a number or is less than 1
    """
    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{option_name} must be a positive whole number.")

    if parsed_value < 1:
        raise ValueError(f"{option_name} must be a positive whole number.")

    return parsed_value


def parse_index_rss_arguments(arguments):
    """
    Parse options for the index-rss command.

    PARAMETERS:
    - arguments: Command arguments after index-rss

    RETURNS:
    - source_arguments: Selected source names
    - overwrite_existing: True when existing files can be replaced
    - workers: Number of worker threads
    - max_age_days: Maximum article age allowed

    RAISES:
    - ValueError when an option is invalid
    """
    source_arguments = []
    overwrite_existing = False
    workers = DEFAULT_WORKERS
    max_age_days = DEFAULT_MAX_AGE_DAYS
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--overwrite-existing":
            overwrite_existing = True
            position = position + 1
        elif argument == "--workers":
            if position + 1 >= len(arguments):
                raise ValueError("--workers needs a value.")

            workers = parse_positive_integer("--workers", arguments[position + 1])
            position = position + 2
        elif argument == "--max-age-days":
            if position + 1 >= len(arguments):
                raise ValueError("--max-age-days needs a value.")

            max_age_days = parse_positive_integer("--max-age-days", arguments[position + 1])
            position = position + 2
        elif argument.startswith("--"):
            raise ValueError(f"Unknown option for index-rss: {argument}")
        else:
            source_arguments.append(argument)
            position = position + 1

    return source_arguments, overwrite_existing, workers, max_age_days


def parse_article_arguments(arguments, allow_overwrite, allow_filters):
    """
    Parse options for article fetching commands.

    PARAMETERS:
    - arguments: Command arguments after fetch-articles or retry-failed-articles
    - allow_overwrite: True when --overwrite-existing is valid
    - allow_filters: True when --no-filters is valid

    RETURNS:
    - source_arguments: Selected source names
    - overwrite_existing: True when existing article JSON can be replaced
    - workers: Number of worker threads
    - limit: Maximum total articles to process, or None
    - per_source: Maximum articles per source, or None
    - use_filters: True when pre-scrape filters should run

    RAISES:
    - ValueError when an option is invalid
    """
    source_arguments = []
    overwrite_existing = False
    workers = DEFAULT_ARTICLE_WORKERS
    limit = None
    per_source = None
    use_filters = True
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--overwrite-existing":
            if not allow_overwrite:
                raise ValueError("--overwrite-existing is not valid for this command.")

            overwrite_existing = True
            position = position + 1
        elif argument == "--no-filters":
            if not allow_filters:
                raise ValueError("--no-filters is not valid for this command.")

            use_filters = False
            position = position + 1
        elif argument == "--workers":
            if position + 1 >= len(arguments):
                raise ValueError("--workers needs a value.")

            workers = parse_positive_integer("--workers", arguments[position + 1])
            position = position + 2
        elif argument == "--limit":
            if position + 1 >= len(arguments):
                raise ValueError("--limit needs a value.")

            limit = parse_positive_integer("--limit", arguments[position + 1])
            position = position + 2
        elif argument == "--per-source":
            if position + 1 >= len(arguments):
                raise ValueError("--per-source needs a value.")

            per_source = parse_positive_integer("--per-source", arguments[position + 1])
            position = position + 2
        elif argument.startswith("--"):
            raise ValueError(f"Unknown article option: {argument}")
        else:
            source_arguments.append(argument)
            position = position + 1

    return source_arguments, overwrite_existing, workers, limit, per_source, use_filters


def parse_clean_articles_arguments(arguments):
    """
    Parse options for the clean-articles command.

    PARAMETERS:
    - arguments: Command arguments after clean-articles

    RETURNS:
    - source_arguments: Selected source names
    - overwrite_existing: True when existing clean files can be replaced
    - workers: Number of worker threads
    - limit: Maximum total articles to clean, or None
    - per_source: Maximum articles per source, or None

    RAISES:
    - ValueError when an option is invalid
    """
    source_arguments = []
    overwrite_existing = False
    workers = DEFAULT_CLEAN_WORKERS
    limit = None
    per_source = None
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--overwrite-existing":
            overwrite_existing = True
            position = position + 1
        elif argument == "--workers":
            if position + 1 >= len(arguments):
                raise ValueError("--workers needs a value.")

            workers = parse_positive_integer("--workers", arguments[position + 1])
            position = position + 2
        elif argument == "--limit":
            if position + 1 >= len(arguments):
                raise ValueError("--limit needs a value.")

            limit = parse_positive_integer("--limit", arguments[position + 1])
            position = position + 2
        elif argument == "--per-source":
            if position + 1 >= len(arguments):
                raise ValueError("--per-source needs a value.")

            per_source = parse_positive_integer("--per-source", arguments[position + 1])
            position = position + 2
        elif argument.startswith("--"):
            raise ValueError(f"Unknown option for clean-articles: {argument}")
        else:
            source_arguments.append(argument)
            position = position + 1

    return source_arguments, overwrite_existing, workers, limit, per_source


def parse_quality_cleaning_arguments(arguments):
    """
    Parse options for the quality-cleaning command.

    PARAMETERS:
    - arguments: Command arguments after quality-cleaning

    RETURNS:
    - source_arguments: Selected source names
    - sample_per_source: Number of LLM judge samples per source
    - sample_mode: suspicious, random, newest, shortest, or longest
    - random_seed: Seed for stable random samples
    - minimum_text_characters: Minimum clean article text length
    - output_dir: Optional output folder, or None

    RAISES:
    - ValueError when an option is invalid
    """
    source_arguments = []
    sample_per_source = DEFAULT_SAMPLE_PER_SOURCE
    sample_mode = DEFAULT_SAMPLE_MODE
    random_seed = DEFAULT_RANDOM_SEED
    minimum_text_characters = DEFAULT_MINIMUM_TEXT_CHARACTERS
    output_dir = None
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--sample-per-source":
            if position + 1 >= len(arguments):
                raise ValueError("--sample-per-source needs a value.")

            sample_per_source = parse_positive_integer(
                "--sample-per-source",
                arguments[position + 1],
            )
            position = position + 2
        elif argument == "--sample-mode":
            if position + 1 >= len(arguments):
                raise ValueError("--sample-mode needs a value.")

            sample_mode = arguments[position + 1].strip().lower()

            if sample_mode not in VALID_SAMPLE_MODES:
                raise ValueError(
                    "--sample-mode must be one of: " + ", ".join(VALID_SAMPLE_MODES)
                )

            position = position + 2
        elif argument == "--seed":
            if position + 1 >= len(arguments):
                raise ValueError("--seed needs a value.")

            random_seed = parse_positive_integer("--seed", arguments[position + 1])
            position = position + 2
        elif argument == "--minimum-text-characters":
            if position + 1 >= len(arguments):
                raise ValueError("--minimum-text-characters needs a value.")

            minimum_text_characters = parse_positive_integer(
                "--minimum-text-characters",
                arguments[position + 1],
            )
            position = position + 2
        elif argument == "--output-dir":
            if position + 1 >= len(arguments):
                raise ValueError("--output-dir needs a value.")

            output_dir = arguments[position + 1]
            position = position + 2
        elif argument.startswith("--"):
            raise ValueError(f"Unknown option for quality-cleaning: {argument}")
        else:
            source_arguments.append(argument)
            position = position + 1

    return (
        source_arguments,
        sample_per_source,
        sample_mode,
        random_seed,
        minimum_text_characters,
        output_dir,
    )


def list_sources():
    """
    Print every enabled source with its RSS URL.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    print("[INFO] RSS sources")

    enabled_sources = get_enabled_sources()

    for position, source in enumerate(enabled_sources, start=1):
        cli_name = get_cli_name(source["name"])
        print(f"[{position}/{len(enabled_sources)}] {source['name']} ({cli_name})")
        print(f"    enabled: yes")
        print(f"    url: {source['url']}")


def show_status():
    """
    Print the collector status summary.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    enabled_sources = get_enabled_sources()
    link_counts = count_link_snapshots_by_source(enabled_sources, STATUS_LINKS_DIR)
    raw_article_counts = count_article_json_by_source(enabled_sources, STATUS_RAW_ARTICLES_DIR)
    clean_article_counts = count_article_json_by_source(enabled_sources, STATUS_CLEAN_ARTICLES_DIR)

    print("[INFO] Overall collector status")
    print(f"    enabled sources: {len(enabled_sources)}")
    print(f"    indexed link snapshots: {sum_counts(link_counts)}")
    print(f"    raw articles: {sum_counts(raw_article_counts)}")
    print(f"    clean articles: {sum_counts(clean_article_counts)}")
    print()
    print("[INFO] Source-by-source details")

    for position, source in enumerate(enabled_sources, start=1):
        source_name = source["name"]
        link_count = link_counts.get(source_name, 0)
        raw_article_count = raw_article_counts.get(source_name, 0)
        clean_article_count = clean_article_counts.get(source_name, 0)
        print(
            f"[{position}/{len(enabled_sources)}] {source_name}: "
            f"link_snapshots={link_count} "
            f"raw_articles={raw_article_count} "
            f"clean_articles={clean_article_count}"
        )


def run_index_rss_step(remaining_arguments):
    """
    Run the index-rss collector step.

    PARAMETERS:
    - remaining_arguments: Source names plus index-rss options

    RETURNS:
    - 0 when the command succeeds
    - 1 when the user input is invalid or every selected source fails
    """
    try:
        source_arguments, overwrite_existing, workers, max_age_days = parse_index_rss_arguments(
            remaining_arguments
        )
        selected_sources = select_sources(source_arguments)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    return index_links(
        selected_sources,
        overwrite_existing=overwrite_existing,
        workers=workers,
        max_age_days=max_age_days,
    )


def run_fetch_articles_step(remaining_arguments):
    """
    Run the fetch-articles collector step.

    PARAMETERS:
    - remaining_arguments: Source names plus fetch options

    RETURNS:
    - 0 when the command succeeds
    - 1 when the user input is invalid or fetching cannot start
    """
    try:
        source_arguments, overwrite_existing, workers, limit, per_source, use_filters = (
            parse_article_arguments(
                remaining_arguments,
                allow_overwrite=True,
                allow_filters=True,
            )
        )
        selected_sources = select_sources(source_arguments)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    return fetch_articles(
        selected_sources,
        overwrite_existing=overwrite_existing,
        workers=workers,
        limit=limit,
        per_source=per_source,
        use_filters=use_filters,
    )


def run_retry_failed_articles_step(remaining_arguments):
    """
    Run the retry-failed-articles collector step.

    PARAMETERS:
    - remaining_arguments: Source names plus retry options

    RETURNS:
    - 0 when the command succeeds
    - 1 when the user input is invalid or retry cannot start
    """
    try:
        source_arguments, overwrite_existing, workers, limit, per_source, use_filters = (
            parse_article_arguments(
                remaining_arguments,
                allow_overwrite=False,
                allow_filters=False,
            )
        )
        selected_sources = select_sources(source_arguments)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    return retry_failed_articles(
        selected_sources,
        workers=workers,
        limit=limit,
        per_source=per_source,
    )


def run_clean_articles_step(remaining_arguments):
    """
    Run the clean-articles collector step.

    PARAMETERS:
    - remaining_arguments: Source names plus clean options

    RETURNS:
    - 0 when the command succeeds
    - 1 when the user input is invalid or cleaning cannot start
    """
    try:
        source_arguments, overwrite_existing, workers, limit, per_source = (
            parse_clean_articles_arguments(remaining_arguments)
        )
        include_unlisted_sources = len(source_arguments) == 1 and source_arguments[0] == "all"
        selected_sources = select_sources(source_arguments)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    return clean_articles(
        selected_sources,
        overwrite_existing=overwrite_existing,
        workers=workers,
        limit=limit,
        per_source=per_source,
        include_unlisted_sources=include_unlisted_sources,
    )


def run_quality_cleaning_step(remaining_arguments):
    """
    Run the quality-cleaning collector step.

    PARAMETERS:
    - remaining_arguments: Source names plus quality options

    RETURNS:
    - 0 when the passive report is written
    - 1 when the user input is invalid
    """
    try:
        (
            source_arguments,
            sample_per_source,
            sample_mode,
            random_seed,
            minimum_text_characters,
            output_dir,
        ) = parse_quality_cleaning_arguments(remaining_arguments)
        include_unlisted_sources = len(source_arguments) == 1 and source_arguments[0] == "all"
        selected_sources = select_sources(source_arguments)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    return quality_cleaning(
        selected_sources,
        include_unlisted_sources=include_unlisted_sources,
        sample_per_source=sample_per_source,
        sample_mode=sample_mode,
        random_seed=random_seed,
        minimum_text_characters=minimum_text_characters,
        output_dir=output_dir,
    )


def main(arguments=None):
    """
    Run the collector command-line interface.

    PARAMETERS:
    - arguments: Optional argument list for tests. If None, use sys.argv.

    RETURNS:
    - 0 when the command succeeds
    - 1 when the command fails
    """
    if arguments is None:
        arguments = sys.argv[1:]

    if len(arguments) == 0:
        print_help()
        return 0

    command = arguments[0]
    remaining_arguments = arguments[1:]

    if command == "list-sources":
        list_sources()
        return 0

    if command == "status":
        show_status()
        return 0

    if command == "index-rss":
        return run_index_rss_step(remaining_arguments)

    if command == "fetch-articles":
        return run_fetch_articles_step(remaining_arguments)

    if command == "retry-failed-articles":
        return run_retry_failed_articles_step(remaining_arguments)

    if command == "clean-articles":
        return run_clean_articles_step(remaining_arguments)

    if command == "quality-cleaning":
        return run_quality_cleaning_step(remaining_arguments)

    print(f"[ERROR] Unknown collect command: {command}")
    print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
