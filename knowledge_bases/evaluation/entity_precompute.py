"""
Precompute GLiNER entity mentions for cleaned corpus articles.
"""

import re
import time
from pathlib import Path

from knowledge_bases.build_knowledge_base import load_recipe
from knowledge_bases.build_knowledge_base import resolve_selected_recipe_names
from knowledge_bases.evaluation.articles import get_cached_clean_articles
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_STORE_PATH
from knowledge_bases.evaluation.entity_metrics import make_entity_metric_config
from knowledge_bases.evaluation.entity_metrics import normalize_entity_mentions
from knowledge_bases.evaluation.entity_store import create_entity_store_schema
from knowledge_bases.evaluation.entity_store import get_cached_entities
from knowledge_bases.evaluation.entity_store import make_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store
from knowledge_bases.evaluation.entity_store import write_entity_error
from knowledge_bases.evaluation.entity_store import write_entity_record


DEFAULT_ENTITY_PRECOMPUTE_DEVICE = "auto"
DEFAULT_ENTITY_PRECOMPUTE_BATCH_SIZE = 8
DEFAULT_ENTITY_WINDOW_TOKENS = 350
DEFAULT_ENTITY_WINDOW_OVERLAP_TOKENS = 50
GLINER_TOKEN_PATTERN = re.compile(r"\w+(?:[-_]\w+)*|\S")


def resolve_entity_device(requested_device, mps_available=None):
    """
    Resolve auto/cpu/mps into a concrete device string.
    """
    if requested_device not in ["auto", "cpu", "mps"]:
        raise ValueError("--device must be auto, cpu, or mps")

    if mps_available is None:
        mps_available = torch_mps_is_available()

    if requested_device == "auto":
        if mps_available:
            return "mps"
        return "cpu"

    if requested_device == "mps" and not mps_available:
        raise ValueError("MPS is not available on this machine")

    return requested_device


def torch_mps_is_available():
    """
    Check whether PyTorch can use Apple MPS.
    """
    try:
        import torch

        return bool(torch.backends.mps.is_available())
    except Exception:
        return False


def move_gliner_model_to_device(model, resolved_device):
    """
    Move a GLiNER model to cpu or mps.
    """
    try:
        model.to(resolved_device)
        return model
    except Exception:
        pass

    try:
        model.model.to(resolved_device)
        return model
    except Exception as error:
        raise ValueError(f"Could not move GLiNER model to {resolved_device}: {error}") from error


def split_text_into_token_windows(text, max_tokens=DEFAULT_ENTITY_WINDOW_TOKENS, overlap_tokens=DEFAULT_ENTITY_WINDOW_OVERLAP_TOKENS):
    """
    Split article text into whitespace-token windows that GLiNER can process.
    """
    if max_tokens < 1:
        raise ValueError("entity_window_tokens must be at least 1")

    if overlap_tokens < 0:
        raise ValueError("entity_window_overlap_tokens cannot be negative")

    if overlap_tokens >= max_tokens:
        raise ValueError("entity_window_overlap_tokens must be smaller than entity_window_tokens")

    text = str(text)
    token_matches = list(GLINER_TOKEN_PATTERN.finditer(text))
    if not token_matches:
        return []

    windows = []
    step_size = max_tokens - overlap_tokens
    token_start = 0

    while token_start < len(token_matches):
        token_end = min(token_start + max_tokens, len(token_matches))
        character_start = token_matches[token_start].start()
        character_end = token_matches[token_end - 1].end()

        windows.append(
            {
                "text": text[character_start:character_end],
                "character_start": character_start,
                "character_end": character_end,
                "token_start": token_start,
                "token_end": token_end,
            }
        )

        if token_end >= len(token_matches):
            break

        token_start = token_start + step_size

    return windows


