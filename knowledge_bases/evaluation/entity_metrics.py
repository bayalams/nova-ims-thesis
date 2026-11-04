"""
Entity-pair preservation metrics for KB evaluation.
"""

import hashlib
import json
import re
from pathlib import Path

from knowledge_bases.evaluation.articles import find_source_text
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_CACHE_PATH
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_MENTIONS_PATH
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_SAMPLE_SIZE
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_STORE_PATH
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_WINDOW_BATCH_SIZE
from knowledge_bases.evaluation.constants import DEFAULT_THESIS_METRIC_CONFIG
from knowledge_bases.evaluation.entity_store import create_entity_store_schema
from knowledge_bases.evaluation.entity_store import get_cached_entities
from knowledge_bases.evaluation.entity_store import make_entity_cache_key as make_store_entity_cache_key
from knowledge_bases.evaluation.entity_store import open_entity_store
from knowledge_bases.evaluation.entity_store import write_entity_error
from knowledge_bases.evaluation.entity_store import write_entity_record
from knowledge_bases.evaluation.utils import normalize_text_for_comparison
from knowledge_bases.evaluation.utils import safe_rate


def make_entity_metric_config():
    """
    Return a copy of the default thesis metric configuration.
    """
    config = dict(DEFAULT_THESIS_METRIC_CONFIG)
    config["ner_labels"] = list(DEFAULT_THESIS_METRIC_CONFIG["ner_labels"])
    return config


def make_entity_metric_artifacts(
    cache_path=DEFAULT_ENTITY_CACHE_PATH,
    mentions_path=DEFAULT_ENTITY_MENTIONS_PATH,
    store_path=DEFAULT_ENTITY_STORE_PATH,
):
    """
    Return entity artifact paths as strings.
    """
    return {
        "cache_path": str(cache_path),
        "mentions_path": str(mentions_path),
        "store_path": str(store_path),
    }


def extract_entity_batches_with_gliner(texts, config, runtime):
    """
    Extract article-level entities with the shared windowed GLiNER path.
    """
    from knowledge_bases.evaluation.entity_precompute import extract_entity_batches_with_gliner as extractor

    return extractor(texts, config, runtime)


def count_entity_windows(article_records, config):
    """
    Count GLiNER windows with the shared windowing path.
    """
    from knowledge_bases.evaluation.entity_precompute import count_record_windows

    return count_record_windows(article_records, config)


