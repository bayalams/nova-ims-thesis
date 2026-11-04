"""
Evaluate generated report run folders with unsupervised diagnostics.
"""

import csv
import json
from pathlib import Path

from reporting.html_viewer import write_report_batch_viewer


METRIC_FAMILIES = {
    "citation_behavior": [
        "citation_count",
        "distinct_cited_sources",
        "citation_reference_validity_rate",
        "citation_out_of_range_count",
        "citation_nonstandard_count",
    ],
    "daily_evidence_use": [
        "daily_article_count",
        "cited_daily_article_count",
        "cited_daily_article_rate",
    ],
    "citation_density": [
        "report_line_count",
        "cited_line_count",
        "cited_line_ratio",
    ],
    "rag_context_use": [
        "retrieved_chunk_count",
        "rag_source_article_count",
        "cited_rag_article_count",
        "cited_rag_article_rate",
        "kb_search_call_count",
        "successful_kb_search_call_count",
        "read_article_call_count",
        "kb_requirement_satisfied",
    ],
    "report_shape": [
        "report_word_count",
        "section_count",
    ],
    "source_spread": [
        "cited_source_entropy",
        "cited_source_hhi",
        "top_cited_source_share",
    ],
    "operational": [
        "llm_prompt_tokens",
        "llm_completion_tokens",
        "llm_call_count",
        "runtime_seconds",
    ],
    "temporal_validity": [
        "cited_future_article_count",
        "cited_past_article_count",
        "cited_daily_window_article_count",
        "cited_unknown_date_article_count",
        "cited_temporal_validity_rate",
        "source_future_article_count",
        "rag_future_article_count",
    ],
}


EVALUATION_COLUMNS = [
    "strategy",
    "status",
    "error",
    "context_strategy",
    "knowledge_base_recipe",
    "report_path",
    "manifest_path",
]

for family_name in METRIC_FAMILIES:
    for metric_name in METRIC_FAMILIES[family_name]:
        if metric_name not in EVALUATION_COLUMNS:
            EVALUATION_COLUMNS.append(metric_name)


