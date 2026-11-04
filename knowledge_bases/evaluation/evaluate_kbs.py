"""
Evaluate knowledge-base builds using local, deterministic metrics.

This module is the command-facing orchestration layer. Metric calculations,
SQLite reads, clean article loading, and table rendering live in smaller
modules in this package.
"""

import json
import sqlite3
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path

from knowledge_bases.build_knowledge_base import load_recipe
from knowledge_bases.build_knowledge_base import resolve_selected_recipe_names
from knowledge_bases.evaluation.articles import get_cached_clean_articles
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_CACHE_PATH
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_MENTIONS_PATH
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_SAMPLE_SIZE
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_STORE_PATH
from knowledge_bases.evaluation.constants import DEFAULT_ENTITY_WINDOW_BATCH_SIZE
from knowledge_bases.evaluation.constants import DEFAULT_EVALUATION_OUTPUT_PATH
from knowledge_bases.evaluation.constants import PENDING_METRICS
from knowledge_bases.evaluation.database import fetch_article_rows
from knowledge_bases.evaluation.database import fetch_chunk_rows
from knowledge_bases.evaluation.database import get_table_columns
from knowledge_bases.evaluation.database import get_table_names
from knowledge_bases.evaluation.entity_metrics import calculate_entity_pair_preservation_rate
from knowledge_bases.evaluation.entity_metrics import make_entity_metric_artifacts
from knowledge_bases.evaluation.entity_metrics import make_entity_metric_config
from knowledge_bases.evaluation.entity_metrics import reset_entity_mentions_file
from knowledge_bases.evaluation.entity_precompute import resolve_entity_device
from knowledge_bases.evaluation.metrics import make_diagnostic_metrics
from knowledge_bases.evaluation.metrics import make_empty_diagnostic_metrics
from knowledge_bases.evaluation.metrics import make_missing_database_sanity_metrics
from knowledge_bases.evaluation.metrics import make_pending_thesis_metrics
from knowledge_bases.evaluation.metrics import make_sanity_metrics
from knowledge_bases.evaluation.metrics import make_thesis_metrics
from knowledge_bases.evaluation.retrieval_metrics import DEFAULT_RETRIEVAL_SAMPLE_SIZE
from knowledge_bases.evaluation.retrieval_metrics import DEFAULT_RETRIEVAL_SEARCH_MODE
from knowledge_bases.evaluation.retrieval_metrics import DEFAULT_RETRIEVAL_TOP_K
from knowledge_bases.evaluation.retrieval_metrics import evaluate_retrieval_metrics
from knowledge_bases.evaluation.retrieval_metrics import make_error_retrieval_metrics
from knowledge_bases.evaluation.retrieval_metrics import make_not_requested_retrieval_metrics
from knowledge_bases.evaluation.retrieval_metrics import make_retrieval_options
from knowledge_bases.evaluation.tables import make_comparison_table_rows
from knowledge_bases.evaluation.tables import make_default_table_paths
from knowledge_bases.evaluation.tables import write_comparison_tables
from knowledge_bases.evaluation.thesis_retrieval_metrics import make_empty_thesis_retrieval_metrics
from knowledge_bases.evaluation.utils import format_optional_rate
from knowledge_bases.evaluation.utils import load_json_file