def make_entity_cache_key(text, config):
    """
    Build a stable cache key from article text and NER configuration.
    """
    cache_input = {
        "text": str(text),
        "ner_backend": config["ner_backend"],
        "ner_model": config["ner_model"],
        "ner_labels": list(config["ner_labels"]),
        "ner_threshold": config["ner_threshold"],
    }
    cache_text = json.dumps(cache_input, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(cache_text.encode("utf-8")).hexdigest()


def normalize_entity_text(text):
    """
    Normalize entity text for comparison with chunk text.
    """
    return normalize_text_for_comparison(text)


def normalize_entity_mentions(raw_entities, threshold):
    """
    Normalize raw entity dictionaries returned by GLiNER or a fake extractor.
    """
    entities = []
    seen_keys = {}

    for raw_entity in raw_entities:
        text = str(raw_entity.get("text", "")).strip()
        normalized_text = normalize_entity_text(text)
        if not normalized_text:
            continue

        score = raw_entity.get("score", 1.0)
        try:
            numeric_score = float(score)
        except Exception:
            numeric_score = 0.0

        if numeric_score < threshold:
            continue

        label = str(raw_entity.get("label", "")).strip().lower()
        start = safe_integer(raw_entity.get("start"), 0)
        end = safe_integer(raw_entity.get("end"), start + len(text))
        entity_key = (normalized_text, label, start, end)
        if entity_key in seen_keys:
            continue

        seen_keys[entity_key] = True
        entities.append(
            {
                "text": text,
                "normalized_text": normalized_text,
                "label": label,
                "start": start,
                "end": end,
                "score": numeric_score,
            }
        )

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
    Return stable entity sort key.
    """
    return (safe_integer(entity.get("start"), 0), safe_integer(entity.get("end"), 0), entity.get("normalized_text", ""))


def build_entity_pairs(entities, window_characters):
    """
    Build canonical entity pairs that appear near each other.
    """
    sorted_entities = sorted(entities, key=get_entity_sort_key)
    pairs_by_key = {}

    for left_index in range(len(sorted_entities)):
        left_entity = sorted_entities[left_index]
        left_text = left_entity["normalized_text"]
        left_start = safe_integer(left_entity.get("start"), 0)
        left_end = safe_integer(left_entity.get("end"), left_start)

        for right_index in range(left_index + 1, len(sorted_entities)):
            right_entity = sorted_entities[right_index]
            right_text = right_entity["normalized_text"]
            right_start = safe_integer(right_entity.get("start"), 0)

            if right_start - left_end > window_characters:
                break

            if left_text == right_text:
                continue

            pair_values = sorted([left_text, right_text])
            pair_key = (pair_values[0], pair_values[1])
            if pair_key not in pairs_by_key:
                pairs_by_key[pair_key] = {
                    "left": pair_values[0],
                    "right": pair_values[1],
                    "window_characters": window_characters,
                }

    pairs = []
    for pair_key in sorted(pairs_by_key):
        pairs.append(pairs_by_key[pair_key])
    return pairs


def group_chunks_by_article_id(chunk_rows):
    """
    Group chunk rows by article id.
    """
    chunks_by_article_id = {}
    for chunk_row in chunk_rows:
        article_id = str(chunk_row.get("article_id", "")).strip()
        if article_id not in chunks_by_article_id:
            chunks_by_article_id[article_id] = []
        chunks_by_article_id[article_id].append(chunk_row)
    return chunks_by_article_id


def select_entity_metric_article_rows(article_rows, sample_size):
    """
    Select a stable sample of indexed articles for entity metrics.
    """
    sorted_article_rows = sorted(article_rows, key=get_article_row_sort_key)
    return sorted_article_rows[:sample_size]


def get_article_row_sort_key(article_row):
    """
    Return stable sort key for an article row.
    """
    return str(article_row.get("article_id", ""))


def pair_is_preserved_in_chunks(pair, chunk_rows):
    """
    Check whether both entity texts appear in at least one same-article chunk.
    """
    left = pair["left"]
    right = pair["right"]

    for chunk_row in chunk_rows:
        chunk_tokens = tokenize_normalized_text(chunk_row.get("chunk_text", ""))
        if contains_token_sequence(chunk_tokens, left) and contains_token_sequence(chunk_tokens, right):
            return True

    return False


def tokenize_normalized_text(text):
    """
    Normalize text and split it into word tokens.
    """
    normalized_text = normalize_entity_text(text)
    if not normalized_text:
        return []
    return re.findall(r"\w+", normalized_text)


def contains_token_sequence(text_tokens, phrase):
    """
    Check whether phrase appears as an exact contiguous token sequence.
    """
    phrase_tokens = tokenize_normalized_text(phrase)
    if not phrase_tokens:
        return False

    if len(phrase_tokens) > len(text_tokens):
        return False

    last_start = len(text_tokens) - len(phrase_tokens)
    for start_index in range(last_start + 1):
        matches = True
        for phrase_index in range(len(phrase_tokens)):
            if text_tokens[start_index + phrase_index] != phrase_tokens[phrase_index]:
                matches = False
                break

        if matches:
            return True

    return False


def reset_entity_mentions_file(mentions_path):
    """
    Clear the latest-run entity mentions artifact.
    """
    mentions_path = Path(mentions_path)
    mentions_path.parent.mkdir(parents=True, exist_ok=True)
    mentions_path.write_text("", encoding="utf-8")


def append_jsonl(path, records):
    """
    Append records to a JSONL file.
    """
    if not records:
        return

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_entity_cache(cache_path):
    """
    Load entity cache records from JSONL.
    """
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return {}

    cache = {}
    with cache_path.open("r", encoding="utf-8") as input_file:
        for line in input_file:
            try:
                record = json.loads(line)
                cache_key = record.get("cache_key")
                if cache_key:
                    cache[cache_key] = record
            except Exception:
                continue

    return cache


def append_entity_cache_record(cache_path, record):
    """
    Append one entity cache record.
    """
    append_jsonl(cache_path, [record])


def extract_entities_with_gliner(text, config, runtime):
    """
    Extract entities with the local GLiNER model.
    """
    if runtime.get("force_import_error_for_test"):
        raise ValueError("GLiNER dependency is not installed. Run: uv add gliner")

    try:
        from gliner import GLiNER
    except Exception as error:
        raise ValueError("GLiNER dependency is not installed. Run: uv add gliner") from error

    model_name = config["ner_model"]
    model_key = "gliner_model:" + model_name

    if model_key not in runtime:
        print(f"[INFO] Loading GLiNER model: {model_name}", flush=True)
        runtime[model_key] = GLiNER.from_pretrained(model_name)

    model = runtime[model_key]
    labels = list(config["ner_labels"])
    threshold = float(config["ner_threshold"])
    return model.predict_entities(str(text), labels, threshold=threshold)


def get_entities_for_article(text, article_id, content_hash, config, cache, cache_path, runtime, entity_extractor_function):
    """
    Return cached or newly extracted entities for one article.
    """
    cache_key = make_entity_cache_key(text, config)
    if cache_key in cache:
        return cache[cache_key].get("entities", [])

    if entity_extractor_function is None:
        raw_entities = extract_entities_with_gliner(text, config, runtime)
    else:
        raw_entities = entity_extractor_function(text, config, runtime)

    entities = normalize_entity_mentions(raw_entities, config["ner_threshold"])
    record = {
        "cache_key": cache_key,
        "article_id": article_id,
        "content_hash": content_hash,
        "ner_backend": config["ner_backend"],
        "ner_model": config["ner_model"],
        "ner_threshold": config["ner_threshold"],
        "ner_labels": list(config["ner_labels"]),
        "entities": entities,
    }
    append_entity_cache_record(cache_path, record)
    cache[cache_key] = record
    return entities


def calculate_entity_pair_preservation_rate(
    article_rows,
    chunk_rows,
    clean_articles,
    recipe_name,
    config,
    cache_path,
    mentions_path,
    runtime,
    entity_extractor_function=None,
    reset_mentions=True,
    entity_sample_size=DEFAULT_ENTITY_SAMPLE_SIZE,
    entity_store_path=DEFAULT_ENTITY_STORE_PATH,
    entity_device="mps",
    entity_window_batch_size=None,
):
    """
    Calculate entity-pair preservation for one recipe.
    """
    if reset_mentions:
        reset_entity_mentions_file(mentions_path)

    if entity_window_batch_size is not None:
        entity_window_batch_size = safe_integer(entity_window_batch_size, DEFAULT_ENTITY_WINDOW_BATCH_SIZE)
        if entity_window_batch_size < 1:
            raise ValueError("entity_window_batch_size must be at least 1")
        config = dict(config)
        config["ner_labels"] = list(config["ner_labels"])
        config["entity_window_batch_size"] = entity_window_batch_size

    cache = load_entity_cache(cache_path)
    entity_store_connection = None
    if entity_extractor_function is None:
        entity_store_connection = open_entity_store(entity_store_path)
        create_entity_store_schema(entity_store_connection)

    chunks_by_article_id = group_chunks_by_article_id(chunk_rows)
    sampled_article_rows = select_entity_metric_article_rows(article_rows, entity_sample_size)
    checked_article_count = 0
    article_count_with_pairs = 0
    article_count_without_pairs = 0
    source_entity_pair_count = 0
    preserved_entity_pair_count = 0
    cached_entity_count = 0
    computed_entity_count = 0
    missing_or_error_entity_count = 0
    estimated_window_count = 0

    try:
        article_contexts = []
        for position, article_row in enumerate(sampled_article_rows, start=1):
            article_id = str(article_row.get("article_id", "")).strip()
            if not article_id:
                continue

            source_text = find_source_text(article_row, clean_articles)
            if not source_text:
                continue

            content_hash = str(article_row.get("content_hash") or "").strip()
            if not content_hash:
                content_hash = make_entity_cache_key(source_text, config)

            article_contexts.append(
                {
                    "position": position,
                    "article_row": article_row,
                    "article_id": article_id,
                    "source_text": source_text,
                    "content_hash": content_hash,
                    "entities": None,
                }
            )

        checked_article_count = len(article_contexts)

        if entity_extractor_function is None:
            missing_contexts = []
            for context in article_contexts:
                store_cache_key = make_store_entity_cache_key(context["source_text"], config, entity_device)
                context["store_cache_key"] = store_cache_key
                entities = get_cached_entities(entity_store_connection, store_cache_key)
                if entities is None:
                    missing_contexts.append(context)
                else:
                    context["entities"] = entities
                    cached_entity_count = cached_entity_count + 1

            missing_batch_size = safe_integer(
                config.get("entity_window_batch_size"),
                DEFAULT_ENTITY_WINDOW_BATCH_SIZE,
            )
            if missing_batch_size < 1:
                missing_batch_size = DEFAULT_ENTITY_WINDOW_BATCH_SIZE
            extraction_config = dict(config)
            extraction_config["resolved_device"] = entity_device

            for start_index in range(0, len(missing_contexts), missing_batch_size):
                batch_contexts = missing_contexts[start_index : start_index + missing_batch_size]
                batch_texts = []
                batch_records = []
                for context in batch_contexts:
                    batch_texts.append(context["source_text"])
                    batch_records.append(
                        {
                            "article_id": context["article_id"],
                            "content_hash": context["content_hash"],
                            "text": context["source_text"],
                        }
                    )

                try:
                    estimated_window_count = estimated_window_count + count_entity_windows(batch_records, config)
                    raw_batch_entities = extract_entity_batches_with_gliner(batch_texts, extraction_config, runtime)
                    if len(raw_batch_entities) != len(batch_contexts):
                        raise ValueError("GLiNER returned a different number of result lists than input texts")

                    for context, raw_entities in zip(batch_contexts, raw_batch_entities):
                        entities = normalize_entity_mentions(raw_entities, config["ner_threshold"])
                        write_entity_record(
                            entity_store_connection,
                            context["store_cache_key"],
                            context["article_id"],
                            context["content_hash"],
                            context["source_text"],
                            config,
                            entity_device,
                            missing_batch_size,
                            entities,
                        )
                        context["entities"] = entities
                        computed_entity_count = computed_entity_count + 1
                except Exception as error:
                    print(f"[WARNING] Entity extraction batch failed: {error}", flush=True)
                    for context in batch_contexts:
                        write_entity_error(
                            entity_store_connection,
                            context["store_cache_key"],
                            context["article_id"],
                            context["content_hash"],
                            context["source_text"],
                            config,
                            entity_device,
                            missing_batch_size,
                            str(error),
                        )
                        missing_or_error_entity_count = missing_or_error_entity_count + 1

        for context in article_contexts:
            article_row = context["article_row"]
            article_id = context["article_id"]
            source_text = context["source_text"]
            content_hash = context["content_hash"]
            print(f"[{context['position']}/{len(sampled_article_rows)}] Extracting entities: {article_id}", flush=True)

            if entity_extractor_function is None:
                entities = context["entities"]
                if entities is None:
                    continue
            else:
                entities = get_entities_for_article(
                    source_text,
                    article_id,
                    content_hash,
                    config,
                    cache,
                    cache_path,
                    runtime,
                    entity_extractor_function,
                )
                computed_entity_count = computed_entity_count + 1

            pairs = build_entity_pairs(entities, config["entity_pair_window_characters"])
            article_chunks = chunks_by_article_id.get(article_id, [])

            if pairs:
                article_count_with_pairs = article_count_with_pairs + 1
            else:
                article_count_without_pairs = article_count_without_pairs + 1

            output_pairs = []
            for pair in pairs:
                preserved = pair_is_preserved_in_chunks(pair, article_chunks)
                source_entity_pair_count = source_entity_pair_count + 1
                if preserved:
                    preserved_entity_pair_count = preserved_entity_pair_count + 1

                output_pair = dict(pair)
                output_pair["preserved_in_chunk"] = preserved
                output_pairs.append(output_pair)

            mention_record = {
                "recipe_name": recipe_name,
                "article_id": article_id,
                "source": article_row.get("source"),
                "title": article_row.get("title"),
                "content_hash": content_hash,
                "ner_backend": config["ner_backend"],
                "ner_model": config["ner_model"],
                "ner_threshold": config["ner_threshold"],
                "ner_labels": list(config["ner_labels"]),
                "resolved_device": entity_device,
                "entities": entities,
                "entity_pairs": output_pairs,
            }
            append_jsonl(mentions_path, [mention_record])
    finally:
        if entity_store_connection is not None:
            entity_store_connection.close()

    return {
        "value": safe_rate(preserved_entity_pair_count, source_entity_pair_count),
        "details": {
            "sample_size": entity_sample_size,
            "sampled_article_count": len(sampled_article_rows),
            "checked_article_count": checked_article_count,
            "article_count_with_pairs": article_count_with_pairs,
            "article_count_without_pairs": article_count_without_pairs,
            "source_entity_pair_count": source_entity_pair_count,
            "preserved_entity_pair_count": preserved_entity_pair_count,
            "cached_entity_count": cached_entity_count,
            "computed_entity_count": computed_entity_count,
            "missing_or_error_entity_count": missing_or_error_entity_count,
            "estimated_window_count": estimated_window_count,
        },
        "error": None,
    }
