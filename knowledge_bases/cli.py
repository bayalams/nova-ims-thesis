"""
Command-line interface for knowledge-base recipes.
"""

import sys
import subprocess

from knowledge_bases.build_knowledge_base import DEFAULT_EMBEDDING_BATCH_SIZE
from knowledge_bases.build_knowledge_base import DEFAULT_EMBEDDING_MAX_BATCH_TOKENS
from knowledge_bases.build_knowledge_base import DEFAULT_EMBEDDING_MAX_RETRIES
from knowledge_bases.build_knowledge_base import DEFAULT_EMBEDDING_REQUEST_DELAY_SECONDS
from knowledge_bases.build_knowledge_base import DEFAULT_WORKERS
from knowledge_bases.build_knowledge_base import explain_recipe_text
from knowledge_bases.build_knowledge_base import list_recipe_names
from knowledge_bases.build_knowledge_base import parse_timestamp_to_epoch
from knowledge_bases.build_knowledge_base import print_status
from knowledge_bases.build_knowledge_base import run_recipe
from knowledge_bases.build_knowledge_base import run_recipes
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_SAMPLE_SIZE
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_WINDOW_BATCH_SIZE
from knowledge_bases.evaluation.evaluate_kbs import evaluate_recipes
from knowledge_bases.evaluation.entity_precompute import DEFAULT_ENTITY_PRECOMPUTE_BATCH_SIZE
from knowledge_bases.evaluation.entity_precompute import DEFAULT_ENTITY_PRECOMPUTE_DEVICE
from knowledge_bases.evaluation.entity_precompute import run_precompute_entities
from knowledge_bases.evaluation.retrieval_metrics import DEFAULT_RETRIEVAL_SAMPLE_SIZE
from knowledge_bases.evaluation.retrieval_metrics import DEFAULT_RETRIEVAL_SEARCH_MODE
from knowledge_bases.evaluation.retrieval_metrics import DEFAULT_RETRIEVAL_TOP_K
from knowledge_bases.retrieval.search_sqlite import search_recipe


def print_help():
    """
    Print available build-kb commands.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    print("Knowledge-base commands:")
    print("  uv run build-kb list-recipes")
    print("  uv run build-kb status")
    print("  uv run build-kb setup-vec1")
    print("  uv run build-kb explain-recipe news_no_chunking_3small")
    print("  uv run build-kb run all --workers 2")
    print("  uv run build-kb run news_no_chunking_3small --yes")
    print("  uv run build-kb run news_no_chunking_3small --sample-articles 100 --random-seed 42 --overwrite-existing")
    print("  uv run build-kb run all --yes --workers 4 --embedding-batch-size 50")
    print("  uv run build-kb precompute-entities all")
    print("  uv run build-kb precompute-entities news_fixed_2000_overlap_3large --limit 100")
    print("  uv run --env-file .env build-kb evaluate all --table --output shared_data/knowledge_bases/evaluation_metrics.json")
    print("  uv run --env-file .env build-kb evaluate all --retrieval-sample-size 100")
    print("  uv run --env-file .env build-kb evaluate all --entity-sample-size 100")
    print("  uv run --env-file .env build-kb evaluate all --entity-device cpu --entity-window-batch-size 1")
    print("  uv run build-kb search news_no_chunking_3small \"query text\" --top-k 10")
    print("  uv run build-kb search news_no_chunking_3small \"query text\" --indexed-before 2026-05-01T00:00:00+00:00")


def setup_vec1():
    """
    Run the local Vec1 setup script.

    PARAMETERS:
    - None

    RETURNS:
    - The shell script return code
    """
    print("[INFO] Running Vec1 setup script", flush=True)
    completed_process = subprocess.run(["bash", "knowledge_bases/setup_vec1.sh"], check=False)
    return completed_process.returncode


def print_recipe_list():
    """
    Print every available KB recipe.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    recipe_names = list_recipe_names()
    print("[INFO] Knowledge-base recipes")

    for position, recipe_name in enumerate(recipe_names, start=1):
        print(f"[{position}/{len(recipe_names)}] {recipe_name}")


