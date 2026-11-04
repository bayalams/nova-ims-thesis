"""
Inspect GLiNER entities and entity-pair preservation for KB articles.

Run from the repository root, for example:

uv run python explorer/scripts/inspect_ner_metric.py --recipe news_fixed_2000_overlap_3large --sample-size 3
uv run python explorer/scripts/inspect_ner_metric.py --recipe news_fixed_2000_overlap_3large --article-id ARTICLE_ID
"""

import sys
from pathlib import Path

from knowledge_bases.build_knowledge_base import load_recipe
from knowledge_bases.evaluation.articles import find_source_text
from knowledge_bases.evaluation.articles import get_cached_clean_articles
from knowledge_bases.evaluation.database import fetch_article_rows
from knowledge_bases.evaluation.database import fetch_chunk_rows
from knowledge_bases.evaluation.database import get_table_columns
from knowledge_bases.evaluation.database import get_table_names
from knowledge_bases.evaluation.entity_metrics import build_entity_pairs
from knowledge_bases.evaluation.entity_metrics import contains_token_sequence
from knowledge_bases.evaluation.entity_metrics import make_entity_metric_config
from knowledge_bases.evaluation.entity_metrics import normalize_entity_mentions
from knowledge_bases.evaluation.entity_metrics import select_entity_metric_article_rows
from knowledge_bases.evaluation.entity_metrics import tokenize_normalized_text
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_STORE_PATH
from knowledge_bases.evaluation.entity_precompute import count_record_windows
from knowledge_bases.evaluation.entity_precompute import extract_entity_batches_with_gliner
from knowledge_bases.evaluation.entity_precompute import resolve_entity_device
from knowledge_bases.evaluation.entity_store import create_entity_store_schema
from knowledge_bases.evaluation.entity_store import get_cached_entities
from knowledge_bases.evaluation.entity_store import get_document_row
from knowledge_bases.evaluation.entity_store import make_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store
from knowledge_bases.evaluation.entity_store import write_entity_error
from knowledge_bases.evaluation.entity_store import write_entity_record
from knowledge_bases.storage.sqlite_kb import open_kb_database


DEFAULT_SAMPLE_SIZE = 3
DEFAULT_MAX_ENTITIES = 60
DEFAULT_MAX_PAIRS = 60


def print_help():
    """
    Print script usage.
    """
    print("[INFO] Inspect GLiNER entity metric health")
    print("")
    print("Examples:")
    print("  uv run python explorer/scripts/inspect_ner_metric.py --recipe news_fixed_2000_overlap_3large --sample-size 5")
    print("  uv run python explorer/scripts/inspect_ner_metric.py --recipe news_fixed_2000_overlap_3large --article-id ARTICLE_ID")
    print("  uv run python explorer/scripts/inspect_ner_metric.py --recipe news_fixed_2000_overlap_3large --article-id ARTICLE_ID --compute-missing")
    print("")
    print("Options:")
    print("  --recipe NAME             Required KB recipe name")
    print("  --article-id ID           Inspect one indexed article")
    print("  --sample-size N           Inspect first N stable indexed articles, default 3")
    print("  --store-path PATH         Entity SQLite store path")
    print("  --device auto|cpu|mps     Entity cache device key, default auto")
    print("  --compute-missing         Run GLiNER for missing/error cached articles")
    print("  --max-entities N          Max entities to print per article, default 60")
    print("  --max-pairs N             Max entity pairs to print per article, default 60")