def merge_window_entities(windows, raw_window_entities, threshold):
    """
    Offset window entity spans back to article coordinates and merge duplicates.
    """
    if len(windows) != len(raw_window_entities):
        raise ValueError("Window count and GLiNER result count do not match")

    best_entities_by_key = {}

    for window, raw_entities in zip(windows, raw_window_entities):
        character_start = int(window["character_start"])
        adjusted_entities = []

        for raw_entity in raw_entities:
            adjusted_entity = dict(raw_entity)
            adjusted_entity["start"] = character_start + safe_integer(raw_entity.get("start"), 0)
            adjusted_entity["end"] = character_start + safe_integer(raw_entity.get("end"), adjusted_entity["start"])
            adjusted_entities.append(adjusted_entity)

        normalized_entities = normalize_entity_mentions(adjusted_entities, threshold)
        for entity in normalized_entities:
            entity_key = (
                entity["normalized_text"],
                entity["label"],
                int(entity["start"]),
                int(entity["end"]),
            )
            existing_entity = best_entities_by_key.get(entity_key)
            if existing_entity is None or float(entity["score"]) > float(existing_entity["score"]):
                best_entities_by_key[entity_key] = entity

    entities = []
    for entity_key in sorted(best_entities_by_key):
        entities.append(best_entities_by_key[entity_key])

    return sorted(entities, key=get_entity_sort_key)


def safe_integer(value, fallback):
    """
    Convert a value to int, or return a fallback.
    """
    try:
        return int(value)
    except Exception:
        return fallback


def get_entity_sort_key(entity):
    """
    Return a stable entity sort key.
    """
    return (
        safe_integer(entity.get("start"), 0),
        safe_integer(entity.get("end"), 0),
        entity.get("normalized_text", ""),
    )


def format_duration(seconds):
    """
    Format seconds as a short human-readable duration.
    """
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def get_entity_window_settings(config):
    """
    Read window settings from metric config.
    """
    max_tokens = int(config.get("entity_window_tokens", DEFAULT_ENTITY_WINDOW_TOKENS))
    overlap_tokens = int(config.get("entity_window_overlap_tokens", DEFAULT_ENTITY_WINDOW_OVERLAP_TOKENS))
    return max_tokens, overlap_tokens


def count_record_windows(article_records, config):
    """
    Count how many GLiNER windows will be processed for article records.
    """
    max_tokens, overlap_tokens = get_entity_window_settings(config)
    window_count = 0

    for article_record in article_records:
        windows = split_text_into_token_windows(article_record["text"], max_tokens, overlap_tokens)
        window_count = window_count + len(windows)

    return window_count


def extract_entity_batches_with_gliner(texts, config, runtime):
    """
    Extract entity mentions for a batch of texts with GLiNER.
    """
    if runtime.get("force_import_error_for_test"):
        raise ValueError("GLiNER dependency is not installed. Run: uv add gliner")

    model_name = config["ner_model"]
    resolved_device = config.get("resolved_device", "cpu")
    model_key = "gliner_model:" + model_name + ":" + resolved_device

    if model_key not in runtime:
        try:
            from gliner import GLiNER
        except Exception as error:
            raise ValueError("GLiNER dependency is not installed. Run: uv add gliner") from error

        print(f"[INFO] Loading GLiNER model: {model_name}", flush=True)
        model = GLiNER.from_pretrained(model_name)
        runtime[model_key] = move_gliner_model_to_device(model, resolved_device)

    model = runtime[model_key]
    labels = list(config["ner_labels"])
    threshold = float(config["ner_threshold"])
    max_tokens, overlap_tokens = get_entity_window_settings(config)
    window_batch_size = int(config.get("entity_window_batch_size", DEFAULT_ENTITY_PRECOMPUTE_BATCH_SIZE))

    all_windows = []
    article_window_indexes = []
    for article_index, text in enumerate(texts):
        windows = split_text_into_token_windows(text, max_tokens, overlap_tokens)
        article_indexes = []
        for window in windows:
            article_indexes.append(len(all_windows))
            all_windows.append(window)
        article_window_indexes.append(article_indexes)

    raw_window_entities = []
    for start_index in range(0, len(all_windows), window_batch_size):
        window_batch = all_windows[start_index : start_index + window_batch_size]
        window_texts = []
        for window in window_batch:
            window_texts.append(window["text"])

        raw_batch_entities = model.batch_predict_entities(window_texts, labels, threshold=threshold)
        if len(raw_batch_entities) != len(window_texts):
            raise ValueError("GLiNER returned a different number of window results than input windows")

        for raw_entities in raw_batch_entities:
            raw_window_entities.append(raw_entities)

    article_results = []
    for article_indexes in article_window_indexes:
        article_windows = []
        article_raw_entities = []
        for window_index in article_indexes:
            article_windows.append(all_windows[window_index])
            article_raw_entities.append(raw_window_entities[window_index])
        article_results.append(merge_window_entities(article_windows, article_raw_entities, threshold))

    return article_results