def evaluate_recipes(
    recipe_arguments,
    output_path=None,
    write_tables=False,
    markdown_table_path=None,
    csv_table_path=None,
    retrieval_metrics=True,
    retrieval_sample_size=DEFAULT_RETRIEVAL_SAMPLE_SIZE,
    retrieval_top_k=DEFAULT_RETRIEVAL_TOP_K,
    retrieval_search_mode=DEFAULT_RETRIEVAL_SEARCH_MODE,
    retrieval_search_function=None,
    entity_extractor_function=None,
    entity_sample_size=DEFAULT_ENTITY_SAMPLE_SIZE,
    entity_cache_path=None,
    entity_mentions_path=None,
    entity_store_path=None,
    entity_device="auto",
    entity_window_batch_size=DEFAULT_ENTITY_WINDOW_BATCH_SIZE,
):
    """
    Evaluate one or more KB recipes and write a JSON report.

    PARAMETERS:
    - recipe_arguments: Recipe names, or ["all"]
    - output_path: Optional JSON output path
    - write_tables: Whether to write Markdown and CSV comparison tables
    - markdown_table_path: Optional Markdown table path
    - csv_table_path: Optional CSV table path
    - retrieval_metrics: Whether to run retrieval metrics
    - retrieval_sample_size: Number of indexed article ids to query
    - retrieval_top_k: Number of results per retrieval query
    - retrieval_search_mode: exact or ann
    - retrieval_search_function: Optional fake search function for tests
    - entity_extractor_function: Optional fake entity extractor for tests
    - entity_sample_size: Number of indexed articles for entity-pair metrics
    - entity_cache_path: Optional entity cache path for tests
    - entity_mentions_path: Optional entity mentions path for tests
    - entity_store_path: Optional SQLite precomputed entity store path
    - entity_device: Device name used for precomputed entity cache keys
    - entity_window_batch_size: GLiNER text-window batch size

    RETURNS:
    - Report dictionary
    """
    recipe_names = resolve_selected_recipe_names(recipe_arguments)
    if not recipe_names:
        raise ValueError("evaluate needs at least one recipe name or all")

    print("[INFO] Evaluating knowledge-base recipes")

    started_at = time.time()
    recipe_reports = []
    clean_articles_cache = {}
    retrieval_embedding_cache = {}
    retrieval_runtime = {}
    entity_metric_config = make_entity_metric_config()
    entity_metric_config["entity_window_batch_size"] = entity_window_batch_size
    entity_metric_runtime = {}
    if entity_cache_path is None:
        entity_cache_path = DEFAULT_ENTITY_CACHE_PATH
    if entity_mentions_path is None:
        entity_mentions_path = DEFAULT_ENTITY_MENTIONS_PATH
    if entity_store_path is None:
        entity_store_path = DEFAULT_ENTITY_STORE_PATH
    resolved_entity_device = entity_device
    if entity_extractor_function is None:
        resolved_entity_device = resolve_entity_device(entity_device)
    print(f"[INFO] Entity device: {resolved_entity_device}", flush=True)
    print(f"[INFO] Entity window batch size: {entity_window_batch_size}", flush=True)
    reset_entity_mentions_file(entity_mentions_path)
    retrieval_options = make_retrieval_options(
        retrieval_metrics,
        retrieval_sample_size,
        retrieval_top_k,
        retrieval_search_mode,
    )

    for position, recipe_name in enumerate(recipe_names, start=1):
        print(f"[{position}/{len(recipe_names)}] Evaluating recipe: {recipe_name}", flush=True)

        try:
            recipe = load_recipe(recipe_name)
            recipe_report = evaluate_recipe(
                recipe=recipe,
                clean_articles_cache=clean_articles_cache,
                retrieval_options=retrieval_options,
                retrieval_embedding_cache=retrieval_embedding_cache,
                retrieval_runtime=retrieval_runtime,
                retrieval_search_function=retrieval_search_function,
                entity_metric_config=entity_metric_config,
                entity_metric_runtime=entity_metric_runtime,
                entity_extractor_function=entity_extractor_function,
                reset_entity_mentions=False,
                entity_sample_size=entity_sample_size,
                entity_cache_path=entity_cache_path,
                entity_mentions_path=entity_mentions_path,
                entity_store_path=entity_store_path,
                entity_device=resolved_entity_device,
                entity_window_batch_size=entity_window_batch_size,
            )
        except Exception as error:
            recipe_report = make_recipe_error_report(
                recipe_name,
                retrieval_options,
                retrieval_metrics,
                error,
                entity_metric_config,
                entity_cache_path,
                entity_mentions_path,
                entity_store_path,
            )

        recipe_reports.append(recipe_report)
        print_recipe_summary(recipe_report)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started_at, 2),
        "recipe_count": len(recipe_reports),
        "recipes": recipe_reports,
    }

    final_output_path = output_path
    if final_output_path is None:
        final_output_path = DEFAULT_EVALUATION_OUTPUT_PATH

    final_output_path = Path(final_output_path)
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[INFO] Evaluation report written: {final_output_path}")

    if write_tables:
        table_result = write_tables_for_report(
            report,
            final_output_path,
            markdown_table_path,
            csv_table_path,
        )
        report["comparison_table_paths"] = table_result

    return report