def parse_run_arguments(arguments):
    """
    Parse build-kb run arguments.

    PARAMETERS:
    - arguments: Arguments after "run"

    RETURNS:
    - A dictionary with recipe names and flags
    """
    recipe_arguments = []
    workers = DEFAULT_WORKERS
    embedding_batch_size = DEFAULT_EMBEDDING_BATCH_SIZE
    embedding_max_batch_tokens = DEFAULT_EMBEDDING_MAX_BATCH_TOKENS
    embedding_request_delay_seconds = DEFAULT_EMBEDDING_REQUEST_DELAY_SECONDS
    embedding_max_retries = DEFAULT_EMBEDDING_MAX_RETRIES
    sample_articles = None
    random_seed = None
    overwrite_existing = False
    yes = False
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--workers":
            if position + 1 >= len(arguments):
                raise ValueError("--workers needs a number")
            workers = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--embedding-batch-size":
            if position + 1 >= len(arguments):
                raise ValueError("--embedding-batch-size needs a number")
            embedding_batch_size = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--embedding-max-batch-tokens":
            if position + 1 >= len(arguments):
                raise ValueError("--embedding-max-batch-tokens needs a number")
            embedding_max_batch_tokens = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--embedding-request-delay-seconds":
            if position + 1 >= len(arguments):
                raise ValueError("--embedding-request-delay-seconds needs a number")
            embedding_request_delay_seconds = float(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--embedding-max-retries":
            if position + 1 >= len(arguments):
                raise ValueError("--embedding-max-retries needs a number")
            embedding_max_retries = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--sample-articles":
            if position + 1 >= len(arguments):
                raise ValueError("--sample-articles needs a number")
            sample_articles = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--random-seed":
            if position + 1 >= len(arguments):
                raise ValueError("--random-seed needs a number")
            random_seed = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--overwrite-existing":
            overwrite_existing = True
            position = position + 1
            continue

        if argument == "--yes":
            yes = True
            position = position + 1
            continue

        if argument.startswith("--"):
            raise ValueError(f"Unknown run option: {argument}")

        recipe_arguments.append(argument)
        position = position + 1

    if not recipe_arguments:
        raise ValueError("run needs at least one recipe name or all")

    return {
        "recipe_arguments": recipe_arguments,
        "workers": workers,
        "embedding_batch_size": embedding_batch_size,
        "embedding_max_batch_tokens": embedding_max_batch_tokens,
        "embedding_request_delay_seconds": embedding_request_delay_seconds,
        "embedding_max_retries": embedding_max_retries,
        "sample_articles": sample_articles,
        "random_seed": random_seed,
        "overwrite_existing": overwrite_existing,
        "yes": yes,
    }


def parse_search_arguments(arguments):
    """
    Parse build-kb search arguments.

    PARAMETERS:
    - arguments: Arguments after "search"

    RETURNS:
    - A dictionary with search options
    """
    if len(arguments) < 2:
        raise ValueError("search needs a recipe name and query text")

    recipe_name = arguments[0]
    query_text = arguments[1]
    top_k = 10
    search_mode = "ann"
    indexed_before = None
    position = 2

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--top-k":
            if position + 1 >= len(arguments):
                raise ValueError("--top-k needs a number")
            top_k = int(arguments[position + 1])
            position = position + 2
            continue

        if argument == "--search-mode":
            if position + 1 >= len(arguments):
                raise ValueError("--search-mode needs ann or exact")
            search_mode = arguments[position + 1]
            position = position + 2
            continue

        if argument == "--indexed-before":
            if position + 1 >= len(arguments):
                raise ValueError("--indexed-before needs a timestamp")
            indexed_before = arguments[position + 1]
            if parse_timestamp_to_epoch(indexed_before) is None:
                raise ValueError(f"Could not parse --indexed-before timestamp: {indexed_before}")
            position = position + 2
            continue

        raise ValueError(f"Unknown search option: {argument}")

    return {
        "recipe_name": recipe_name,
        "query_text": query_text,
        "top_k": top_k,
        "search_mode": search_mode,
        "indexed_before": indexed_before,
    }


def parse_evaluate_arguments(arguments):
    """
    Parse build-kb evaluate arguments.

    PARAMETERS:
    - arguments: Arguments after "evaluate"

    RETURNS:
    - A dictionary with recipe names and output path
    """
    recipe_arguments = []
    output_path = None
    write_tables = False
    markdown_table_path = None
    csv_table_path = None
    retrieval_metrics = True
    retrieval_sample_size = DEFAULT_RETRIEVAL_SAMPLE_SIZE
    retrieval_top_k = DEFAULT_RETRIEVAL_TOP_K
    retrieval_search_mode = DEFAULT_RETRIEVAL_SEARCH_MODE
    entity_sample_size = DEFAULT_ENTITY_SAMPLE_SIZE
    entity_device = "auto"
    entity_window_batch_size = DEFAULT_ENTITY_WINDOW_BATCH_SIZE
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--retrieval-metrics":
            retrieval_metrics = True
            position = position + 1
            continue

        if argument == "--retrieval-sample-size":
            if position + 1 >= len(arguments):
                raise ValueError("--retrieval-sample-size needs a number")
            retrieval_sample_size = int(arguments[position + 1])
            if retrieval_sample_size < 1:
                raise ValueError("--retrieval-sample-size must be at least 1")
            position = position + 2
            continue

        if argument == "--retrieval-top-k":
            if position + 1 >= len(arguments):
                raise ValueError("--retrieval-top-k needs a number")
            retrieval_top_k = int(arguments[position + 1])
            if retrieval_top_k < 1:
                raise ValueError("--retrieval-top-k must be at least 1")
            position = position + 2
            continue

        if argument == "--retrieval-search-mode":
            if position + 1 >= len(arguments):
                raise ValueError("--retrieval-search-mode needs exact or ann")
            retrieval_search_mode = arguments[position + 1]
            if retrieval_search_mode not in ["exact", "ann"]:
                raise ValueError("--retrieval-search-mode must be exact or ann")
            position = position + 2
            continue

        if argument == "--entity-sample-size":
            if position + 1 >= len(arguments):
                raise ValueError("--entity-sample-size needs a number")
            entity_sample_size = int(arguments[position + 1])
            if entity_sample_size < 1:
                raise ValueError("--entity-sample-size must be at least 1")
            position = position + 2
            continue

        if argument == "--entity-device":
            if position + 1 >= len(arguments):
                raise ValueError("--entity-device needs auto, cpu, or mps")
            entity_device = arguments[position + 1]
            if entity_device not in ["auto", "cpu", "mps"]:
                raise ValueError("--entity-device must be auto, cpu, or mps")
            position = position + 2
            continue

        if argument == "--entity-window-batch-size":
            if position + 1 >= len(arguments):
                raise ValueError("--entity-window-batch-size needs a number")
            entity_window_batch_size = int(arguments[position + 1])
            if entity_window_batch_size < 1:
                raise ValueError("--entity-window-batch-size must be at least 1")
            position = position + 2
            continue

        if argument == "--table":
            write_tables = True
            position = position + 1
            continue

        if argument == "--output":
            if position + 1 >= len(arguments):
                raise ValueError("--output needs a file path")
            output_path = arguments[position + 1]
            position = position + 2
            continue

        if argument == "--markdown-table":
            if position + 1 >= len(arguments):
                raise ValueError("--markdown-table needs a file path")
            markdown_table_path = arguments[position + 1]
            write_tables = True
            position = position + 2
            continue

        if argument == "--csv-table":
            if position + 1 >= len(arguments):
                raise ValueError("--csv-table needs a file path")
            csv_table_path = arguments[position + 1]
            write_tables = True
            position = position + 2
            continue

        if argument.startswith("--"):
            raise ValueError(f"Unknown evaluate option: {argument}")

        recipe_arguments.append(argument)
        position = position + 1

    if not recipe_arguments:
        raise ValueError("evaluate needs at least one recipe name or all")

    return {
        "recipe_arguments": recipe_arguments,
        "output_path": output_path,
        "write_tables": write_tables,
        "markdown_table_path": markdown_table_path,
        "csv_table_path": csv_table_path,
        "retrieval_metrics": retrieval_metrics,
        "retrieval_sample_size": retrieval_sample_size,
        "retrieval_top_k": retrieval_top_k,
        "retrieval_search_mode": retrieval_search_mode,
        "entity_sample_size": entity_sample_size,
        "entity_device": entity_device,
        "entity_window_batch_size": entity_window_batch_size,
    }


def parse_precompute_entities_arguments(arguments):
    """
    Parse build-kb precompute-entities arguments.

    PARAMETERS:
    - arguments: Arguments after "precompute-entities"

    RETURNS:
    - A dictionary with recipe names and NER options
    """
    recipe_arguments = []
    device = DEFAULT_ENTITY_PRECOMPUTE_DEVICE
    batch_size = DEFAULT_ENTITY_PRECOMPUTE_BATCH_SIZE
    limit = None
    overwrite_existing = False
    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--device":
            if position + 1 >= len(arguments):
                raise ValueError("--device needs auto, cpu, or mps")
            device = arguments[position + 1]
            if device not in ["auto", "cpu", "mps"]:
                raise ValueError("--device must be auto, cpu, or mps")
            position = position + 2
            continue

        if argument == "--batch-size":
            if position + 1 >= len(arguments):
                raise ValueError("--batch-size needs a number")
            batch_size = int(arguments[position + 1])
            if batch_size < 1:
                raise ValueError("--batch-size must be at least 1")
            position = position + 2
            continue

        if argument == "--limit":
            if position + 1 >= len(arguments):
                raise ValueError("--limit needs a number")
            limit = int(arguments[position + 1])
            if limit < 1:
                raise ValueError("--limit must be at least 1")
            position = position + 2
            continue

        if argument == "--overwrite-existing":
            overwrite_existing = True
            position = position + 1
            continue

        if argument.startswith("--"):
            raise ValueError(f"Unknown precompute-entities option: {argument}")

        recipe_arguments.append(argument)
        position = position + 1

    if not recipe_arguments:
        raise ValueError("precompute-entities needs at least one recipe name or all")

    return {
        "recipe_arguments": recipe_arguments,
        "device": device,
        "batch_size": batch_size,
        "limit": limit,
        "overwrite_existing": overwrite_existing,
    }


def main(arguments=None):
    """
    Run the knowledge-base command-line interface.

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

    try:
        if command == "list-recipes":
            print_recipe_list()
            return 0

        if command == "status":
            print_status()
            return 0

        if command == "setup-vec1":
            return setup_vec1()

        if command == "explain-recipe" and len(arguments) == 2:
            print(explain_recipe_text(arguments[1]))
            return 0

        if command == "run" and len(arguments) >= 2:
            run_options = parse_run_arguments(arguments[1:])
            run_recipes(
                run_options["recipe_arguments"],
                workers=run_options["workers"],
                embedding_batch_size=run_options["embedding_batch_size"],
                embedding_max_batch_tokens=run_options["embedding_max_batch_tokens"],
                embedding_request_delay_seconds=run_options["embedding_request_delay_seconds"],
                embedding_max_retries=run_options["embedding_max_retries"],
                sample_articles=run_options["sample_articles"],
                random_seed=run_options["random_seed"],
                overwrite_existing=run_options["overwrite_existing"],
                yes=run_options["yes"],
            )
            return 0

        if command == "evaluate" and len(arguments) >= 2:
            evaluate_options = parse_evaluate_arguments(arguments[1:])
            evaluate_recipes(
                evaluate_options["recipe_arguments"],
                output_path=evaluate_options["output_path"],
                write_tables=evaluate_options["write_tables"],
                markdown_table_path=evaluate_options["markdown_table_path"],
                csv_table_path=evaluate_options["csv_table_path"],
                retrieval_metrics=evaluate_options["retrieval_metrics"],
                retrieval_sample_size=evaluate_options["retrieval_sample_size"],
                retrieval_top_k=evaluate_options["retrieval_top_k"],
                retrieval_search_mode=evaluate_options["retrieval_search_mode"],
                entity_sample_size=evaluate_options["entity_sample_size"],
                entity_device=evaluate_options["entity_device"],
                entity_window_batch_size=evaluate_options["entity_window_batch_size"],
            )
            return 0

        if command == "precompute-entities" and len(arguments) >= 2:
            precompute_options = parse_precompute_entities_arguments(arguments[1:])
            run_precompute_entities(
                precompute_options["recipe_arguments"],
                device=precompute_options["device"],
                batch_size=precompute_options["batch_size"],
                limit=precompute_options["limit"],
                overwrite_existing=precompute_options["overwrite_existing"],
            )
            return 0

        if command == "search" and len(arguments) >= 3:
            search_options = parse_search_arguments(arguments[1:])
            search_recipe(
                search_options["recipe_name"],
                search_options["query_text"],
                search_options["top_k"],
                search_options["search_mode"],
                search_options["indexed_before"],
            )
            return 0
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    print(f"[ERROR] Unknown build-kb command: {' '.join(arguments)}")
    print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
