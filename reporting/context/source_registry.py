"""
Source numbering and citation helpers for reports.
"""

import os
import re

from reporting.context.daily_articles import get_article_id


SOURCE_CITATION_RE = re.compile(r"\[Sources?\s+([^\]]+)\]", flags=re.IGNORECASE)


def make_source_registry():
    """
    Create an empty source registry.
    """
    return {
        "source_articles": [],
        "article_id_to_number": {},
        "daily_article_ids": [],
        "rag_source_article_ids": [],
    }


def register_daily_articles(registry, articles):
    """
    Register daily input articles as numbered sources.
    """
    for article in articles:
        article_id = get_article_id(article)
        source_number = len(registry["source_articles"]) + 1
        registry["article_id_to_number"][article_id] = source_number
        registry["daily_article_ids"].append(article_id)
        registry["source_articles"].append({
            "source_number": source_number,
            "article_id": article_id,
            "article": article,
            "source_type": "daily",
        })


def register_rag_source(registry, article_id, title, source, date, url, text):
    """
    Register one retrieved KB article as a citeable source.
    """
    if not article_id:
        return None

    if article_id in registry["article_id_to_number"]:
        source_number = registry["article_id_to_number"][article_id]
        return {
            "source_number": source_number,
            "article_id": article_id,
        }

    article = {
        "id": article_id,
        "text": text or "",
        "metadata": {
            "title": title or "Untitled",
            "source": source or "Unknown",
            "date": date or "Unknown",
            "link": url or "",
        },
    }
    source_number = len(registry["source_articles"]) + 1
    registry["article_id_to_number"][article_id] = source_number
    registry["rag_source_article_ids"].append(article_id)
    registry["source_articles"].append({
        "source_number": source_number,
        "article_id": article_id,
        "article": article,
        "source_type": "knowledge_base",
    })
    return {
        "source_number": source_number,
        "article_id": article_id,
    }


def extract_cited_source_numbers(report_text):
    """
    Extract sorted unique source numbers from report text.
    """
    numbers = []
    for match in SOURCE_CITATION_RE.finditer(report_text or ""):
        payload = match.group(1)
        for raw_number in re.findall(r"\d+", payload):
            numbers.append(int(raw_number))

    return sorted(set(numbers))


def strip_model_sources_section(report_text):
    """
    Remove a model-generated trailing sources section.
    """
    text = report_text or ""
    lines = text.splitlines()
    level_two_headings = []

    for index, line in enumerate(lines):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            heading = {
                "line_index": index,
                "title": match.group(1).strip().lower(),
            }
            level_two_headings.append(heading)

    generated_titles = ["sources", "source pool", "references"]
    if not level_two_headings:
        return text.rstrip()

    last_heading = level_two_headings[-1]
    if last_heading["title"] not in generated_titles:
        return text.rstrip()

    first_trailing_heading = last_heading
    heading_index = len(level_two_headings) - 2
    while heading_index >= 0:
        heading = level_two_headings[heading_index]
        if heading["title"] not in generated_titles:
            break
        first_trailing_heading = heading
        heading_index = heading_index - 1

    strip_start_index = first_trailing_heading["line_index"]
    previous_index = strip_start_index - 1
    while previous_index >= 0 and not lines[previous_index].strip():
        previous_index = previous_index - 1

    if previous_index >= 0 and re.match(r"^\s*---+\s*$", lines[previous_index]):
        strip_start_index = previous_index

    kept_lines = lines[:strip_start_index]
    return "\n".join(kept_lines).rstrip()


def format_source_line(source_item):
    """
    Format one source-pool line.
    """
    article = source_item["article"]
    metadata = article.get("metadata", {}) or {}
    title = metadata.get("title", "Untitled") or "Untitled"
    source = metadata.get("source", "Unknown") or "Unknown"
    date = metadata.get("date", article.get("published_at", "Unknown")) or "Unknown"
    url = metadata.get("link", metadata.get("url", "")) or ""
    source_number = source_item["source_number"]

    if url:
        return f"{source_number}. **{title}** - {source}, {date} - [link]({url})"

    return f"{source_number}. **{title}** - {source}, {date}"