def evaluate_recipe(
    recipe,
    clean_articles_cache=None,
    retrieval_options=None,
    retrieval_embedding_cache=None,
    retrieval_runtime=None,
    retrieval_search_function=None,
    entity_metric_config=None,
    entity_metric_runtime=None,
    entity_extractor_function=None,
    reset_entity_mentions=True,
    entity_sample_size=DEFAULT_ENTITY_SAMPLE_SIZE,
    entity_cache_path=None,
    entity_mentions_path=None,
    entity_store_path=None,
    entity_device="mps",
    entity_window_batch_size=None,
):
    """
    Evaluate one KB recipe.

    PARAMETERS:
    - recipe: Recipe dictionary
    - clean_articles_cache: Optional shared cache keyed by input corpus folder
    - retrieval_options: Optional retrieval metric options
    - retrieval_embedding_cache: Optional shared query embedding cache
    - retrieval_runtime: Optional shared runtime values
    - retrieval_search_function: Optional fake search function for tests
    - entity_metric_config: Optional entity metric config
    - entity_metric_runtime: Optional shared entity metric runtime values
    - entity_extractor_function: Optional fake entity extractor for tests
    - reset_entity_mentions: Whether to clear the entity mentions artifact first
    - entity_sample_size: Number of indexed articles for entity-pair metrics
    - entity_cache_path: Optional entity cache path for tests
    - entity_mentions_path: Optional entity mentions path for tests
    - entity_store_path: Optional SQLite precomputed entity store path
    - entity_device: Device name used for precomputed entity cache keys
    - entity_window_batch_size: Optional GLiNER text-window batch size

    RETURNS:
    - Metrics dictionary
    """
    if retrieval_options is None:
        retrieval_options = make_retrieval_options(
            False,
            DEFAULT_RETRIEVAL_SAMPLE_SIZE,
            DEFAULT_RETRIEVAL_TOP_K,
            DEFAULT_RETRIEVAL_SEARCH_MODE,
        )

    if entity_metric_config is None:
        entity_metric_config = make_entity_metric_config()

    if entity_window_batch_size is not None:
        entity_metric_config = copy_metric_config(entity_metric_config)
        entity_metric_config["entity_window_batch_size"] = entity_window_batch_size

    if entity_metric_runtime is None:
        entity_metric_runtime = {}

    if entity_cache_path is None:
        entity_cache_path = DEFAULT_ENTITY_CACHE_PATH
    if entity_mentions_path is None:
        entity_mentions_path = DEFAULT_ENTITY_MENTIONS_PATH
    if entity_store_path is None:
        entity_store_path = DEFAULT_ENTITY_STORE_PATH

    input_folder = Path(recipe["input_corpus"])
    output_folder = Path(recipe["output_folder"])
    db_path = output_folder / "kb.sqlite"
    manifest_path = output_folder / "manifest.json"

    clean_articles = get_cached_clean_articles(input_folder, clean_articles_cache)
    manifest = load_json_file(manifest_path)

    recipe_report = make_base_recipe_report(
        recipe,
        input_folder,
        output_folder,
        db_path,
        manifest_path,
        entity_cache_path,
        entity_mentions_path,
        entity_store_path,
    )
    recipe_report["thesis_metric_config"] = copy_metric_config(entity_metric_config)

    if not db_path.exists():
        recipe_report["status"] = "missing_database"
        recipe_report["sanity_metrics"] = make_missing_database_sanity_metrics(clean_articles, manifest)
        recipe_report["thesis_metrics"] = make_pending_thesis_metrics()
        recipe_report["diagnostic_metrics"] = make_empty_diagnostic_metrics()
        if retrieval_options.get("enabled", False):
            error = ValueError(f"KB database does not exist yet: {db_path}")
            recipe_report["retrieval_metrics"] = make_error_retrieval_metrics(retrieval_options, error)
        apply_thesis_retrieval_metrics(recipe_report)
        return recipe_report

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row

    try:
        table_names = get_table_names(connection)
        article_columns = get_table_columns(connection, "articles")
        article_rows = fetch_article_rows(connection, table_names, article_columns)
        chunk_rows = fetch_chunk_rows(connection, table_names)

        recipe_report["sanity_metrics"] = make_sanity_metrics(
            connection,
            table_names,
            article_columns,
            article_rows,
            chunk_rows,
            clean_articles,
            manifest,
            db_path,
        )
        recipe_report["thesis_metrics"] = make_thesis_metrics(article_rows, chunk_rows, clean_articles)
        apply_entity_pair_preservation_metric(
            recipe_report,
            article_rows,
            chunk_rows,
            clean_articles,
            entity_metric_config,
            entity_metric_runtime,
            entity_extractor_function,
            entity_sample_size,
            reset_entity_mentions,
            entity_cache_path,
            entity_mentions_path,
            entity_store_path,
            entity_device,
            entity_window_batch_size,
        )
        recipe_report["diagnostic_metrics"] = make_diagnostic_metrics(article_rows, chunk_rows)

        if retrieval_options.get("enabled", False):
            try:
                recipe_report["retrieval_metrics"] = evaluate_retrieval_metrics(
                    connection,
                    recipe,
                    article_rows,
                    clean_articles,
                    retrieval_options,
                    retrieval_embedding_cache,
                    retrieval_runtime,
                    retrieval_search_function,
                )
            except Exception as error:
                recipe_report["retrieval_metrics"] = make_error_retrieval_metrics(retrieval_options, error)

            retrieval_config = recipe_report["retrieval_metrics"].get("config", {})
            recipe_report["sanity_metrics"]["query_latency_ms"] = retrieval_config.get("query_latency_ms")
    finally:
        connection.close()

    apply_thesis_retrieval_metrics(recipe_report)
    return recipe_report