def parse_arguments(arguments):
    """
    Parse command-line options.
    """
    options = {
        "recipe_name": "",
        "article_id": "",
        "sample_size": DEFAULT_SAMPLE_SIZE,
        "store_path": DEFAULT_ENTITY_STORE_PATH,
        "device": "auto",
        "compute_missing": False,
        "max_entities": DEFAULT_MAX_ENTITIES,
        "max_pairs": DEFAULT_MAX_PAIRS,
    }

    position = 0
    while position < len(arguments):
        argument = arguments[position]

        if argument in ["--help", "-h"]:
            options["help"] = True
            position = position + 1
            continue

        if argument == "--recipe":
            options["recipe_name"] = read_option_value(arguments, position, argument)
            position = position + 2
            continue

        if argument == "--article-id":
            options["article_id"] = read_option_value(arguments, position, argument)
            position = position + 2
            continue

        if argument == "--sample-size":
            options["sample_size"] = read_positive_integer(read_option_value(arguments, position, argument), argument)
            position = position + 2
            continue

        if argument == "--store-path":
            options["store_path"] = Path(read_option_value(arguments, position, argument))
            position = position + 2
            continue

        if argument == "--device":
            options["device"] = read_option_value(arguments, position, argument)
            if options["device"] not in ["auto", "cpu", "mps"]:
                raise ValueError("--device must be auto, cpu, or mps")
            position = position + 2
            continue

        if argument == "--compute-missing":
            options["compute_missing"] = True
            position = position + 1
            continue

        if argument == "--max-entities":
            options["max_entities"] = read_positive_integer(read_option_value(arguments, position, argument), argument)
            position = position + 2
            continue

        if argument == "--max-pairs":
            options["max_pairs"] = read_positive_integer(read_option_value(arguments, position, argument), argument)
            position = position + 2
            continue

        raise ValueError("Unknown option: " + argument)

    if options.get("help"):
        return options

    if not options["recipe_name"]:
        raise ValueError("--recipe is required")

    return options


def read_option_value(arguments, position, option_name):
    """
    Read the value after an option.
    """
    if position + 1 >= len(arguments):
        raise ValueError(option_name + " needs a value")
    return arguments[position + 1]


def read_positive_integer(value, option_name):
    """
    Parse a positive integer option.
    """
    try:
        number = int(value)
    except ValueError:
        raise ValueError(option_name + " must be a number")

    if number < 1:
        raise ValueError(option_name + " must be at least 1")

    return number


def resolve_inspection_device(device, compute_missing):
    """
    Resolve the device used by entity cache keys.

    Reading an existing cache can use a literal device key. Computing missing
    entities validates that the requested runtime device is available.
    """
    if device == "auto":
        return resolve_entity_device(device)

    if device not in ["cpu", "mps"]:
        raise ValueError("--device must be auto, cpu, or mps")

    if compute_missing:
        return resolve_entity_device(device)

    return device


def build_entity_inspection_report(
    recipe,
    article_id="",
    sample_size=DEFAULT_SAMPLE_SIZE,
    store_path=DEFAULT_ENTITY_STORE_PATH,
    device="auto",
    compute_missing=False,
    batch_extractor_function=None,
):
    """
    Build a structured NER metric inspection report.
    """
    config = make_entity_metric_config()
    resolved_device = resolve_inspection_device(device, compute_missing)
    input_folder = Path(recipe["input_corpus"])
    output_folder = Path(recipe["output_folder"])
    db_path = output_folder / "kb.sqlite"

    if not db_path.exists():
        raise ValueError("KB database does not exist: " + str(db_path))

    clean_articles = get_cached_clean_articles(input_folder, {})
    connection = open_kb_database(db_path)
    store_connection = open_entity_store(store_path)
    create_entity_store_schema(store_connection)

    try:
        table_names = get_table_names(connection)
        article_columns = get_table_columns(connection, "articles")
        article_rows = fetch_article_rows(connection, table_names, article_columns)
        chunk_rows = fetch_chunk_rows(connection, table_names)
        selected_article_rows = select_article_rows_for_inspection(article_rows, article_id, sample_size)

        runtime = {}
        article_reports = []
        for article_row in selected_article_rows:
            article_reports.append(
                inspect_article_entities(
                    article_row,
                    chunk_rows,
                    clean_articles,
                    store_connection,
                    store_path,
                    config,
                    resolved_device,
                    compute_missing,
                    batch_extractor_function,
                    runtime,
                )
            )
    finally:
        connection.close()
        store_connection.close()

    return {
        "recipe_name": recipe.get("name", ""),
        "database_path": str(db_path),
        "store_path": str(store_path),
        "resolved_device": resolved_device,
        "compute_missing": compute_missing,
        "article_count": len(article_reports),
        "articles": article_reports,
    }