def precompute_entity_records(
    article_records,
    store_path,
    config,
    resolved_device,
    batch_size,
    overwrite_existing=False,
    batch_extractor_function=None,
    runtime=None,
):
    """
    Precompute entity mentions for article records.
    """
    if batch_size < 1:
        raise ValueError("--batch-size must be at least 1")

    if runtime is None:
        runtime = {}

    config = dict(config)
    config["resolved_device"] = resolved_device

    if batch_extractor_function is None:
        batch_extractor_function = extract_entity_batches_with_gliner

    connection = open_entity_store(store_path)
    create_entity_store_schema(connection)

    try:
        candidate_count = 0
        unique_records = []
        seen_cache_keys = {}

        for article_record in article_records:
            text = str(article_record.get("text", "")).strip()
            if not text:
                continue

            candidate_count = candidate_count + 1
            cache_key = make_entity_cache_key(text, config, resolved_device)
            if cache_key in seen_cache_keys:
                continue

            seen_cache_keys[cache_key] = True
            prepared_record = dict(article_record)
            prepared_record["text"] = text
            prepared_record["cache_key"] = cache_key
            unique_records.append(prepared_record)

        missing_records = []
        cached_count = 0
        for article_record in unique_records:
            cache_key = article_record["cache_key"]
            cached_entities = get_cached_entities(connection, cache_key)
            if cached_entities is not None and not overwrite_existing:
                cached_count = cached_count + 1
            else:
                missing_records.append(article_record)

        processed_count = 0
        error_count = 0
        missing_window_count = count_record_windows(missing_records, config)
        start_time = time.monotonic()

        print(f"[INFO] Entity precompute unique texts: {len(unique_records)}", flush=True)
        print(f"[INFO] Entity precompute cached texts: {cached_count}", flush=True)
        print(f"[INFO] Entity precompute missing texts: {len(missing_records)}", flush=True)
        print(f"[INFO] Entity precompute estimated GLiNER windows: {missing_window_count}", flush=True)

        for start_index in range(0, len(missing_records), batch_size):
            batch_records = missing_records[start_index : start_index + batch_size]
            batch_texts = []
            for article_record in batch_records:
                batch_texts.append(article_record["text"])

            end_position = start_index + len(batch_records)
            print(
                f"[{end_position}/{len(missing_records)}] Precomputing entity batch",
                flush=True,
            )

            try:
                raw_batch_entities = batch_extractor_function(batch_texts, config, runtime)
                if len(raw_batch_entities) != len(batch_records):
                    raise ValueError("GLiNER returned a different number of result lists than input texts")

                for article_record, raw_entities in zip(batch_records, raw_batch_entities):
                    entities = normalize_entity_mentions(raw_entities, config["ner_threshold"])
                    write_entity_record(
                        connection,
                        article_record["cache_key"],
                        str(article_record.get("article_id", "")),
                        str(article_record.get("content_hash", "")),
                        article_record["text"],
                        config,
                        resolved_device,
                        batch_size,
                        entities,
                    )
                    processed_count = processed_count + 1
            except Exception as error:
                for article_record in batch_records:
                    write_entity_error(
                        connection,
                        article_record["cache_key"],
                        str(article_record.get("article_id", "")),
                        str(article_record.get("content_hash", "")),
                        article_record["text"],
                        config,
                        resolved_device,
                        batch_size,
                        str(error),
                    )
                    error_count = error_count + 1

            finished_missing_count = processed_count + error_count
            remaining_count = len(missing_records) - finished_missing_count
            if finished_missing_count > 0:
                elapsed_seconds = time.monotonic() - start_time
                seconds_per_article = elapsed_seconds / finished_missing_count
                eta_seconds = seconds_per_article * remaining_count
                print(
                    "      elapsed: "
                    + format_duration(elapsed_seconds)
                    + " | ETA remaining: "
                    + format_duration(eta_seconds),
                    flush=True,
                )

        return {
            "candidate_count": candidate_count,
            "unique_count": len(unique_records),
            "cached_count": cached_count,
            "processed_count": processed_count,
            "error_count": error_count,
            "estimated_window_count": missing_window_count,
            "store_path": str(store_path),
            "resolved_device": resolved_device,
            "batch_size": batch_size,
        }
    finally:
        connection.close()


