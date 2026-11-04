"""
Static HTML viewer for grouped report runs.
"""

import html
import json
import re
from pathlib import Path


def html_escape(value):
    """
    Escape a value so it is safe to place inside HTML.
    """
    return html.escape(str(value), quote=True)


def read_json_file(path):
    """
    Read a JSON file and return the parsed dictionary.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Could not parse JSON file: {path}: {error}") from error


def resolve_artifact_path(run_folder, path_text):
    """
    Resolve a report or manifest path from the run manifest.
    """
    if not path_text:
        return None

    artifact_path = Path(path_text)
    if artifact_path.is_absolute():
        return artifact_path

    if artifact_path.exists():
        return artifact_path

    local_path = run_folder / artifact_path.name
    if local_path.exists():
        return local_path

    return artifact_path


def make_dom_id(value):
    """
    Build a safe HTML id from a strategy name.
    """
    safe_value = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value))
    if not safe_value:
        safe_value = "item"
    return "tab-" + safe_value


def render_inline_markdown(text):
    """
    Render the small inline Markdown subset used in generated reports.
    """
    rendered = html_escape(text)

    def replace_link(match):
        label = match.group(1)
        url = match.group(2)
        return (
            "<a href=\""
            + url
            + "\" target=\"_blank\" rel=\"noopener noreferrer\">"
            + label
            + "</a>"
        )

    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, rendered)
    return rendered


def close_open_list(html_parts, current_list_type):
    """
    Close a list if one is open.
    """
    if current_list_type:
        html_parts.append("</" + current_list_type + ">")
    return None


def flush_paragraph(html_parts, paragraph_lines):
    """
    Write the current paragraph into the HTML output.
    """
    if paragraph_lines:
        html_parts.append("<p>" + " ".join(paragraph_lines) + "</p>")
        paragraph_lines.clear()


def render_markdown_to_html(markdown_text):
    """
    Render generated report Markdown into simple HTML.
    """
    html_parts = []
    paragraph_lines = []
    current_list_type = None
    in_code_block = False

    for raw_line in str(markdown_text).splitlines():
        line = raw_line.rstrip()
        stripped_line = line.strip()

        if stripped_line.startswith("```"):
            flush_paragraph(html_parts, paragraph_lines)
            current_list_type = close_open_list(html_parts, current_list_type)
            if in_code_block:
                html_parts.append("</code></pre>")
                in_code_block = False
            else:
                html_parts.append("<pre><code>")
                in_code_block = True
            continue

        if in_code_block:
            html_parts.append(html_escape(line))
            continue

        if not stripped_line:
            flush_paragraph(html_parts, paragraph_lines)
            current_list_type = close_open_list(html_parts, current_list_type)
            continue

        if stripped_line == "---":
            flush_paragraph(html_parts, paragraph_lines)
            current_list_type = close_open_list(html_parts, current_list_type)
            html_parts.append("<hr>")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped_line)
        if heading_match:
            flush_paragraph(html_parts, paragraph_lines)
            current_list_type = close_open_list(html_parts, current_list_type)
            level = len(heading_match.group(1))
            heading_text = render_inline_markdown(heading_match.group(2))
            html_parts.append(f"<h{level}>{heading_text}</h{level}>")
            continue

        unordered_match = re.match(r"^\s*[-*]\s+(.*)$", line)
        ordered_match = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if unordered_match or ordered_match:
            flush_paragraph(html_parts, paragraph_lines)
            list_type = "ul"
            list_text = ""
            if ordered_match:
                list_type = "ol"
                list_text = ordered_match.group(1)
            else:
                list_text = unordered_match.group(1)

            if current_list_type != list_type:
                current_list_type = close_open_list(html_parts, current_list_type)
                html_parts.append("<" + list_type + ">")
                current_list_type = list_type

            html_parts.append("<li>" + render_inline_markdown(list_text) + "</li>")
            continue

        current_list_type = close_open_list(html_parts, current_list_type)
        paragraph_lines.append(render_inline_markdown(stripped_line))

    flush_paragraph(html_parts, paragraph_lines)
    current_list_type = close_open_list(html_parts, current_list_type)
    if in_code_block:
        html_parts.append("</code></pre>")

    return "\n".join(html_parts)


def format_value_for_table(value):
    """
    Format a manifest value for a traceability table.
    """
    if isinstance(value, (dict, list)):
        return "<pre>" + html_escape(json.dumps(value, indent=2, ensure_ascii=False)) + "</pre>"

    return html_escape(value)


def render_key_value_table(title, data):
    """
    Render a dictionary as a small traceability table.
    """
    html_parts = []
    html_parts.append("<h3>" + html_escape(title) + "</h3>")

    if not data:
        html_parts.append("<p class=\"muted\">No data recorded.</p>")
        return "\n".join(html_parts)

    html_parts.append("<table class=\"trace-table\">")
    html_parts.append("<tbody>")

    for key in sorted(data.keys()):
        html_parts.append("<tr>")
        html_parts.append("<th>" + html_escape(key) + "</th>")
        html_parts.append("<td>" + format_value_for_table(data.get(key)) + "</td>")
        html_parts.append("</tr>")

    html_parts.append("</tbody>")
    html_parts.append("</table>")
    return "\n".join(html_parts)


def render_chunk_list(chunk_ids):
    """
    Render retrieved chunk IDs.
    """
    html_parts = []
    html_parts.append("<h3>Retrieved Chunks</h3>")

    if not chunk_ids:
        html_parts.append("<p class=\"muted\">No retrieved chunks recorded.</p>")
        return "\n".join(html_parts)

    html_parts.append("<ul class=\"compact-list\">")
    for chunk_id in chunk_ids:
        html_parts.append("<li><code>" + html_escape(chunk_id) + "</code></li>")
    html_parts.append("</ul>")
    return "\n".join(html_parts)


def render_tool_call_table(tool_calls):
    """
    Render model tool calls and arguments from the manifest.
    """
    html_parts = []
    html_parts.append("<h3>Tool Calls</h3>")

    if not tool_calls:
        html_parts.append("<p class=\"muted\">No tool calls recorded.</p>")
        return "\n".join(html_parts)

    html_parts.append("<table class=\"trace-table tool-table\">")
    html_parts.append(
        "<thead><tr>"
        "<th>Phase</th><th>Iteration</th><th>Tool</th><th>Arguments</th>"
        "<th>Status</th><th>Results</th><th>Retrieved chunks</th><th>Error</th>"
        "</tr></thead>"
    )
    html_parts.append("<tbody>")

    for tool_call in tool_calls:
        arguments = json.dumps(tool_call.get("arguments", {}), indent=2, ensure_ascii=False)
        retrieved_chunks = json.dumps(tool_call.get("retrieved_chunk_ids", []), ensure_ascii=False)
        html_parts.append("<tr>")
        html_parts.append("<td>" + html_escape(tool_call.get("phase", "")) + "</td>")
        html_parts.append("<td>" + html_escape(tool_call.get("iteration", "")) + "</td>")
        html_parts.append("<td>" + html_escape(tool_call.get("tool_name", "")) + "</td>")
        html_parts.append("<td><pre>" + html_escape(arguments) + "</pre></td>")
        html_parts.append("<td>" + html_escape(tool_call.get("status", "")) + "</td>")
        html_parts.append("<td>" + html_escape(tool_call.get("result_count", "")) + "</td>")
        html_parts.append("<td><pre>" + html_escape(retrieved_chunks) + "</pre></td>")
        html_parts.append("<td>" + html_escape(tool_call.get("error", "")) + "</td>")
        html_parts.append("</tr>")

    html_parts.append("</tbody>")
    html_parts.append("</table>")
    return "\n".join(html_parts)


def render_tool_summary(manifest):
    """
    Render compact tool availability and usage information.
    """
    return render_key_value_table("Tool Summary", {
        "available_tools": manifest.get("available_tools", []),
        "required_tool_policy": manifest.get("required_tool_policy", {}),
        "tool_call_counts": manifest.get("tool_call_counts", {}),
        "kb_search_call_count": manifest.get("kb_search_call_count", 0),
        "read_article_call_count": manifest.get("read_article_call_count", 0),
        "kb_requirement_satisfied": manifest.get("kb_requirement_satisfied", False),
    })


def render_full_json_details(title, data):
    """
    Render an expandable raw JSON block.
    """
    json_text = json.dumps(data, indent=2, ensure_ascii=False)
    return (
        "<details class=\"json-details\">"
        "<summary>"
        + html_escape(title)
        + "</summary>"
        "<pre>"
        + html_escape(json_text)
        + "</pre>"
        "</details>"
    )


def load_strategy_view_data(run_folder, strategy_result):
    """
    Load report and manifest data for one strategy tab.
    """
    report_text = ""
    strategy_manifest = {}
    artifact_error = ""

    report_path = resolve_artifact_path(run_folder, strategy_result.get("report_path", ""))
    manifest_path = resolve_artifact_path(run_folder, strategy_result.get("manifest_path", ""))

    if strategy_result.get("status") == "ok":
        if report_path is not None and report_path.exists():
            report_text = report_path.read_text(encoding="utf-8")
        else:
            artifact_error = artifact_error + "Report markdown file was not found. "

        if manifest_path is not None and manifest_path.exists():
            strategy_manifest = read_json_file(manifest_path)
        else:
            artifact_error = artifact_error + "Strategy manifest file was not found. "

    return {
        "strategy": strategy_result.get("strategy", ""),
        "status": strategy_result.get("status", ""),
        "error": strategy_result.get("error", ""),
        "artifact_error": artifact_error.strip(),
        "report_path": report_path,
        "manifest_path": manifest_path,
        "report_text": report_text,
        "manifest": strategy_manifest,
    }


def load_batch_view_data(run_folder):
    """
    Load the run manifest and each strategy artifact for the viewer.
    """
    run_manifest_path = run_folder / "run_manifest.json"
    if not run_manifest_path.exists():
        raise ValueError(f"Missing run_manifest.json in run folder: {run_folder}")

    run_manifest = read_json_file(run_manifest_path)
    evaluation = {}
    evaluation_path = run_folder / "evaluation.json"
    if evaluation_path.exists():
        evaluation = read_json_file(evaluation_path)

    strategy_views = []

    for strategy_result in run_manifest.get("strategies", []):
        strategy_views.append(load_strategy_view_data(run_folder, strategy_result))

    return {
        "run_manifest": run_manifest,
        "evaluation": evaluation,
        "strategy_views": strategy_views,
    }


def render_summary_card(label, value):
    """
    Render one top summary card.
    """
    return (
        "<div class=\"summary-card\"><div class=\"label\">"
        + html_escape(label)
        + "</div><div class=\"summary-value\">"
        + html_escape(value)
        + "</div></div>"
    )


def render_strategy_panel(strategy_view, is_active):
    """
    Render one strategy tab panel.
    """
    strategy = strategy_view["strategy"]
    status = strategy_view["status"]
    manifest = strategy_view["manifest"]
    tab_class = "tab-panel"
    if is_active:
        tab_class = tab_class + " active"

    html_parts = []
    html_parts.append("<section id=\"" + html_escape(make_dom_id(strategy)) + "\" class=\"" + tab_class + "\">")
    html_parts.append("<div class=\"strategy-header\">")
    html_parts.append("<div><h2>" + html_escape(strategy) + "</h2>")
    html_parts.append("<p class=\"muted\">Status: " + html_escape(status) + "</p></div>")
    html_parts.append("</div>")

    if strategy_view.get("error"):
        html_parts.append("<div class=\"error-box\">" + html_escape(strategy_view["error"]) + "</div>")

    if strategy_view.get("artifact_error"):
        html_parts.append("<div class=\"error-box\">" + html_escape(strategy_view["artifact_error"]) + "</div>")

    html_parts.append("<div class=\"report-grid\">")
    html_parts.append("<article class=\"report-body\">")
    if strategy_view["report_text"]:
        html_parts.append(render_markdown_to_html(strategy_view["report_text"]))
    else:
        html_parts.append("<p class=\"muted\">No report markdown available for this strategy.</p>")
    html_parts.append("</article>")

    html_parts.append("<aside class=\"trace-panel\">")
    html_parts.append("<h2>Traceability</h2>")
    html_parts.append(render_key_value_table("Artifact Paths", {
        "report_path": strategy_view.get("report_path") or "",
        "manifest_path": strategy_view.get("manifest_path") or "",
    }))

    if manifest:
        html_parts.append(render_key_value_table("Core Metrics", manifest.get("metrics", {})))
        html_parts.append(render_key_value_table("Model Usage", manifest.get("model_metrics", {})))
        html_parts.append(render_key_value_table("Candidate Selection", manifest.get("candidate_selection", {})))
        html_parts.append(render_tool_summary(manifest))
        html_parts.append(render_chunk_list(manifest.get("retrieved_chunk_ids", [])))
        html_parts.append(render_tool_call_table(manifest.get("tool_call_log", [])))
        html_parts.append(render_full_json_details("Full Manifest JSON", manifest))
    else:
        html_parts.append("<p class=\"muted\">No strategy manifest available.</p>")

    html_parts.append("</aside>")
    html_parts.append("</div>")
    html_parts.append("</section>")

    return "\n".join(html_parts)


def render_evaluation_strategy_table(rows):
    """
    Render the per-strategy evaluation scorecard.
    """
    if not rows:
        return "<p class=\"muted\">No strategy evaluation rows recorded.</p>"

    columns = [
        "strategy",
        "status",
        "citation_count",
        "cited_daily_window_article_count",
        "cited_past_article_count",
        "cited_future_article_count",
        "cited_temporal_validity_rate",
        "kb_search_call_count",
        "kb_requirement_satisfied",
    ]
    html_parts = []
    html_parts.append("<table class=\"trace-table\">")
    html_parts.append("<thead><tr>")
    for column in columns:
        html_parts.append("<th>" + html_escape(column) + "</th>")
    html_parts.append("</tr></thead>")
    html_parts.append("<tbody>")
    for row in rows:
        html_parts.append("<tr>")
        for column in columns:
            html_parts.append("<td>" + html_escape(row.get(column, "")) + "</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody>")
    html_parts.append("</table>")
    return "\n".join(html_parts)


def render_evaluation_section(evaluation):
    """
    Render run-level evaluation details when available.
    """
    if not evaluation:
        return ""

    html_parts = []
    html_parts.append("<section class=\"evaluation-panel\">")
    html_parts.append("<h2>Evaluation Summary</h2>")
    html_parts.append(render_key_value_table("Run Diagnostics", evaluation.get("summary", {})))
    html_parts.append("<h3>Strategy Evaluation</h3>")
    html_parts.append(render_evaluation_strategy_table(evaluation.get("strategies", [])))
    html_parts.append(render_full_json_details("Full Evaluation JSON", evaluation))
    html_parts.append("</section>")
    return "\n".join(html_parts)


def build_report_batch_viewer_html(view_data):
    """
    Build the complete static HTML viewer.
    """
    run_manifest = view_data["run_manifest"]
    evaluation = view_data.get("evaluation", {})
    strategy_views = view_data["strategy_views"]
    title = "Report Batch Viewer - " + str(run_manifest.get("run_name", ""))

    html_parts = []
    html_parts.append("<!doctype html>")
    html_parts.append("<html lang=\"en\">")
    html_parts.append("<head>")
    html_parts.append("<meta charset=\"utf-8\">")
    html_parts.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    html_parts.append("<title>" + html_escape(title) + "</title>")
    html_parts.append("<style>")
    html_parts.append(
        ":root { color-scheme: light; --bg: #f6f7f9; --panel: #ffffff; "
        "--line: #d8dee8; --text: #1f2937; --muted: #64748b; --accent: #2563eb; "
        "--warn: #b45309; --bad: #b91c1c; --good: #15803d; }"
    )
    html_parts.append(
        "* { box-sizing: border-box; } body { margin: 0; background: var(--bg); "
        "color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; "
        "font-size: 15px; line-height: 1.55; }"
    )
    html_parts.append(
        "header { padding: 28px 32px 20px; background: #eef2f7; border-bottom: 1px solid var(--line); } "
        "main { padding: 22px 32px 36px; } h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: 0; } "
        "h2 { margin: 0 0 12px; font-size: 21px; letter-spacing: 0; } "
        "h3 { margin: 22px 0 8px; font-size: 15px; letter-spacing: 0; }"
    )
    html_parts.append(
        ".muted { color: var(--muted); } .summary-grid { display: grid; "
        "grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 18px; } "
        ".summary-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; } "
        ".label { color: var(--muted); font-size: 12px; } .summary-value { font-weight: 700; margin-top: 4px; word-break: break-word; }"
    )
    html_parts.append(
        ".tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; } "
        ".tab-button { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); "
        "color: var(--text); padding: 8px 10px; cursor: pointer; font: inherit; } "
        ".tab-button.active { border-color: var(--accent); color: var(--accent); background: #eff6ff; } "
        ".tab-panel { display: none; } .tab-panel.active { display: block; }"
    )
    html_parts.append(
        ".strategy-header { display: flex; justify-content: space-between; gap: 16px; align-items: start; margin-bottom: 14px; } "
        ".report-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 440px); gap: 18px; align-items: start; } "
        ".report-body, .trace-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; } "
        ".report-body { max-width: 920px; } .report-body h1 { font-size: 27px; margin: 0 0 16px; } "
        ".report-body h2 { margin-top: 28px; } .report-body h3 { margin-top: 22px; font-size: 17px; } "
        ".report-body a { color: var(--accent); } .report-body li { margin: 5px 0; }"
    )
    html_parts.append(
        ".trace-table { width: 100%; border-collapse: collapse; border: 1px solid var(--line); margin-bottom: 12px; } "
        ".trace-table th, .trace-table td { border-bottom: 1px solid var(--line); padding: 7px 8px; text-align: left; vertical-align: top; } "
        ".trace-table th { width: 38%; background: #f8fafc; color: var(--muted); font-weight: 600; } "
        "pre { white-space: pre-wrap; word-break: break-word; margin: 0; font-size: 12px; } "
        "code { font-size: 12px; } .compact-list { margin: 0 0 12px 18px; padding: 0; } "
        ".error-box { border: 1px solid #fecaca; background: #fff1f2; color: var(--bad); border-radius: 8px; padding: 12px; margin-bottom: 14px; } "
        ".json-details { margin-top: 16px; } .json-details summary { cursor: pointer; color: var(--accent); margin-bottom: 8px; } "
        ".evaluation-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin-bottom: 18px; } "
        "@media (max-width: 980px) { main, header { padding-left: 16px; padding-right: 16px; } .report-grid { grid-template-columns: 1fr; } }"
    )
    html_parts.append("</style>")
    html_parts.append("</head>")
    html_parts.append("<body>")
    html_parts.append("<header>")
    html_parts.append("<h1>Report Batch Viewer</h1>")
    html_parts.append(
        "<div class=\"muted\">"
        + html_escape(run_manifest.get("recipe_name", ""))
        + " · "
        + html_escape(run_manifest.get("run_name", ""))
        + "</div>"
    )
    html_parts.append("<section class=\"summary-grid\">")
    html_parts.append(render_summary_card("Status", run_manifest.get("status", "")))
    html_parts.append(render_summary_card("Report datetime", run_manifest.get("report_datetime", "")))
    html_parts.append(render_summary_card("Knowledge base", run_manifest.get("knowledge_base_recipe", "")))
    html_parts.append(render_summary_card("Started", run_manifest.get("started_at", "")))
    html_parts.append(render_summary_card("Finished", run_manifest.get("finished_at", "")))
    html_parts.append("</section>")
    html_parts.append("</header>")
    html_parts.append("<main>")
    html_parts.append(render_evaluation_section(evaluation))
    html_parts.append("<nav class=\"tabs\" aria-label=\"Report strategy tabs\">")

    for index, strategy_view in enumerate(strategy_views):
        active_class = ""
        if index == 0:
            active_class = " active"
        strategy = strategy_view["strategy"]
        html_parts.append(
            "<button class=\"tab-button"
            + active_class
            + "\" type=\"button\" onclick=\"showTab('"
            + html_escape(make_dom_id(strategy))
            + "', this)\">"
            + html_escape(strategy)
            + "</button>"
        )

    html_parts.append("</nav>")

    for index, strategy_view in enumerate(strategy_views):
        html_parts.append(render_strategy_panel(strategy_view, index == 0))

    html_parts.append(render_full_json_details("Full Run Manifest JSON", run_manifest))
    html_parts.append("</main>")
    html_parts.append("<script>")
    html_parts.append(
        "function showTab(tabId, button) {"
        "document.querySelectorAll('.tab-panel').forEach(function(panel) { panel.classList.remove('active'); });"
        "document.querySelectorAll('.tab-button').forEach(function(tabButton) { tabButton.classList.remove('active'); });"
        "document.getElementById(tabId).classList.add('active');"
        "button.classList.add('active');"
        "}"
    )
    html_parts.append("</script>")
    html_parts.append("</body>")
    html_parts.append("</html>")
    return "\n".join(html_parts)


def write_report_batch_viewer(run_folder):
    """
    Write index.html for a grouped report run folder.
    """
    run_folder_path = Path(run_folder)
    view_data = load_batch_view_data(run_folder_path)
    html_text = build_report_batch_viewer_html(view_data)
    viewer_path = run_folder_path / "index.html"
    viewer_path.write_text(html_text + "\n", encoding="utf-8")
    return viewer_path