def make_base_recipe_report(
    recipe,
    input_folder,
    output_folder,
    db_path,
    manifest_path,
    entity_cache_path,
    entity_mentions_path,
    entity_store_path,
):
    """
    Create the common report fields for one recipe.

    PARAMETERS:
    - recipe: Recipe dictionary
    - input_folder: Clean article folder
    - output_folder: Recipe output folder
    - db_path: SQLite DB path
    - manifest_path: Manifest JSON path
    - entity_cache_path: Entity cache artifact path
    - entity_mentions_path: Entity mentions artifact path
    - entity_store_path: Entity store artifact path

    RETURNS:
    - Base report dictionary
    """
    return {
        "recipe_name": recipe["name"],
        "status": "evaluated",
        "recipe_config": {
            "embedding_model": recipe.get("embedding_model"),
            "chunking_method": recipe.get("chunking_method"),
            "chunk_size_characters": recipe.get("chunk_size_characters"),
            "chunk_overlap_characters": recipe.get("chunk_overlap_characters"),
        },
        "paths": {
            "input_corpus": str(input_folder),
            "output_folder": str(output_folder),
            "database": str(db_path),
            "manifest": str(manifest_path),
        },
        "manifest_exists": manifest_path.exists(),
        "database_exists": db_path.exists(),
        "pending_metrics": list(PENDING_METRICS),
        "thesis_metric_config": copy_metric_config(make_entity_metric_config()),
        "thesis_metric_errors": {},
        "thesis_metric_details": {},
        "entity_metric_artifacts": make_entity_metric_artifacts(entity_cache_path, entity_mentions_path, entity_store_path),
        "retrieval_metrics": make_not_requested_retrieval_metrics(),
    }


