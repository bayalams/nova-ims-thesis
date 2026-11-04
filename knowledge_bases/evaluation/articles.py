"""
Clean article loading helpers for KB evaluation.
"""

from pathlib import Path

from knowledge_bases.evaluation.utils import load_json_file


def get_cached_clean_articles(input_folder, clean_articles_cache):
    """
    Load clean article metadata, reusing it across recipes when possible.

    PARAMETERS:
    - input_folder: Clean article folder
    - clean_articles_cache: Optional shared cache

    RETURNS:
    - Clean article lookup dictionary
    """
    if clean_articles_cache is None:
        return load_clean_articles_for_evaluation(input_folder)

    cache_key = str(Path(input_folder).resolve())
    if cache_key not in clean_articles_cache:
        clean_articles_cache[cache_key] = load_clean_articles_for_evaluation(input_folder)

    return clean_articles_cache[cache_key]


def load_clean_articles_for_evaluation(input_folder):
    """
    Load valid cleaned articles without printing build-time logs.

    PARAMETERS:
    - input_folder: Folder containing cleaned article JSON files

    RETURNS:
    - Dictionary with article count and lookup tables
    """
    input_folder = Path(input_folder)
    article_paths = sorted(input_folder.glob("*.json"))

    articles_by_id = {}
    articles_by_path = {}
    valid_count = 0
    invalid_count = 0

    for article_path in article_paths:
        try:
            article = load_json_file(article_path)
            metadata = article.get("metadata", {}) or {}

            if not article.get("is_valid_article", True):
                invalid_count = invalid_count + 1
                continue

            text = str(article.get("text", ""))
            if not text.strip():
                invalid_count = invalid_count + 1
                continue

            article_id = article.get("id")
            if article_id is None or str(article_id).strip() == "":
                article_id = article_path.stem
            article_id = str(article_id)

            article_record = {
                "article_id": article_id,
                "path": str(article_path),
                "resolved_path": str(article_path.resolve()),
                "title": str(article.get("title", metadata.get("title", ""))),
                "summary": str(article.get("summary", metadata.get("summary", ""))),
                "text": text,
            }
            articles_by_id[article_id] = article_record
            articles_by_path[str(article_path)] = article_record
            articles_by_path[str(article_path.resolve())] = article_record
            valid_count = valid_count + 1
        except Exception:
            invalid_count = invalid_count + 1

    return {
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "articles_by_id": articles_by_id,
        "articles_by_path": articles_by_path,
    }


def find_source_text(article_row, clean_articles):
    """
    Find the original cleaned article text for one DB article row.

    PARAMETERS:
    - article_row: Article row dictionary
    - clean_articles: Clean article lookup dictionary

    RETURNS:
    - Article text string, or None
    """
    input_file_path = article_row.get("input_file_path")
    if input_file_path:
        article_record = clean_articles["articles_by_path"].get(str(input_file_path))
        if article_record is not None:
            return article_record["text"]

        try:
            resolved_path = str(Path(input_file_path).resolve())
            article_record = clean_articles["articles_by_path"].get(resolved_path)
            if article_record is not None:
                return article_record["text"]
        except Exception:
            pass

    article_id = article_row.get("article_id")
    if article_id:
        article_record = clean_articles["articles_by_id"].get(str(article_id))
        if article_record is not None:
            return article_record["text"]

    return None


def get_first_paragraph(text):
    """
    Extract the first non-empty paragraph.

    PARAMETERS:
    - text: Article text

    RETURNS:
    - First paragraph string, or empty string
    """
    paragraphs = str(text).split("\n\n")

    for paragraph in paragraphs:
        stripped_paragraph = paragraph.strip()
        if stripped_paragraph:
            return stripped_paragraph

    return ""