def build_sources_section(registry, cited_source_numbers):
    """
    Build a source section with cited sources and the full source pool.
    """
    cited_lookup = set(cited_source_numbers or [])
    source_articles = registry["source_articles"]
    lines = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Sources Cited in Report")
    lines.append("")

    cited_items = []
    for item in source_articles:
        if item["source_number"] in cited_lookup:
            cited_items.append(item)

    if cited_items:
        for item in cited_items:
            lines.append(format_source_line(item))
    else:
        lines.append("No numbered sources were cited in the report body.")

    lines.append("")
    lines.append("## Source Pool")
    lines.append("")
    pool_items = []

    for item in source_articles:
        if item["source_number"] in cited_lookup:
            pool_items.append((0, item["source_number"], item))
        else:
            pool_items.append((1, item["source_number"], item))

    pool_items.sort(key=lambda item: (item[0], item[1]))

    for _, _, item in pool_items:
        lines.append(format_source_line(item))

    lines.append("")
    return "\n".join(lines)


def finalize_report_text(report_text, registry):
    """
    Strip model sources, extract citations, and append generated sources.
    """
    cleaned = strip_model_sources_section(report_text)
    cited_numbers = extract_cited_source_numbers(cleaned)
    return cleaned + build_sources_section(registry, cited_numbers)


def parse_source_number_from_line(line):
    """
    Read the leading source number from one markdown source line.
    """
    match = re.match(r"^\s*(\d+)\.\s+", line)
    if not match:
        return None

    return int(match.group(1))


def build_sorted_source_pool_text(source_pool_text):
    """
    Sort source-pool lines by their original source number.
    """
    lines = source_pool_text.splitlines()
    numbered_items = []

    for line in lines:
        source_number = parse_source_number_from_line(line)
        if source_number is None:
            continue
        numbered_items.append((source_number, line))

    if not numbered_items:
        return None

    numbered_items.sort(key=lambda item: item[0])
    sorted_lines = []

    for _, line in numbered_items:
        sorted_lines.append(line)

    return "\n".join(sorted_lines)


def build_sorted_report_copy_text(report_text):
    """
    Return a copy of the report with only the Source Pool reordered.
    """
    if "## Source Pool" not in report_text:
        return None

    before_pool, after_pool = report_text.split("## Source Pool", 1)
    source_pool_text = after_pool.lstrip("\n")
    sorted_pool_text = build_sorted_source_pool_text(source_pool_text)

    if sorted_pool_text is None:
        return None

    return before_pool + "## Source Pool\n\n" + sorted_pool_text + "\n"


def should_sort_report_markdown_file(filename):
    """
    Decide whether a file is a report markdown file that should get a sorted copy.
    """
    if not filename.endswith(".md"):
        return False

    if filename.endswith("-sorted.md"):
        return False

    if filename.endswith("_manifest.md"):
        return False

    return True


def sort_report_batch_markdown(run_folder):
    """
    Create -sorted markdown copies for one report batch folder.
    """
    if not os.path.isdir(run_folder):
        raise ValueError(f"Report run folder does not exist: {run_folder}")

    print(f"[INFO] Sorting report source pools in: {run_folder}")
    filenames = sorted(os.listdir(run_folder))
    created_count = 0
    skipped_count = 0

    for filename in filenames:
        if not should_sort_report_markdown_file(filename):
            continue

        input_path = os.path.join(run_folder, filename)
        output_path = os.path.join(
            run_folder,
            filename[:-3] + "-sorted.md",
        )

        with open(input_path, "r", encoding="utf-8") as handle:
            report_text = handle.read()

        sorted_text = build_sorted_report_copy_text(report_text)
        if sorted_text is None:
            print(f"[WARNING] Skipping report without sortable Source Pool: {filename}")
            skipped_count = skipped_count + 1
            continue

        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(sorted_text)

        print(f"[INFO] Created sorted report: {os.path.basename(output_path)}")
        created_count = created_count + 1

    print(
        f"[INFO] Sorted report summary: created={created_count}, skipped={skipped_count}"
    )
    return {
        "created_count": created_count,
        "skipped_count": skipped_count,
    }