def make_recipe_error_report(
    recipe_name,
    retrieval_options,
    retrieval_metrics_enabled,
    error,
    entity_metric_config,
    entity_cache_path,
    entity_mentions_path,
    entity_store_path,
):
    """
    Create a stable report shape when recipe loading or evaluation fails.

    PARAMETERS:
    - recipe_name: Requested recipe name
    - retrieval_options: Retrieval metric options
    - retrieval_metrics_enabled: Whether retrieval metrics were requested
    - error: Exception raised while loading or evaluating the recipe
    - entity_metric_config: Entity metric configuration dictionary
    - entity_cache_path: Entity cache artifact path
    - entity_mentions_path: Entity mentions artifact path
    - entity_store_path: Entity store artifact path

    RETURNS:
    - Recipe report dictionary
    """
    clean_articles = {
        "valid_count": 0,
        "invalid_count": 0,
    }
    retrieval_metrics = make_not_requested_retrieval_metrics()
    if retrieval_metrics_enabled:
        retrieval_metrics = make_error_retrieval_metrics(retrieval_options, error)

    recipe_report = {
        "recipe_name": recipe_name,
        "status": "error",
        "error": str(error),
        "recipe_config": {},
        "paths": {},
        "manifest_exists": False,
        "database_exists": False,
        "pending_metrics": list(PENDING_METRICS),
        "sanity_metrics": make_missing_database_sanity_metrics(clean_articles, {}),
        "thesis_metrics": make_pending_thesis_metrics(),
        "diagnostic_metrics": make_empty_diagnostic_metrics(),
        "thesis_metric_config": copy_metric_config(entity_metric_config),
        "thesis_metric_errors": {},
        "thesis_metric_details": {},
        "entity_metric_artifacts": make_entity_metric_artifacts(entity_cache_path, entity_mentions_path, entity_store_path),
        "retrieval_metrics": retrieval_metrics,
    }
    apply_thesis_retrieval_metrics(recipe_report)
    return recipe_report


def copy_metric_config(config):
    """
    Copy metric config values so reports do not share mutable lists.
    """
    copied_config = {}
    for key in config:
        value = config[key]
        if isinstance(value, list):
            copied_config[key] = list(value)
        else:
            copied_config[key] = value
    return copied_config


