"""
Knowledge-base recipe loading and build orchestration.

This module is the high-level coordinator. It keeps each step visible:
load recipes, load cleaned articles, chunk text, estimate cost, call OpenAI,
write SQLite rows, and rebuild the Vec1 index.
"""

import hashlib
import json
import random
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from knowledge_bases.chunking.chunk_text import chunk_article_text
from knowledge_bases.embedding.openai_embeddings import build_embedding_client
from knowledge_bases.embedding.openai_embeddings import create_embedding_batch
from knowledge_bases.embedding.openai_embeddings import estimate_embedding_cost
from knowledge_bases.embedding.openai_embeddings import estimate_input_tokens
from knowledge_bases.embedding.openai_embeddings import get_safe_embedding_token_limit
from knowledge_bases.embedding.openai_embeddings import require_embedding_credentials
from knowledge_bases.storage.sqlite_kb import count_table_rows
from knowledge_bases.storage.sqlite_kb import create_kb_schema
from knowledge_bases.storage.sqlite_kb import create_vec1_table
from knowledge_bases.storage.sqlite_kb import delete_article_rows
from knowledge_bases.storage.sqlite_kb import find_vec1_extension
from knowledge_bases.storage.sqlite_kb import get_article_hashes
from knowledge_bases.storage.sqlite_kb import insert_article
from knowledge_bases.storage.sqlite_kb import insert_chunk
from knowledge_bases.storage.sqlite_kb import insert_embedding_batch
from knowledge_bases.storage.sqlite_kb import insert_vec1_vector
from knowledge_bases.storage.sqlite_kb import load_vec1_extension
from knowledge_bases.storage.sqlite_kb import open_kb_database
from knowledge_bases.storage.sqlite_kb import rebuild_vec1_index
from knowledge_bases.storage.sqlite_kb import set_article_status


RECIPES_FOLDER = Path("knowledge_bases/recipes")
DEFAULT_WORKERS = 2
DEFAULT_EMBEDDING_BATCH_SIZE = 50
DEFAULT_EMBEDDING_MAX_BATCH_TOKENS = 100000
DEFAULT_EMBEDDING_REQUEST_DELAY_SECONDS = 0.0
DEFAULT_EMBEDDING_MAX_RETRIES = 8
DEFAULT_EMBEDDING_MAX_BACKOFF_SECONDS = 60.0


def get_recipe_path(recipe_name):
    """
    Build the path for a recipe JSON file.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - A Path object pointing to the recipe file
    """
    return RECIPES_FOLDER / f"{recipe_name}.json"


def list_recipe_names():
    """
    List every KB recipe name.

    PARAMETERS:
    - None

    RETURNS:
    - A sorted list of recipe names without .json
    """
    recipe_names = []

    for recipe_path in RECIPES_FOLDER.glob("*.json"):
        recipe_names.append(recipe_path.stem)

    recipe_names.sort()
    return recipe_names


def load_recipe(recipe_name):
    """
    Load one KB recipe from JSON.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - A dictionary loaded from JSON

    RAISES:
    - ValueError if the recipe file does not exist
    """
    recipe_path = get_recipe_path(recipe_name)

    if not recipe_path.exists():
        raise ValueError(f"Unknown KB recipe: {recipe_name}")

    recipe_text = recipe_path.read_text(encoding="utf-8")
    recipe = json.loads(recipe_text)
    validate_recipe(recipe)
    return recipe


def validate_recipe(recipe):
    """
    Validate the keys required by the KB builder.

    PARAMETERS:
    - recipe: Recipe dictionary

    RETURNS:
    - None

    RAISES:
    - ValueError when a required key is missing
    """
    required_keys = [
        "name",
        "enabled",
        "input_corpus",
        "output_folder",
        "chunking_method",
        "chunk_size_characters",
        "chunk_overlap_characters",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "vector_backend",
        "search_distance",
    ]

    for required_key in required_keys:
        if required_key not in recipe:
            raise ValueError(f"Recipe {recipe.get('name', '<unknown>')} is missing key: {required_key}")

    if recipe["embedding_provider"] not in ["openai", "azure_openai"]:
        raise ValueError("Only openai and azure_openai embeddings are supported in Phase 1")

    if recipe["embedding_provider"] == "azure_openai":
        deployment = str(recipe.get("embedding_deployment", "")).strip()
        if not deployment:
            raise ValueError(f"Recipe {recipe.get('name', '<unknown>')} is missing key: embedding_deployment")

    if recipe["vector_backend"] != "sqlite_vec1":
        raise ValueError("Only sqlite_vec1 is supported in Phase 1")


def explain_recipe_text(recipe_name):
    """
    Create a plain-language explanation for one KB recipe.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - A multi-line string explaining the recipe
    """
    recipe = load_recipe(recipe_name)

    lines = []
    lines.append(f"Recipe: {recipe['name']}")
    lines.append(f"Enabled: {recipe['enabled']}")
    lines.append(f"Input corpus: {recipe['input_corpus']}")
    lines.append(f"Chunking method: {recipe['chunking_method']}")
    lines.append(f"Chunk size: {recipe['chunk_size_characters']} characters")
    lines.append(f"Chunk overlap: {recipe['chunk_overlap_characters']} characters")
    lines.append(f"Embedding provider: {recipe['embedding_provider']}")
    lines.append(f"Embedding model: {recipe['embedding_model']}")
    lines.append(f"Embedding dimensions: {recipe['embedding_dimensions']}")
    lines.append(f"Vector backend: {recipe['vector_backend']}")
    lines.append(f"Search distance: {recipe['search_distance']}")
    lines.append(f"Output folder: {recipe['output_folder']}")

    return "\n".join(lines)