def collect_entity_article_records(recipe_arguments, limit=None):
    """
    Collect unique article records from selected recipe clean corpora.
    """
    recipe_names = resolve_selected_recipe_names(recipe_arguments)
    if not recipe_names:
        raise ValueError("precompute-entities needs at least one recipe name or all")

    clean_articles_cache = {}
    article_records = []
    seen_input_folders = {}
    seen_texts = {}

    for position, recipe_name in enumerate(recipe_names, start=1):
        print(f"[{position}/{len(recipe_names)}] Loading clean articles for recipe: {recipe_name}", flush=True)
        recipe = load_recipe(recipe_name)

        input_folder = Path(recipe["input_corpus"])
        input_folder_key = str(input_folder.resolve())
        if input_folder_key in seen_input_folders:
            continue
        seen_input_folders[input_folder_key] = True

        clean_articles = get_cached_clean_articles(input_folder, clean_articles_cache)
        clean_records = list(clean_articles["articles_by_id"].values())
        clean_records = sorted(clean_records, key=get_clean_article_sort_key)

        for clean_record in clean_records:
            source_text = str(clean_record.get("text", "")).strip()
            if not source_text:
                continue

            if source_text in seen_texts:
                continue
            seen_texts[source_text] = True

            article_records.append(
                {
                    "article_id": str(clean_record.get("article_id", "")),
                    "source": "",
                    "title": str(clean_record.get("title", "")),
                    "content_hash": "",
                    "text": source_text,
                }
            )

            if limit is not None and len(article_records) >= limit:
                return article_records

    return article_records


def get_clean_article_sort_key(clean_record):
    """
    Return a stable sort key for clean article records.
    """
    return str(clean_record.get("article_id", ""))


def run_precompute_entities(
    recipe_arguments,
    device=DEFAULT_ENTITY_PRECOMPUTE_DEVICE,
    batch_size=DEFAULT_ENTITY_PRECOMPUTE_BATCH_SIZE,
    limit=None,
    overwrite_existing=False,
    store_path=DEFAULT_ENTITY_STORE_PATH,
    batch_extractor_function=None,
):
    """
    Command-facing entrypoint for entity precompute.
    """
    resolved_device = resolve_entity_device(device)
    config = make_entity_metric_config()
    article_records = collect_entity_article_records(recipe_arguments, limit)

    if not article_records:
        raise ValueError("No built KB articles found for entity precompute")

    print(f"[INFO] Entity precompute articles: {len(article_records)}", flush=True)
    print(f"[INFO] Entity store: {store_path}", flush=True)
    print(f"[INFO] Device: {resolved_device}", flush=True)
    print(f"[INFO] Batch size: {batch_size}", flush=True)

    summary = precompute_entity_records(
        article_records,
        store_path,
        config,
        resolved_device,
        batch_size,
        overwrite_existing,
        batch_extractor_function,
        {},
    )

    print("[INFO] Entity precompute summary", flush=True)
    print(f"    candidates: {summary['candidate_count']}", flush=True)
    print(f"    unique texts: {summary['unique_count']}", flush=True)
    print(f"    cached: {summary['cached_count']}", flush=True)
    print(f"    processed: {summary['processed_count']}", flush=True)
    print(f"    errors: {summary['error_count']}", flush=True)
    return summary