def apply_entity_pair_preservation_metric(
    recipe_report,
    article_rows,
    chunk_rows,
    clean_articles,
    entity_metric_config,
    entity_metric_runtime,
    entity_extractor_function,
    entity_sample_size,
    reset_entity_mentions,
    entity_cache_path,
    entity_mentions_path,
    entity_store_path,
    entity_device,
    entity_window_batch_size,
):
    """
    Calculate and attach the entity-pair preservation metric.

    PARAMETERS:
    - recipe_report: Metrics dictionary for one recipe
    - article_rows: Article rows as dictionaries
    - chunk_rows: Chunk rows as dictionaries
    - clean_articles: Clean article lookup dictionary
    - entity_metric_config: Entity metric configuration dictionary
    - entity_metric_runtime: Shared runtime dictionary
    - entity_extractor_function: Optional fake entity extractor for tests
    - entity_sample_size: Number of indexed articles for entity-pair metrics
    - reset_entity_mentions: Whether to clear the entity mentions artifact first
    - entity_cache_path: Entity cache artifact path
    - entity_mentions_path: Entity mentions artifact path
    - entity_store_path: Entity store artifact path
    - entity_device: Device name used for precomputed entity cache keys
    - entity_window_batch_size: Optional GLiNER text-window batch size

    RETURNS:
    - None
    """
    try:
        result = calculate_entity_pair_preservation_rate(
            article_rows=article_rows,
            chunk_rows=chunk_rows,
            clean_articles=clean_articles,
            recipe_name=recipe_report["recipe_name"],
            config=entity_metric_config,
            cache_path=entity_cache_path,
            mentions_path=entity_mentions_path,
            runtime=entity_metric_runtime,
            entity_extractor_function=entity_extractor_function,
            reset_mentions=reset_entity_mentions,
            entity_sample_size=entity_sample_size,
            entity_store_path=entity_store_path,
            entity_device=entity_device,
            entity_window_batch_size=entity_window_batch_size,
        )
        recipe_report["thesis_metrics"]["entity_pair_preservation_rate"] = result["value"]
        recipe_report["thesis_metric_details"]["entity_pair_preservation"] = result["details"]
        if result.get("error"):
            recipe_report["thesis_metric_errors"]["entity_pair_preservation_rate"] = result["error"]
    except Exception as error:
        recipe_report["thesis_metrics"]["entity_pair_preservation_rate"] = None
        recipe_report["thesis_metric_errors"]["entity_pair_preservation_rate"] = str(error)
        print(f"[WARNING] Entity-pair metric failed: {error}", flush=True)


def apply_thesis_retrieval_metrics(recipe_report):
    """
    Copy retrieval-derived thesis metrics into the main thesis metric block.

    PARAMETERS:
    - recipe_report: Metrics dictionary for one recipe

    RETURNS:
    - None
    """
    retrieval_metrics = recipe_report.get("retrieval_metrics", {})
    thesis_retrieval = retrieval_metrics.get("thesis_retrieval", make_empty_thesis_retrieval_metrics())

    for metric_name in [
        "story_level_top_k_diversity",
        "article_self_retrieval_top_5_rate",
        "hard_negative_separation_margin",
        "retrieval_hubness_rate",
        "recency_aware_retrieval_score",
    ]:
        recipe_report["thesis_metrics"][metric_name] = thesis_retrieval.get(metric_name)


def write_tables_for_report(report, final_output_path, markdown_table_path, csv_table_path):
    """
    Write optional comparison tables for an evaluation report.

    PARAMETERS:
    - report: Evaluation report dictionary
    - final_output_path: JSON output path
    - markdown_table_path: Optional Markdown path
    - csv_table_path: Optional CSV path

    RETURNS:
    - Dictionary with output paths
    """
    default_markdown_path, default_csv_path = make_default_table_paths(final_output_path)

    if markdown_table_path is None:
        markdown_table_path = default_markdown_path

    if csv_table_path is None:
        csv_table_path = default_csv_path

    table_result = write_comparison_tables(report, markdown_table_path, csv_table_path)
    print(f"[INFO] Markdown comparison table written: {table_result['markdown_table_path']}")
    print(f"[INFO] CSV comparison table written: {table_result['csv_table_path']}")
    return table_result


def print_recipe_summary(recipe_report):
    """
    Print a short human-readable summary for one recipe.

    PARAMETERS:
    - recipe_report: Metrics dictionary for one recipe

    RETURNS:
    - None
    """
    if recipe_report["status"] != "evaluated":
        print(f"[WARNING] {recipe_report['recipe_name']}: {recipe_report['status']}")
        return

    sanity = recipe_report["sanity_metrics"]
    thesis = recipe_report["thesis_metrics"]

    print(
        "[INFO] "
        + recipe_report["recipe_name"]
        + ": articles="
        + str(sanity["article_count"])
        + "/"
        + str(sanity["expected_article_count"])
        + ", chunks="
        + str(sanity["chunk_count"])
        + ", coverage="
        + format_optional_rate(sanity["article_coverage_rate"])
        + ", boundary_break_rate="
        + format_optional_rate(thesis["boundary_break_rate"])
    )