def select_article_rows_for_inspection(article_rows, article_id, sample_size):
    """
    Select either one requested article or a stable sample.
    """
    if article_id:
        for article_row in article_rows:
            if str(article_row.get("article_id", "")) == str(article_id):
                return [article_row]
        raise ValueError("Article id is not indexed in this KB: " + str(article_id))

    return select_entity_metric_article_rows(article_rows, sample_size)


def inspect_article_entities(
    article_row,
    chunk_rows,
    clean_articles,
    store_connection,
    store_path,
    config,
    resolved_device,
    compute_missing,
    batch_extractor_function,
    runtime,
):
    """
    Inspect cached or newly computed entities for one article.
    """
    article_id = str(article_row.get("article_id", "")).strip()
    source_text = find_source_text(article_row, clean_articles)
    article_chunks = get_article_chunks(chunk_rows, article_id)
    title = str(article_row.get("title", "") or "")
    source = str(article_row.get("source", "") or "")
    content_hash = str(article_row.get("content_hash", "") or "")

    base_report = {
        "article_id": article_id,
        "title": title,
        "source": source,
        "text_character_count": len(str(source_text or "")),
        "chunk_count": len(article_chunks),
        "estimated_window_count": 0,
        "cache_status": "missing",
        "error_text": "",
        "entity_count": 0,
        "entity_counts_by_label": {},
        "entities": [],
        "entity_pair_count": 0,
        "preserved_pair_count": 0,
        "missed_pair_count": 0,
        "pairs": [],
    }

    if not source_text:
        base_report["cache_status"] = "no_source_text"
        return base_report

    article_record = {
        "article_id": article_id,
        "content_hash": content_hash,
        "text": source_text,
    }
    base_report["estimated_window_count"] = count_record_windows([article_record], config)

    cache_key = make_entity_cache_key(source_text, config, resolved_device)
    document_row = get_document_row(store_connection, cache_key)
    entities = None

    if document_row is not None and document_row["status"] == "ready":
        entities = get_cached_entities(store_connection, cache_key)
        base_report["cache_status"] = "cached"
    elif document_row is not None and document_row["status"] == "error":
        base_report["cache_status"] = "error"
        base_report["error_text"] = str(document_row["error_text"] or "")

    if entities is None and compute_missing:
        entities = compute_and_store_entities(
            store_connection,
            store_path,
            cache_key,
            article_id,
            content_hash,
            source_text,
            config,
            resolved_device,
            batch_extractor_function,
            runtime,
        )
        base_report["cache_status"] = "computed"

    if entities is None:
        return base_report

    base_report["entity_count"] = len(entities)
    base_report["entity_counts_by_label"] = count_entities_by_label(entities)
    base_report["entities"] = make_entity_rows(entities, source_text)
    base_report["pairs"] = make_pair_rows(entities, article_chunks, config)
    base_report["entity_pair_count"] = len(base_report["pairs"])
    base_report["preserved_pair_count"] = count_preserved_pairs(base_report["pairs"])
    base_report["missed_pair_count"] = base_report["entity_pair_count"] - base_report["preserved_pair_count"]
    return base_report