def print_status():
    """
    Print KB status.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    recipe_names = list_recipe_names()

    print("[INFO] Knowledge-base status")
    print(f"    recipes found: {len(recipe_names)}")

    for position, recipe_name in enumerate(recipe_names, start=1):
        recipe = load_recipe(recipe_name)
        output_folder = Path(recipe["output_folder"])
        db_path = output_folder / "kb.sqlite"

        if db_path.exists():
            print(f"[{position}/{len(recipe_names)}] {recipe_name}: built at {db_path}")
        else:
            print(f"[{position}/{len(recipe_names)}] {recipe_name}: not built")


def resolve_selected_recipe_names(arguments):
    """
    Resolve command-line recipe selections.

    PARAMETERS:
    - arguments: List of recipe arguments after "run"

    RETURNS:
    - A list of recipe names
    """
    if len(arguments) == 1 and arguments[0] == "all":
        return list_recipe_names()

    return arguments


def load_clean_articles(input_folder):
    """
    Load cleaned article JSON files.

    PARAMETERS:
    - input_folder: Folder containing clean article JSON files

    RETURNS:
    - A list of article dictionaries
    """
    input_folder = Path(input_folder)
    article_paths = sorted(input_folder.glob("*.json"))
    articles = []

    print(f"[INFO] Loading cleaned articles from: {input_folder}")
    print(f"[INFO] Clean article files found: {len(article_paths)}")

    for article_path in article_paths:
        try:
            article_text = article_path.read_text(encoding="utf-8")
            article = json.loads(article_text)
            article["input_file_path"] = str(article_path)

            if not article.get("is_valid_article", True):
                continue

            if not article.get("text", "").strip():
                continue

            articles.append(article)
        except Exception as error:
            print(f"[WARNING] Could not load clean article {article_path}: {error}")

    print(f"[INFO] Valid clean articles loaded: {len(articles)}")
    return articles


def parse_timestamp_to_epoch(timestamp_text):
    """
    Parse a timestamp into seconds since 1970.

    PARAMETERS:
    - timestamp_text: Timestamp string from RSS, ISO, or collector filenames

    RETURNS:
    - Epoch seconds, or None when parsing fails
    """
    if timestamp_text is None:
        return None

    timestamp_text = str(timestamp_text).strip()

    if not timestamp_text:
        return None

    normalized_text = timestamp_text
    if normalized_text.endswith("Z"):
        normalized_text = normalized_text[:-1] + "+00:00"

    try:
        parsed_datetime = datetime.fromisoformat(normalized_text)
        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)
        return parsed_datetime.timestamp()
    except Exception:
        pass

    try:
        parsed_datetime = parsedate_to_datetime(timestamp_text)
        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)
        return parsed_datetime.timestamp()
    except Exception:
        pass

    try:
        parsed_datetime = datetime.strptime(timestamp_text, "%Y%m%d_%H%M%S")
        parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)
        return parsed_datetime.timestamp()
    except Exception:
        pass

    return None


def make_article_filter_options(sample_articles, random_seed):
    """
    Create one dictionary with article filter options.

    PARAMETERS:
    - sample_articles: Optional random sample size
    - random_seed: Optional integer seed

    RETURNS:
    - Article filter dictionary
    """
    effective_random_seed = random_seed

    if sample_articles is not None and effective_random_seed is None:
        # Use a default seed so a sampled "run all" compares recipes on the
        # same article subset.
        effective_random_seed = 42

    return {
        "sample_articles": sample_articles,
        "random_seed": effective_random_seed,
    }


def filter_articles_for_build(articles, article_filter_options):
    """
    Filter clean articles before building a KB.

    PARAMETERS:
    - articles: Loaded clean articles
    - article_filter_options: Dictionary from make_article_filter_options

    RETURNS:
    - Dictionary with filtered articles and filter counts
    """
    filtered_articles = list(articles)

    before_sample_count = len(filtered_articles)
    sample_articles = article_filter_options.get("sample_articles")
    sample_applied = False

    if sample_articles is not None and sample_articles < before_sample_count:
        random_seed = article_filter_options.get("random_seed")
        random_generator = random.Random(random_seed)
        sampled_articles = list(filtered_articles)
        random_generator.shuffle(sampled_articles)
        filtered_articles = sampled_articles[:sample_articles]
        filtered_articles.sort(key=get_article_id)
        sample_applied = True

    return {
        "articles": filtered_articles,
        "loaded_article_count": len(articles),
        "before_sample_count": before_sample_count,
        "after_filter_count": len(filtered_articles),
        "sample_applied": sample_applied,
    }


def get_article_id(article):
    """
    Get a stable article id.

    PARAMETERS:
    - article: Clean article dictionary

    RETURNS:
    - Article id string
    """
    article_id = article.get("id")

    if article_id:
        return str(article_id)

    input_file_path = article.get("input_file_path", "")
    return Path(input_file_path).stem


def make_article_hash(article):
    """
    Create a hash for article-level change detection.

    PARAMETERS:
    - article: Clean article dictionary

    RETURNS:
    - SHA256 hash string
    """
    hash_input = {
        "id": get_article_id(article),
        "source": article.get("source", ""),
        "title": article.get("title", ""),
        "link": article.get("link", ""),
        "text": article.get("text", "").strip(),
        "metadata": article.get("metadata", {}),
    }
    hash_text = json.dumps(hash_input, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(hash_text.encode("utf-8")).hexdigest()


def make_chunk_hash(recipe, article_id, chunk):
    """
    Create a hash for one chunk.

    PARAMETERS:
    - recipe: Recipe dictionary
    - article_id: Article id
    - chunk: Chunk dictionary

    RETURNS:
    - SHA256 hash string
    """
    hash_input = {
        "recipe": recipe["name"],
        "article_id": article_id,
        "chunk_index": chunk["chunk_index"],
        "chunk_text": chunk["text"],
        "embedding_model": recipe["embedding_model"],
    }
    hash_text = json.dumps(hash_input, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(hash_text.encode("utf-8")).hexdigest()


def make_article_record(article):
    """
    Create an article DB record from a cleaned article.

    PARAMETERS:
    - article: Clean article dictionary

    RETURNS:
    - Article record dictionary
    """
    metadata = article.get("metadata", {}) or {}
    indexed_at = metadata.get("indexed_at", "")
    indexed_at_epoch = parse_timestamp_to_epoch(indexed_at)

    if indexed_at_epoch is None:
        indexed_at = ""
    else:
        indexed_at = str(indexed_at).strip()

    return {
        "article_id": get_article_id(article),
        "source": article.get("source", metadata.get("source", "")),
        "title": article.get("title", metadata.get("title", "")),
        "url": article.get("link", metadata.get("link", "")),
        "published_at": metadata.get("published", metadata.get("date", "")),
        "indexed_at": indexed_at,
        "indexed_at_epoch": indexed_at_epoch,
        "cleaned_at": article.get("cleaned_at", ""),
        "input_file_path": article.get("input_file_path", ""),
        "content_hash": make_article_hash(article),
        "status": "ready",
    }


def make_pending_article_plan(recipe, article):
    """
    Build chunks and embedding jobs for one article.

    PARAMETERS:
    - recipe: Recipe dictionary
    - article: Clean article dictionary

    RETURNS:
    - A dictionary with article record and chunk records
    """
    article_id = get_article_id(article)
    chunks = chunk_article_text(
        article.get("text", ""),
        recipe["chunking_method"],
        recipe["chunk_size_characters"],
        recipe["chunk_overlap_characters"],
    )

    skip_record = find_oversized_chunk(recipe, article, chunks)
    if skip_record is not None:
        return {
            "article_record": make_article_record(article),
            "chunk_records": [],
            "skip_record": skip_record,
        }

    chunk_records = []
    for chunk in chunks:
        chunk_record = {
            "chunk_id": f"{article_id}_chunk_{chunk['chunk_index']}",
            "article_id": article_id,
            "chunk_index": chunk["chunk_index"],
            "chunk_text": chunk["text"],
            "character_start": chunk["character_start"],
            "character_end": chunk["character_end"],
            "chunk_hash": make_chunk_hash(recipe, article_id, chunk),
        }
        chunk_records.append(chunk_record)

    return {
        "article_record": make_article_record(article),
        "chunk_records": chunk_records,
        "skip_record": None,
    }


def find_oversized_chunk(recipe, article, chunks):
    """
    Check whether any chunk is too large for one OpenAI embedding input.

    PARAMETERS:
    - recipe: Recipe dictionary
    - article: Clean article dictionary
    - chunks: Chunks created from the article

    RETURNS:
    - A skip record dictionary, or None if every chunk is safe
    """
    safe_token_limit = get_safe_embedding_token_limit(recipe["embedding_model"])
    article_id = get_article_id(article)

    for chunk in chunks:
        estimated_tokens = estimate_input_tokens(chunk["text"])

        if estimated_tokens <= safe_token_limit:
            continue

        return {
            "article_id": article_id,
            "source": article.get("source", ""),
            "title": article.get("title", ""),
            "url": article.get("link", ""),
            "input_file_path": article.get("input_file_path", ""),
            "chunk_index": chunk["chunk_index"],
            "chunk_character_count": len(chunk["text"]),
            "estimated_tokens": estimated_tokens,
            "safe_token_limit": safe_token_limit,
            "embedding_model": recipe["embedding_model"],
            "chunking_method": recipe["chunking_method"],
            "reason": "estimated input tokens exceed safe OpenAI embedding limit",
        }

    return None


def build_pending_article_plans(recipe, connection, articles):
    """
    Decide which articles need work for one recipe.

    PARAMETERS:
    - recipe: Recipe dictionary
    - connection: sqlite3 connection
    - articles: Loaded clean articles

    RETURNS:
    - A dictionary with pending/skipped counts and plans
    """
    stored_hashes = get_article_hashes(connection)
    pending_plans = []
    skipped_unchanged = 0
    skipped_too_large = 0
    skipped_too_large_records = []
    changed_articles = 0
    new_articles = 0

    for article in articles:
        article_record = make_article_record(article)
        article_id = article_record["article_id"]
        existing_hash = stored_hashes.get(article_id)

        if existing_hash == article_record["content_hash"]:
            skipped_unchanged = skipped_unchanged + 1
            continue

        pending_plan = make_pending_article_plan(recipe, article)

        if pending_plan["skip_record"] is not None:
            skipped_too_large = skipped_too_large + 1
            skipped_too_large_records.append(pending_plan["skip_record"])
            continue

        if existing_hash is None:
            new_articles = new_articles + 1
        else:
            changed_articles = changed_articles + 1

        pending_plans.append(pending_plan)

    return {
        "pending_plans": pending_plans,
        "skipped_unchanged": skipped_unchanged,
        "skipped_too_large": skipped_too_large,
        "skipped_too_large_records": skipped_too_large_records,
        "new_articles": new_articles,
        "changed_articles": changed_articles,
    }


def estimate_tokens_from_texts(texts):
    """
    Estimate embedding tokens before calling OpenAI.

    PARAMETERS:
    - texts: List of strings

    RETURNS:
    - Rough token estimate
    """
    character_count = 0
    for text in texts:
        character_count = character_count + len(text)

    # Use the same rough rule of thumb as estimate_input_tokens without making
    # a large temporary string for a whole batch.
    estimated_tokens = int(character_count / 4)

    if character_count > 0 and estimated_tokens == 0:
        return 1

    return estimated_tokens


def confirm_paid_embedding_call(total_chunks, estimated_tokens, estimated_cost, yes):
    """
    Ask before making paid OpenAI embedding calls.

    PARAMETERS:
    - total_chunks: Number of chunks to embed
    - estimated_tokens: Estimated input token count
    - estimated_cost: Estimated cost in EUR
    - yes: Whether confirmation should be skipped

    RETURNS:
    - True when processing should continue
    """
    if total_chunks == 0:
        return True

    print("[INFO] Embedding work estimate")
    print(f"    chunks to embed: {total_chunks}")
    print(f"    estimated tokens: {estimated_tokens}")
    print(f"    estimated cost EUR: {estimated_cost}")

    if yes:
        print("[INFO] --yes supplied, continuing without prompt")
        return True

    answer = input("Type y to continue with paid OpenAI embedding calls [y/N]: ").strip().lower()
    return answer == "y"


def make_embedding_jobs(pending_plans):
    """
    Flatten pending article plans into embedding jobs.

    PARAMETERS:
    - pending_plans: List of article plans

    RETURNS:
    - List of embedding job dictionaries
    """
    jobs = []

    for pending_plan in pending_plans:
        for chunk_record in pending_plan["chunk_records"]:
            jobs.append(
                {
                    "article_id": chunk_record["article_id"],
                    "chunk_id": chunk_record["chunk_id"],
                    "text": chunk_record["chunk_text"],
                }
            )

    return jobs


def make_embedding_batches(jobs, batch_size, max_batch_tokens):
    """
    Split embedding jobs into safe OpenAI request batches.

    PARAMETERS:
    - jobs: Embedding job dictionaries
    - batch_size: Maximum number of chunks in one request
    - max_batch_tokens: Maximum estimated tokens in one request

    RETURNS:
    - A list of job batches
    """
    batches = []
    current_batch = []
    current_tokens = 0

    for job in jobs:
        job_tokens = estimate_input_tokens(job["text"])

        batch_is_full = len(current_batch) >= batch_size
        batch_would_exceed_tokens = current_tokens + job_tokens > max_batch_tokens

        if current_batch and (batch_is_full or batch_would_exceed_tokens):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(job)
        current_tokens = current_tokens + job_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


def error_is_rate_limit(error):
    """
    Check whether an exception looks like an OpenAI rate-limit error.

    PARAMETERS:
    - error: Exception object

    RETURNS:
    - True when this looks like a 429 rate-limit error
    """
    error_text = str(error).lower()
    error_name = error.__class__.__name__.lower()

    if "ratelimit" in error_name:
        return True

    if "rate limit" in error_text:
        return True

    if "429" in error_text:
        return True

    return False


def get_oversized_embedding_input_index(error):
    """
    Parse the input index from an OpenAI embedding input-length error.

    PARAMETERS:
    - error: Exception object

    RETURNS:
    - The integer input index, or None when the error is not this case
    """
    error_text = str(error)
    match = re.search(r"input\[(\d+)\].*maximum input length", error_text, flags=re.IGNORECASE)

    if match is None:
        return None

    return int(match.group(1))


def extract_retry_seconds(error):
    """
    Extract OpenAI's suggested retry delay from an error message.

    PARAMETERS:
    - error: Exception object

    RETURNS:
    - Seconds to wait before retrying
    """
    error_text = str(error)
    match = re.search(r"try again in ([0-9.]+)s", error_text, flags=re.IGNORECASE)

    if match:
        return float(match.group(1))

    return 5.0


def create_backoff_state():
    """
    Create shared backoff state for embedding workers.

    PARAMETERS:
    - None

    RETURNS:
    - A dictionary with a lock and the time workers may resume
    """
    return {
        "lock": threading.Lock(),
        "blocked_until": 0.0,
    }


def wait_for_backoff_window(backoff_state):
    """
    Wait if another worker recently hit a rate limit.

    PARAMETERS:
    - backoff_state: Shared backoff dictionary

    RETURNS:
    - None
    """
    with backoff_state["lock"]:
        wait_seconds = backoff_state["blocked_until"] - time.time()

    if wait_seconds > 0:
        print(f"[INFO] Embedding backoff active. Waiting {wait_seconds:.1f}s")
        time.sleep(wait_seconds)


def record_rate_limit_backoff(backoff_state, error, attempt):
    """
    Update shared backoff after an OpenAI rate limit.

    PARAMETERS:
    - backoff_state: Shared backoff dictionary
    - error: Exception from OpenAI
    - attempt: Current retry attempt number

    RETURNS:
    - Seconds selected for the backoff window
    """
    suggested_seconds = extract_retry_seconds(error)
    exponential_seconds = suggested_seconds * (2 ** (attempt - 1))
    wait_seconds = min(exponential_seconds + 1.0, DEFAULT_EMBEDDING_MAX_BACKOFF_SECONDS)
    blocked_until = time.time() + wait_seconds

    with backoff_state["lock"]:
        if blocked_until > backoff_state["blocked_until"]:
            backoff_state["blocked_until"] = blocked_until

    return wait_seconds


def embed_one_job_batch(client, recipe_or_model, batch_jobs, batch_number, max_retries, backoff_state):
    """
    Embed one batch of chunk jobs.

    PARAMETERS:
    - client: OpenAI client
    - recipe_or_model: Recipe dictionary or embedding model name
    - batch_jobs: List of embedding jobs
    - batch_number: Human-readable batch number
    - max_retries: Maximum rate-limit retries
    - backoff_state: Shared backoff dictionary

    RETURNS:
    - A dictionary with vectors and token count
    """
    active_jobs = list(batch_jobs)
    skipped_jobs = []
    attempt = 1

    while True:
        wait_for_backoff_window(backoff_state)

        texts = []
        for job in active_jobs:
            texts.append(job["text"])

        try:
            result = create_embedding_batch(client, texts, recipe_or_model)
            break
        except Exception as error:
            oversized_input_index = get_oversized_embedding_input_index(error)

            if oversized_input_index is not None:
                if oversized_input_index < 0 or oversized_input_index >= len(active_jobs):
                    raise

                skipped_job = active_jobs[oversized_input_index]
                skipped_jobs.append(
                    {
                        "job": skipped_job,
                        "batch_number": batch_number,
                        "input_index": oversized_input_index,
                        "error_text": str(error),
                    }
                )
                print(
                    f"[WARNING] Skipping oversized embedding input in batch {batch_number}: "
                    f"input[{oversized_input_index}] "
                    f"article={skipped_job['article_id']} chunk={skipped_job['chunk_id']}"
                )

                del active_jobs[oversized_input_index]

                if not active_jobs:
                    result = {
                        "vectors": [],
                        "token_count": 0,
                    }
                    break

                continue

            if not error_is_rate_limit(error):
                raise

            if attempt > max_retries:
                raise ValueError(f"Rate limit kept failing after {max_retries} retries") from error

            retry_seconds = record_rate_limit_backoff(backoff_state, error, attempt)
            print(
                f"[WARNING] Rate limit on embedding batch {batch_number}. "
                f"Backoff {retry_seconds:.1f}s before retry {attempt}/{max_retries}"
            )
            attempt = attempt + 1

    return {
        "batch_number": batch_number,
        "jobs": active_jobs,
        "vectors": result["vectors"],
        "token_count": result["token_count"],
        "skipped_jobs": skipped_jobs,
    }


def embed_and_write_jobs(
    connection,
    recipe,
    pending_plans,
    client,
    recipe_or_model,
    jobs,
    workers,
    embedding_run_id,
    batch_size=DEFAULT_EMBEDDING_BATCH_SIZE,
    max_batch_tokens=DEFAULT_EMBEDDING_MAX_BATCH_TOKENS,
    request_delay_seconds=DEFAULT_EMBEDDING_REQUEST_DELAY_SECONDS,
    max_retries=DEFAULT_EMBEDDING_MAX_RETRIES,
):
    """
    Embed chunk jobs and write each completed batch to SQLite.

    PARAMETERS:
    - connection: SQLite connection for this recipe
    - recipe: Recipe dictionary
    - pending_plans: Pending article plans
    - client: OpenAI client
    - recipe_or_model: Recipe dictionary or embedding model name
    - jobs: Embedding job dictionaries
    - workers: Worker count
    - embedding_run_id: Unique id for this embedding run
    - batch_size: Texts per OpenAI embedding request
    - max_batch_tokens: Estimated tokens per OpenAI request
    - request_delay_seconds: Delay between sequential OpenAI requests
    - max_retries: Maximum rate-limit retries

    RETURNS:
    - A dictionary with token and vector counts
    """
    job_batches = make_embedding_batches(jobs, batch_size, max_batch_tokens)
    write_state = make_streaming_write_state(pending_plans)
    total_tokens = 0
    vectors_written = 0
    skipped_too_large_records = []
    backoff_state = create_backoff_state()

    print(f"[INFO] Embedding batches queued: {len(job_batches)}")
    print(f"[INFO] Embedding workers: {workers}")
    print(f"[INFO] Embedding batch size limit: {batch_size}")
    print(f"[INFO] Embedding estimated tokens per request limit: {max_batch_tokens}")
    print(f"[INFO] Embedding delay between requests: {request_delay_seconds}s")

    if workers == 1:
        for position, job_batch in enumerate(job_batches, start=1):
            print(f"[{position}/{len(job_batches)}] Embedding batch")
            batch_result = embed_one_job_batch(client, recipe_or_model, job_batch, position, max_retries, backoff_state)
            total_tokens = total_tokens + batch_result["token_count"]
            skipped_too_large_records.extend(
                record_runtime_skipped_embedding_jobs(connection, recipe, write_state, batch_result)
            )
            batch_vectors_written = write_embedding_batch_to_database(
                connection,
                recipe,
                write_state,
                batch_result,
                embedding_run_id,
            )
            vectors_written = vectors_written + batch_vectors_written
            print(f"[{position}/{len(job_batches)}] Wrote batch {position} ({batch_vectors_written} vectors)")

            if request_delay_seconds > 0 and position < len(job_batches):
                print(f"[INFO] Waiting {request_delay_seconds}s before next embedding request")
                time.sleep(request_delay_seconds)
    else:
        next_position = 1

        with ThreadPoolExecutor(max_workers=workers) as executor:
            while next_position <= len(job_batches):
                future_records = []

                for _worker_number in range(workers):
                    if next_position > len(job_batches):
                        break

                    job_batch = job_batches[next_position - 1]
                    future = executor.submit(
                        embed_one_job_batch,
                        client,
                        recipe_or_model,
                        job_batch,
                        next_position,
                        max_retries,
                        backoff_state,
                    )
                    future_records.append({"future": future, "position": next_position})
                    next_position = next_position + 1

                for future_record in future_records:
                    position = future_record["position"]
                    batch_result = future_record["future"].result()
                    print(f"[{position}/{len(job_batches)}] Embedded batch {batch_result['batch_number']}")
                    total_tokens = total_tokens + batch_result["token_count"]
                    skipped_too_large_records.extend(
                        record_runtime_skipped_embedding_jobs(connection, recipe, write_state, batch_result)
                    )
                    batch_vectors_written = write_embedding_batch_to_database(
                        connection,
                        recipe,
                        write_state,
                        batch_result,
                        embedding_run_id,
                    )
                    vectors_written = vectors_written + batch_vectors_written
                    print(f"[{position}/{len(job_batches)}] Wrote batch {position} ({batch_vectors_written} vectors)")

    return {
        "token_count": total_tokens,
        "vectors_written": vectors_written,
        "skipped_too_large_records": skipped_too_large_records,
    }


def make_streaming_write_state(pending_plans):
    """
    Create lookup dictionaries used while writing embedding batches.

    PARAMETERS:
    - pending_plans: Pending article plans

    RETURNS:
    - A dictionary of article and chunk lookup data
    """
    article_record_by_article_id = {}
    chunk_record_by_chunk_id = {}
    total_chunks_by_article_id = {}
    written_chunks_by_article_id = {}

    for pending_plan in pending_plans:
        article_record = pending_plan["article_record"]
        article_id = article_record["article_id"]
        chunk_records = pending_plan["chunk_records"]

        article_record_by_article_id[article_id] = article_record
        total_chunks_by_article_id[article_id] = len(chunk_records)
        written_chunks_by_article_id[article_id] = 0

        for chunk_record in chunk_records:
            chunk_record_by_chunk_id[chunk_record["chunk_id"]] = chunk_record

    return {
        "article_record_by_article_id": article_record_by_article_id,
        "chunk_record_by_chunk_id": chunk_record_by_chunk_id,
        "total_chunks_by_article_id": total_chunks_by_article_id,
        "written_chunks_by_article_id": written_chunks_by_article_id,
        "started_article_ids": {},
        "skipped_article_ids": {},
    }


def make_runtime_oversized_skip_record(recipe, write_state, skipped_job):
    """
    Build a skip-report record for an input OpenAI rejected during embedding.

    PARAMETERS:
    - recipe: Recipe dictionary
    - write_state: Streaming write state dictionary
    - skipped_job: Skipped job dictionary from embed_one_job_batch

    RETURNS:
    - A skip record dictionary
    """
    job = skipped_job["job"]
    article_id = job["article_id"]
    chunk_id = job["chunk_id"]
    article_record = write_state["article_record_by_article_id"].get(article_id, {})
    chunk_record = write_state["chunk_record_by_chunk_id"].get(chunk_id, {})

    return {
        "article_id": article_id,
        "source": article_record.get("source", ""),
        "title": article_record.get("title", ""),
        "url": article_record.get("url", ""),
        "input_file_path": article_record.get("input_file_path", ""),
        "chunk_id": chunk_id,
        "chunk_index": chunk_record.get("chunk_index"),
        "chunk_character_count": len(job["text"]),
        "estimated_tokens": estimate_input_tokens(job["text"]),
        "safe_token_limit": get_safe_embedding_token_limit(recipe["embedding_model"]),
        "embedding_model": recipe["embedding_model"],
        "chunking_method": recipe["chunking_method"],
        "batch_number": skipped_job["batch_number"],
        "input_index": skipped_job["input_index"],
        "reason": "OpenAI rejected this embedding input because it exceeds the maximum input length",
        "error_text": skipped_job["error_text"],
    }


def record_runtime_skipped_embedding_jobs(connection, recipe, write_state, batch_result):
    """
    Delete stale rows and create skip-report records for runtime skipped jobs.

    PARAMETERS:
    - connection: SQLite connection
    - recipe: Recipe dictionary
    - write_state: Streaming write state dictionary
    - batch_result: Result from embed_one_job_batch

    RETURNS:
    - A list of skip records
    """
    skipped_records = []

    for skipped_job in batch_result.get("skipped_jobs", []):
        skipped_record = make_runtime_oversized_skip_record(recipe, write_state, skipped_job)
        skipped_records.append(skipped_record)
        write_state["skipped_article_ids"][skipped_record["article_id"]] = True
        delete_article_rows(connection, skipped_record["article_id"])
        print(
            "[WARNING] Runtime oversized article skipped: "
            f"{skipped_record['article_id']} ({skipped_record['chunk_character_count']} characters)"
        )

    if skipped_records:
        connection.commit()

    return skipped_records


def make_article_record_with_status(article_record, status):
    """
    Copy an article record and set its build status.

    PARAMETERS:
    - article_record: Article database record
    - status: Status text to store

    RETURNS:
    - A copied article record
    """
    copied_record = dict(article_record)
    copied_record["status"] = status
    return copied_record


def start_streaming_article_if_needed(connection, write_state, article_id):
    """
    Insert an in-progress article row before writing its chunks.

    PARAMETERS:
    - connection: SQLite connection
    - write_state: Streaming write state dictionary
    - article_id: Article id for the current chunk

    RETURNS:
    - None
    """
    if article_id in write_state["started_article_ids"]:
        return

    article_record = write_state["article_record_by_article_id"][article_id]
    delete_article_rows(connection, article_id)
    insert_article(connection, make_article_record_with_status(article_record, "embedding"))
    write_state["started_article_ids"][article_id] = True


def write_embedding_batch_to_database(connection, recipe, write_state, batch_result, embedding_run_id):
    """
    Write one embedded batch to SQLite and commit it.

    PARAMETERS:
    - connection: SQLite connection
    - recipe: Recipe dictionary
    - write_state: Streaming write state dictionary
    - batch_result: Result from embed_one_job_batch
    - embedding_run_id: Unique id for this embedding run

    RETURNS:
    - Number of vectors written
    """
    vector_count = 0
    jobs = batch_result["jobs"]
    vectors = batch_result["vectors"]
    embedding_dimensions = None

    if vectors:
        embedding_dimensions = len(vectors[0])

    for position, job in enumerate(jobs):
        article_id = job["article_id"]
        chunk_id = job["chunk_id"]

        if article_id in write_state["skipped_article_ids"]:
            continue

        start_streaming_article_if_needed(connection, write_state, article_id)

        chunk_record = write_state["chunk_record_by_chunk_id"][chunk_id]
        chunk_rowid = insert_chunk(connection, chunk_record)
        insert_vec1_vector(connection, chunk_rowid, vectors[position])

        write_state["written_chunks_by_article_id"][article_id] = (
            write_state["written_chunks_by_article_id"][article_id] + 1
        )
        vector_count = vector_count + 1

        article_is_complete = (
            write_state["written_chunks_by_article_id"][article_id]
            == write_state["total_chunks_by_article_id"][article_id]
        )

        if article_is_complete:
            set_article_status(connection, article_id, "ready")

    batch_record = {
        "batch_id": f"{embedding_run_id}_batch_{batch_result['batch_number']}",
        "embedding_model": recipe["embedding_model"],
        "embedding_dimensions": embedding_dimensions,
        "token_count": batch_result["token_count"],
        "status": "success",
        "error_text": "",
    }
    insert_embedding_batch(connection, batch_record)
    connection.commit()
    return vector_count


def write_manifest(recipe, output_folder, manifest):
    """
    Write a readable manifest JSON file.

    PARAMETERS:
    - recipe: Recipe dictionary
    - output_folder: Recipe output folder
    - manifest: Manifest dictionary

    RETURNS:
    - Path to the manifest file
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    manifest_path = output_folder / "manifest.json"
    manifest["recipe"] = recipe
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def write_embedding_skip_report(output_folder, skipped_records):
    """
    Write records for articles skipped before embedding.

    PARAMETERS:
    - output_folder: Recipe output folder
    - skipped_records: List of skipped article dictionaries

    RETURNS:
    - Path to the JSONL report
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    report_path = output_folder / "embedding_skipped_articles.jsonl"
    lines = []

    for skipped_record in skipped_records:
        lines.append(json.dumps(skipped_record, ensure_ascii=False))

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_recipe(recipe_name):
    """
    Run one recipe with default options.

    PARAMETERS:
    - recipe_name: The recipe name without .json

    RETURNS:
    - None
    """
    run_recipes([recipe_name], workers=DEFAULT_WORKERS, overwrite_existing=False, yes=False)


def run_recipes(
    recipe_arguments,
    workers=DEFAULT_WORKERS,
    overwrite_existing=False,
    yes=False,
    embedding_batch_size=DEFAULT_EMBEDDING_BATCH_SIZE,
    embedding_max_batch_tokens=DEFAULT_EMBEDDING_MAX_BATCH_TOKENS,
    embedding_request_delay_seconds=DEFAULT_EMBEDDING_REQUEST_DELAY_SECONDS,
    embedding_max_retries=DEFAULT_EMBEDDING_MAX_RETRIES,
    sample_articles=None,
    random_seed=None,
):
    """
    Build one or more KB recipes.

    PARAMETERS:
    - recipe_arguments: "all" or a list of recipe names
    - workers: Worker count for embedding and Vec1 rebuild
    - overwrite_existing: Whether to delete selected output folders first
    - yes: Whether to skip paid-call confirmation
    - embedding_batch_size: Maximum chunks per OpenAI embedding request
    - embedding_max_batch_tokens: Maximum estimated tokens per embedding request
    - embedding_request_delay_seconds: Delay between sequential embedding requests
    - embedding_max_retries: Maximum retries after OpenAI rate limits
    - sample_articles: Optional number of random articles to select
    - random_seed: Optional random seed for reproducible sampling

    RETURNS:
    - None
    """
    if workers < 1:
        raise ValueError("--workers must be at least 1")

    if embedding_batch_size < 1:
        raise ValueError("--embedding-batch-size must be at least 1")

    if embedding_max_batch_tokens < 1:
        raise ValueError("--embedding-max-batch-tokens must be at least 1")

    if embedding_request_delay_seconds < 0:
        raise ValueError("--embedding-request-delay-seconds cannot be negative")

    if embedding_max_retries < 0:
        raise ValueError("--embedding-max-retries cannot be negative")

    if sample_articles is not None and sample_articles < 1:
        raise ValueError("--sample-articles must be at least 1")

    recipe_names = resolve_selected_recipe_names(recipe_arguments)
    recipes = []
    article_filter_options = make_article_filter_options(
        sample_articles,
        random_seed,
    )

    for recipe_name in recipe_names:
        recipes.append(load_recipe(recipe_name))

    print("[INFO] Knowledge-base build")
    print(f"[INFO] Recipes selected: {len(recipes)}")
    print(f"[INFO] Workers: {workers}")
    print(f"[INFO] Embedding batch size: {embedding_batch_size}")
    print(f"[INFO] Embedding max batch tokens: {embedding_max_batch_tokens}")
    print(f"[INFO] Embedding request delay seconds: {embedding_request_delay_seconds}")
    print(f"[INFO] Embedding max retries: {embedding_max_retries}")
    print(f"[INFO] overwrite existing KBs: {overwrite_existing}")
    print(f"[INFO] Article sample size: {sample_articles}")
    print(f"[INFO] Article random seed: {article_filter_options['random_seed']}")

    if workers > 1:
        print("[WARNING] Multiple embedding workers can still hit OpenAI rate limits. Use --workers 1 for slow runs.")

    if sample_articles is not None and not overwrite_existing:
        print("[WARNING] Sampling without --overwrite-existing can leave older non-sampled articles in an existing KB.")

    vec1_extension_path = find_vec1_extension()
    print(f"[INFO] Vec1 extension: {vec1_extension_path}")

    build_plans = []
    all_texts_to_embed = []

    for recipe in recipes:
        build_plan = prepare_recipe_build_plan(recipe, overwrite_existing, vec1_extension_path, article_filter_options)
        build_plans.append(build_plan)

        for job in build_plan["embedding_jobs"]:
            all_texts_to_embed.append(job["text"])

    estimated_tokens = estimate_tokens_from_texts(all_texts_to_embed)
    estimated_cost = 0.0
    total_chunks = 0

    for build_plan in build_plans:
        recipe = build_plan["recipe"]
        require_embedding_credentials(recipe)
        recipe_texts = []

        for job in build_plan["embedding_jobs"]:
            recipe_texts.append(job["text"])

        recipe_tokens = estimate_tokens_from_texts(recipe_texts)
        estimated_cost = estimated_cost + estimate_embedding_cost(recipe["embedding_model"], recipe_tokens)
        total_chunks = total_chunks + len(build_plan["embedding_jobs"])

    if not confirm_paid_embedding_call(total_chunks, estimated_tokens, round(estimated_cost, 6), yes):
        print("[INFO] Build cancelled before embedding API calls")
        return

    for build_plan in build_plans:
        client = build_embedding_client(build_plan["recipe"])
        run_prepared_build_plan(
            build_plan,
            client,
            workers,
            embedding_batch_size,
            embedding_max_batch_tokens,
            embedding_request_delay_seconds,
            embedding_max_retries,
        )


def prepare_recipe_build_plan(recipe, overwrite_existing, vec1_extension_path, article_filter_options):
    """
    Prepare one recipe build plan before OpenAI calls.

    PARAMETERS:
    - recipe: Recipe dictionary
    - overwrite_existing: Whether to delete this output folder first
    - vec1_extension_path: Path to the compiled Vec1 extension
    - article_filter_options: Build-time corpus filter options

    RETURNS:
    - Build plan dictionary
    """
    output_folder = Path(recipe["output_folder"])
    db_path = output_folder / "kb.sqlite"

    if overwrite_existing and output_folder.exists():
        print(f"[WARNING] Removing existing KB folder: {output_folder}")
        shutil.rmtree(output_folder)

    output_folder.mkdir(parents=True, exist_ok=True)

    connection = open_kb_database(db_path)
    create_kb_schema(connection)
    load_vec1_extension(connection, vec1_extension_path)
    create_vec1_table(connection)

    articles = load_clean_articles(recipe["input_corpus"])
    filter_summary = filter_articles_for_build(articles, article_filter_options)
    filtered_articles = filter_summary["articles"]
    pending_summary = build_pending_article_plans(recipe, connection, filtered_articles)
    embedding_jobs = make_embedding_jobs(pending_summary["pending_plans"])

    connection.close()

    print(f"[INFO] Recipe: {recipe['name']}")
    print(f"    clean articles available: {len(articles)}")
    print(f"    articles after filters: {len(filtered_articles)}")
    print(f"    articles before random sample: {filter_summary['before_sample_count']}")
    print(f"    random sample applied: {filter_summary['sample_applied']}")
    print(f"    new articles: {pending_summary['new_articles']}")
    print(f"    changed articles: {pending_summary['changed_articles']}")
    print(f"    skipped unchanged articles: {pending_summary['skipped_unchanged']}")
    print(f"    skipped too-large articles: {pending_summary['skipped_too_large']}")
    print(f"    chunks to embed: {len(embedding_jobs)}")

    return {
        "recipe": recipe,
        "db_path": db_path,
        "vec1_extension_path": vec1_extension_path,
        "articles_loaded": len(articles),
        "article_filter_options": article_filter_options,
        "article_filter_summary": filter_summary,
        "pending_plans": pending_summary["pending_plans"],
        "embedding_jobs": embedding_jobs,
        "new_articles": pending_summary["new_articles"],
        "changed_articles": pending_summary["changed_articles"],
        "skipped_unchanged": pending_summary["skipped_unchanged"],
        "skipped_too_large": pending_summary["skipped_too_large"],
        "skipped_too_large_records": pending_summary["skipped_too_large_records"],
    }


def run_prepared_build_plan(
    build_plan,
    client,
    workers,
    embedding_batch_size,
    embedding_max_batch_tokens,
    embedding_request_delay_seconds,
    embedding_max_retries,
):
    """
    Execute one prepared recipe build plan.

    PARAMETERS:
    - build_plan: Dictionary from prepare_recipe_build_plan
    - client: OpenAI client
    - workers: Worker count
    - embedding_batch_size: Maximum chunks per OpenAI embedding request
    - embedding_max_batch_tokens: Maximum estimated tokens per embedding request
    - embedding_request_delay_seconds: Delay between sequential embedding requests
    - embedding_max_retries: Maximum retries after OpenAI rate limits

    RETURNS:
    - None
    """
    recipe = build_plan["recipe"]
    start_time = time.time()
    skip_report_path = write_embedding_skip_report(recipe["output_folder"], build_plan["skipped_too_large_records"])
    build_plan["embedding_batch_size"] = embedding_batch_size
    build_plan["embedding_max_batch_tokens"] = embedding_max_batch_tokens
    build_plan["embedding_request_delay_seconds"] = embedding_request_delay_seconds
    build_plan["embedding_max_retries"] = embedding_max_retries

    print(f"[INFO] Building recipe: {recipe['name']}")
    if build_plan["skipped_too_large_records"]:
        print(f"[WARNING] Oversized articles skipped before embedding: {len(build_plan['skipped_too_large_records'])}")
        print(f"[INFO] Skip report: {skip_report_path}")

    connection = open_kb_database(build_plan["db_path"])
    create_kb_schema(connection)
    load_vec1_extension(connection, build_plan["vec1_extension_path"])
    create_vec1_table(connection)

    for skipped_record in build_plan["skipped_too_large_records"]:
        delete_article_rows(connection, skipped_record["article_id"])

    connection.commit()

    if not build_plan["embedding_jobs"]:
        print("[INFO] No new or changed chunks to embed")
        index_status = rebuild_vec1_index(connection, workers, recipe["search_distance"])
        manifest = make_manifest(recipe, build_plan, connection, 0, 0, index_status, start_time)
        write_manifest(recipe, recipe["output_folder"], manifest)
        connection.close()
        return

    embedding_run_id = f"{recipe['name']}_{time.time_ns()}"
    embedding_result = embed_and_write_jobs(
        connection,
        recipe,
        build_plan["pending_plans"],
        client,
        recipe,
        build_plan["embedding_jobs"],
        workers,
        embedding_run_id,
        batch_size=embedding_batch_size,
        max_batch_tokens=embedding_max_batch_tokens,
        request_delay_seconds=embedding_request_delay_seconds,
        max_retries=embedding_max_retries,
    )
    vectors_written = embedding_result["vectors_written"]

    runtime_skipped_records = embedding_result.get("skipped_too_large_records", [])
    if runtime_skipped_records:
        skipped_article_ids = {}

        for skipped_record in build_plan["skipped_too_large_records"]:
            skipped_article_ids[skipped_record["article_id"]] = True

        for skipped_record in runtime_skipped_records:
            if skipped_record["article_id"] not in skipped_article_ids:
                build_plan["skipped_too_large"] = build_plan["skipped_too_large"] + 1
                skipped_article_ids[skipped_record["article_id"]] = True

        build_plan["skipped_too_large_records"].extend(runtime_skipped_records)
        skip_report_path = write_embedding_skip_report(recipe["output_folder"], build_plan["skipped_too_large_records"])
        print(f"[WARNING] Oversized articles skipped during embedding: {len(runtime_skipped_records)}")
        print(f"[INFO] Skip report updated: {skip_report_path}")

    print(f"[INFO] Vectors written: {vectors_written}")
    print("[INFO] Rebuilding Vec1 index")
    index_status = rebuild_vec1_index(connection, workers, recipe["search_distance"])
    print(f"[INFO] Vec1 index status: {index_status}")

    manifest = make_manifest(
        recipe,
        build_plan,
        connection,
        embedding_result["token_count"],
        vectors_written,
        index_status,
        start_time,
    )
    manifest_path = write_manifest(recipe, recipe["output_folder"], manifest)
    connection.close()
    print(f"[INFO] Manifest written: {manifest_path}")


def make_manifest(recipe, build_plan, connection, token_count, vectors_written, index_status, start_time):
    """
    Build a manifest dictionary for one recipe run.

    PARAMETERS:
    - recipe: Recipe dictionary
    - build_plan: Prepared build plan
    - connection: sqlite3 connection
    - token_count: OpenAI token count
    - vectors_written: New vector count
    - index_status: Vec1 index status string
    - start_time: Build start time from time.time()

    RETURNS:
    - Manifest dictionary
    """
    end_time = time.time()
    estimated_cost = estimate_embedding_cost(recipe["embedding_model"], token_count)

    return {
        "recipe_name": recipe["name"],
        "input_corpus": recipe["input_corpus"],
        "output_folder": recipe["output_folder"],
        "embedding_provider": recipe["embedding_provider"],
        "embedding_model": recipe["embedding_model"],
        "embedding_dimensions": recipe["embedding_dimensions"],
        "chunking_method": recipe["chunking_method"],
        "chunk_size_characters": recipe["chunk_size_characters"],
        "chunk_overlap_characters": recipe["chunk_overlap_characters"],
        "articles_loaded": build_plan["articles_loaded"],
        "article_filter_options": build_plan["article_filter_options"],
        "articles_before_random_sample": build_plan["article_filter_summary"]["before_sample_count"],
        "articles_after_filters": build_plan["article_filter_summary"]["after_filter_count"],
        "article_random_sample_applied": build_plan["article_filter_summary"]["sample_applied"],
        "article_count": count_table_rows(connection, "articles"),
        "chunk_count": count_table_rows(connection, "chunks"),
        "vector_count": count_table_rows(connection, "vec1_chunks"),
        "new_article_count": build_plan["new_articles"],
        "changed_article_count": build_plan["changed_articles"],
        "skipped_unchanged_article_count": build_plan["skipped_unchanged"],
        "skipped_too_large_article_count": build_plan["skipped_too_large"],
        "embedding_skip_report_path": str(Path(recipe["output_folder"]) / "embedding_skipped_articles.jsonl"),
        "embedding_batch_size": build_plan.get("embedding_batch_size"),
        "embedding_max_batch_tokens": build_plan.get("embedding_max_batch_tokens"),
        "embedding_request_delay_seconds": build_plan.get("embedding_request_delay_seconds"),
        "embedding_max_retries": build_plan.get("embedding_max_retries"),
        "new_vector_count": vectors_written,
        "embedding_token_count": token_count,
        "estimated_embedding_cost_eur": estimated_cost,
        "build_time_seconds": round(end_time - start_time, 2),
        "build_status": "complete",
        "vec1_extension_path": str(build_plan["vec1_extension_path"]),
        "vec1_index_status": index_status,
    }