def read_json_file(path):
    """
    Read a JSON file.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_artifact_path(run_folder, path_text):
    """
    Resolve a path from the run manifest.
    """
    if not path_text:
        return None

    path = Path(path_text)
    if path.is_absolute():
        return path

    local_path = Path(run_folder) / path.name
    if local_path.exists():
        return local_path

    return path


def metric_value(manifest, metrics, model_metrics, key):
    """
    Read one metric from manifest metrics or older manifest locations.
    """
    if key in metrics:
        return metrics.get(key)

    if key == "kb_requirement_satisfied":
        return manifest.get("kb_requirement_satisfied", "")
    if key == "kb_search_call_count":
        return manifest.get("kb_search_call_count", "")
    if key == "successful_kb_search_call_count":
        return manifest.get("successful_kb_search_call_count", "")
    if key == "read_article_call_count":
        return manifest.get("read_article_call_count", "")
    if key == "llm_prompt_tokens":
        return model_metrics.get("prompt_tokens", "")
    if key == "llm_completion_tokens":
        return model_metrics.get("completion_tokens", "")
    if key == "llm_call_count":
        return model_metrics.get("llm_calls", "")
    if key == "runtime_seconds":
        return model_metrics.get("runtime_seconds", "")

    return ""


def build_evaluation_row(run_folder, strategy_result):
    """
    Build one flat evaluation row from a strategy result and manifest.
    """
    row = {}
    for column in EVALUATION_COLUMNS:
        row[column] = ""

    row["strategy"] = strategy_result.get("strategy", "")
    row["status"] = strategy_result.get("status", "")
    row["error"] = strategy_result.get("error", "")
    row["report_path"] = strategy_result.get("report_path", "")
    row["manifest_path"] = strategy_result.get("manifest_path", "")

    manifest_path = resolve_artifact_path(run_folder, strategy_result.get("manifest_path", ""))
    if manifest_path is None or not manifest_path.exists():
        return row

    manifest = read_json_file(manifest_path)
    metrics = manifest.get("metrics", {}) or {}
    model_metrics = manifest.get("model_metrics", {}) or {}

    row["context_strategy"] = manifest.get("context_strategy", "")
    row["knowledge_base_recipe"] = manifest.get("knowledge_base_recipe", "")

    for family_name in METRIC_FAMILIES:
        for metric_name in METRIC_FAMILIES[family_name]:
            row[metric_name] = metric_value(manifest, metrics, model_metrics, metric_name)

    return row


def value_as_int(value):
    """
    Convert a metric value to int for summaries.
    """
    try:
        return int(float(value))
    except Exception:
        return 0


def value_is_false(value):
    """
    Return True for explicit false-like values.
    """
    if value is False:
        return True

    text = str(value).strip().lower()
    return text in ["false", "0", "no"]


def build_evaluation_summary(rows):
    """
    Summarize the run-level diagnostic rows.
    """
    error_count = 0
    future_citation_count = 0
    kb_requirement_failure_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_runtime_seconds = 0.0

    for row in rows:
        if row.get("status") != "ok":
            error_count = error_count + 1
        future_citation_count = future_citation_count + value_as_int(
            row.get("cited_future_article_count", "")
        )
        if row.get("status") == "ok" and value_is_false(row.get("kb_requirement_satisfied", "")):
            kb_requirement_failure_count = kb_requirement_failure_count + 1
        total_prompt_tokens = total_prompt_tokens + value_as_int(row.get("llm_prompt_tokens", ""))
        total_completion_tokens = total_completion_tokens + value_as_int(
            row.get("llm_completion_tokens", "")
        )
        try:
            total_runtime_seconds = total_runtime_seconds + float(row.get("runtime_seconds", 0) or 0)
        except Exception:
            pass

    return {
        "strategy_count": len(rows),
        "error_count": error_count,
        "future_citation_count": future_citation_count,
        "kb_requirement_failure_count": kb_requirement_failure_count,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_runtime_seconds": round(total_runtime_seconds, 4),
    }


def write_evaluation_csv(csv_path, rows):
    """
    Write flat evaluation rows.
    """
    with Path(csv_path).open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EVALUATION_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_report_run_evaluation(run_folder):
    """
    Write evaluation.csv and evaluation.json for one report run folder.
    """
    run_folder = Path(run_folder)
    run_manifest_path = run_folder / "run_manifest.json"
    if not run_manifest_path.exists():
        raise ValueError(f"Missing run_manifest.json in run folder: {run_folder}")

    run_manifest = read_json_file(run_manifest_path)
    rows = []
    for strategy_result in run_manifest.get("strategies", []):
        rows.append(build_evaluation_row(run_folder, strategy_result))

    evaluation = {
        "run_name": run_manifest.get("run_name", ""),
        "recipe_name": run_manifest.get("recipe_name", ""),
        "report_datetime": run_manifest.get("report_datetime", ""),
        "knowledge_base_recipe": run_manifest.get("knowledge_base_recipe", ""),
        "summary": build_evaluation_summary(rows),
        "metric_families": METRIC_FAMILIES,
        "strategies": rows,
    }

    csv_path = run_folder / "evaluation.csv"
    json_path = run_folder / "evaluation.json"
    write_evaluation_csv(csv_path, rows)
    json_path.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")

    return {
        "csv_path": csv_path,
        "json_path": json_path,
        "evaluation": evaluation,
    }


def evaluate_report_run_folder(run_folder):
    """
    Recompute evaluation artifacts and refresh the static viewer.
    """
    result = write_report_run_evaluation(run_folder)
    viewer_path = write_report_batch_viewer(run_folder)
    result["viewer_path"] = viewer_path
    return result