def compute_and_store_entities(
    store_connection,
    store_path,
    cache_key,
    article_id,
    content_hash,
    source_text,
    config,
    resolved_device,
    batch_extractor_function,
    runtime,
):
    """
    Run GLiNER for one article, write the result, and return normalized entities.
    """
    if batch_extractor_function is None:
        batch_extractor_function = extract_entity_batches_with_gliner

    batch_size = int(config.get("entity_window_batch_size", 8))
    extraction_config = dict(config)
    extraction_config["resolved_device"] = resolved_device

    try:
        raw_batch_entities = batch_extractor_function([source_text], extraction_config, runtime)
        if len(raw_batch_entities) != 1:
            raise ValueError("GLiNER returned a different number of result lists than input texts")

        entities = normalize_entity_mentions(raw_batch_entities[0], config["ner_threshold"])
        write_entity_record(
            store_connection,
            cache_key,
            article_id,
            content_hash,
            source_text,
            config,
            resolved_device,
            batch_size,
            entities,
        )
        return entities
    except Exception as error:
        write_entity_error(
            store_connection,
            cache_key,
            article_id,
            content_hash,
            source_text,
            config,
            resolved_device,
            batch_size,
            str(error),
        )
        raise


def get_article_chunks(chunk_rows, article_id):
    """
    Return chunks for one article.
    """
    article_chunks = []
    for chunk_row in chunk_rows:
        if str(chunk_row.get("article_id", "")) == article_id:
            article_chunks.append(chunk_row)
    return article_chunks


def count_entities_by_label(entities):
    """
    Count entities by label.
    """
    counts = {}
    for entity in entities:
        label = str(entity.get("label", "")).strip() or "unknown"
        if label not in counts:
            counts[label] = 0
        counts[label] = counts[label] + 1
    return counts


def make_entity_rows(entities, source_text):
    """
    Build printable entity rows with snippets.
    """
    rows = []
    for entity in entities:
        start = safe_integer(entity.get("start"), 0)
        end = safe_integer(entity.get("end"), start)
        rows.append(
            {
                "text": entity.get("text", ""),
                "normalized_text": entity.get("normalized_text", ""),
                "label": entity.get("label", ""),
                "start": start,
                "end": end,
                "score": float(entity.get("score", 0.0)),
                "snippet": make_text_snippet(source_text, start, end),
            }
        )
    return rows


def make_pair_rows(entities, article_chunks, config):
    """
    Build pair rows with preserving chunk information.
    """
    pairs = build_entity_pairs(entities, config["entity_pair_window_characters"])
    rows = []

    for pair in pairs:
        preserving_chunks = find_preserving_chunks(pair, article_chunks)
        pair_row = dict(pair)
        pair_row["preserved_in_chunk"] = len(preserving_chunks) > 0
        pair_row["preserving_chunks"] = preserving_chunks
        rows.append(pair_row)

    return rows


def find_preserving_chunks(pair, article_chunks):
    """
    Find chunks where both entity texts appear.
    """
    preserving_chunks = []
    for chunk_row in article_chunks:
        chunk_tokens = tokenize_normalized_text(chunk_row.get("chunk_text", ""))
        left_present = contains_token_sequence(chunk_tokens, pair["left"])
        right_present = contains_token_sequence(chunk_tokens, pair["right"])

        if left_present and right_present:
            preserving_chunks.append(
                {
                    "chunk_id": chunk_row.get("chunk_id", ""),
                    "chunk_index": chunk_row.get("chunk_index"),
                    "character_start": chunk_row.get("character_start"),
                    "character_end": chunk_row.get("character_end"),
                }
            )

    return preserving_chunks


def count_preserved_pairs(pair_rows):
    """
    Count preserved pair rows.
    """
    count = 0
    for pair_row in pair_rows:
        if pair_row.get("preserved_in_chunk"):
            count = count + 1
    return count


def make_text_snippet(text, start, end, context_characters=55):
    """
    Return a short snippet around one entity span.
    """
    text = str(text)
    start = max(0, int(start))
    end = max(start, int(end))
    snippet_start = max(0, start - context_characters)
    snippet_end = min(len(text), end + context_characters)
    prefix = ""
    suffix = ""
    if snippet_start > 0:
        prefix = "..."
    if snippet_end < len(text):
        suffix = "..."
    return prefix + text[snippet_start:snippet_end].replace("\n", " ") + suffix


