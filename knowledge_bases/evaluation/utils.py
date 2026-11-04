"""
Small shared helpers for knowledge-base evaluation.
"""

import json
from pathlib import Path


def load_json_file(json_path):
    """
    Load a JSON file if it exists.

    PARAMETERS:
    - json_path: Path to JSON file

    RETURNS:
    - Dictionary from the file, or an empty dictionary
    """
    json_path = Path(json_path)
    if not json_path.exists():
        return {}

    json_text = json_path.read_text(encoding="utf-8")
    return json.loads(json_text)


def make_number_summary(values):
    """
    Summarize numeric values.

    PARAMETERS:
    - values: List of numbers

    RETURNS:
    - Dictionary with average, median, min, and max
    """
    if not values:
        return {
            "average": None,
            "median": None,
            "min": None,
            "max": None,
        }

    sorted_values = sorted(values)
    return {
        "average": sum(sorted_values) / len(sorted_values),
        "median": calculate_median(sorted_values),
        "min": sorted_values[0],
        "max": sorted_values[-1],
    }


def calculate_median(sorted_values):
    """
    Calculate the median of a sorted list.

    PARAMETERS:
    - sorted_values: Sorted list of numbers

    RETURNS:
    - Median value
    """
    count = len(sorted_values)
    middle = count // 2

    if count % 2 == 1:
        return sorted_values[middle]

    return (sorted_values[middle - 1] + sorted_values[middle]) / 2


def average_or_none(values):
    """
    Average a list, returning None for an empty list.

    PARAMETERS:
    - values: List of numeric values

    RETURNS:
    - Average, or None
    """
    if not values:
        return None

    return sum(values) / len(values)


def safe_rate(numerator, denominator):
    """
    Divide two numbers, returning None when the denominator is zero.

    PARAMETERS:
    - numerator: Numerator
    - denominator: Denominator

    RETURNS:
    - Rate, or None
    """
    if denominator is None:
        return None

    if denominator == 0:
        return None

    return numerator / denominator


def safe_int(value):
    """
    Convert a value to int when possible.

    PARAMETERS:
    - value: Value to convert

    RETURNS:
    - Integer, or None
    """
    if value is None:
        return None

    try:
        return int(value)
    except Exception:
        return None


def is_missing_value(value):
    """
    Check whether a metadata value is missing.

    PARAMETERS:
    - value: Value to check

    RETURNS:
    - True if missing
    """
    if value is None:
        return True

    if str(value).strip() == "":
        return True

    return False


def normalize_text_for_comparison(text):
    """
    Normalize text for simple exact comparisons.

    PARAMETERS:
    - text: Text to normalize

    RETURNS:
    - Lowercased whitespace-collapsed text
    """
    parts = str(text).lower().split()
    return " ".join(parts)


def get_database_size_bytes(db_path):
    """
    Count the SQLite database size on disk, including WAL sidecars.

    PARAMETERS:
    - db_path: Path to kb.sqlite

    RETURNS:
    - Size in bytes
    """
    db_path = Path(db_path)
    possible_paths = [
        db_path,
        Path(str(db_path) + "-wal"),
        Path(str(db_path) + "-shm"),
    ]

    total_size = 0
    for possible_path in possible_paths:
        if possible_path.exists():
            total_size = total_size + possible_path.stat().st_size

    return total_size


def bytes_to_megabytes(value):
    """
    Convert bytes to MiB.

    PARAMETERS:
    - value: Byte count

    RETURNS:
    - Megabytes as a float, or None
    """
    if value is None:
        return None

    try:
        return float(value) / 1048576
    except Exception:
        return None


def format_optional_rate(value):
    """
    Format an optional rate for terminal output.

    PARAMETERS:
    - value: Optional numeric value

    RETURNS:
    - String
    """
    if value is None:
        return "n/a"

    return f"{value:.3f}"