def safe_integer(value, fallback):
    """
    Convert value to int, or return fallback.
    """
    try:
        return int(value)
    except Exception:
        return fallback


def print_report(report, max_entities=DEFAULT_MAX_ENTITIES, max_pairs=DEFAULT_MAX_PAIRS):
    """
    Print a readable NER inspection report.
    """
    print("[INFO] NER metric inspection")
    print("[INFO] Recipe: " + str(report["recipe_name"]))
    print("[INFO] Database: " + str(report["database_path"]))
    print("[INFO] Entity store: " + str(report["store_path"]))
    print("[INFO] Device key: " + str(report["resolved_device"]))
    print("[INFO] Articles inspected: " + str(report["article_count"]))

    for article_report in report["articles"]:
        print("")
        print("[ARTICLE] " + article_report["article_id"])
        print("  title: " + article_report["title"])
        print("  source: " + article_report["source"])
        print("  text characters: " + str(article_report["text_character_count"]))
        print("  chunks: " + str(article_report["chunk_count"]))
        print("  GLiNER windows: " + str(article_report["estimated_window_count"]))
        print("  cache status: " + article_report["cache_status"])
        if article_report["error_text"]:
            print("  error: " + article_report["error_text"])

        print("  entities: " + str(article_report["entity_count"]))
        print("  entity labels: " + format_label_counts(article_report["entity_counts_by_label"]))
        print(
            "  pairs preserved: "
            + str(article_report["preserved_pair_count"])
            + "/"
            + str(article_report["entity_pair_count"])
        )

        print("  entity mentions:")
        for entity in article_report["entities"][:max_entities]:
            print(
                "    - "
                + entity["label"]
                + " | "
                + format_score(entity["score"])
                + " | "
                + str(entity["start"])
                + ":"
                + str(entity["end"])
                + " | "
                + entity["text"]
            )
            print("      " + entity["snippet"])
        if len(article_report["entities"]) > max_entities:
            print("    ... " + str(len(article_report["entities"]) - max_entities) + " more entities")

        print("  entity pairs:")
        for pair in article_report["pairs"][:max_pairs]:
            preserved = "no"
            if pair["preserved_in_chunk"]:
                preserved = "yes"
            print("    - " + pair["left"] + " <> " + pair["right"] + " | preserved: " + preserved)
            if pair["preserving_chunks"]:
                print("      chunks: " + format_preserving_chunks(pair["preserving_chunks"]))
        if len(article_report["pairs"]) > max_pairs:
            print("    ... " + str(len(article_report["pairs"]) - max_pairs) + " more pairs")


def format_label_counts(label_counts):
    """
    Format label counts in stable order.
    """
    if not label_counts:
        return "none"

    parts = []
    for label in sorted(label_counts):
        parts.append(label + "=" + str(label_counts[label]))
    return ", ".join(parts)


def format_score(score):
    """
    Format an entity score.
    """
    return f"{float(score):.3f}"


def format_preserving_chunks(chunks):
    """
    Format preserving chunk indexes.
    """
    parts = []
    for chunk in chunks:
        parts.append(str(chunk.get("chunk_index")))
    return ", ".join(parts)


def main(arguments=None):
    """
    Script entrypoint.
    """
    if arguments is None:
        arguments = sys.argv[1:]

    try:
        options = parse_arguments(arguments)
        if options.get("help"):
            print_help()
            return 0

        recipe = load_recipe(options["recipe_name"])
        report = build_entity_inspection_report(
            recipe,
            article_id=options["article_id"],
            sample_size=options["sample_size"],
            store_path=options["store_path"],
            device=options["device"],
            compute_missing=options["compute_missing"],
        )
        print_report(report, options["max_entities"], options["max_pairs"])
        return 0
    except ValueError as error:
        print("[ERROR] " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
