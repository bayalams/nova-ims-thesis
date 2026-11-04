"""
Text chunking helpers for knowledge-base recipes.

"""


def make_chunk_record(text, chunk_index, character_start, character_end):
    """
    Create one chunk dictionary.

    PARAMETERS:
    - text: The chunk text
    - chunk_index: The zero-based chunk number inside the article
    - character_start: Where this chunk starts in the article text
    - character_end: Where this chunk ends in the article text

    RETURNS:
    - A dictionary describing one chunk
    """
    return {
        "chunk_index": chunk_index,
        "text": text,
        "character_start": character_start,
        "character_end": character_end,
    }


def make_single_chunk(text):
    """
    Return the full article as one chunk.

    PARAMETERS:
    - text: The cleaned article text

    RETURNS:
    - A list with one chunk dictionary
    """
    cleaned_text = text.strip()

    if not cleaned_text:
        return []

    return [make_chunk_record(cleaned_text, 0, 0, len(text))]


def validate_chunk_settings(chunk_size, chunk_overlap):
    """
    Check that fixed-size chunk settings are safe.

    PARAMETERS:
    - chunk_size: Maximum characters per chunk
    - chunk_overlap: Characters repeated between neighboring chunks

    RETURNS:
    - None

    RAISES:
    - ValueError when the settings cannot safely move forward
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")


def make_fixed_chunks(text, chunk_size, chunk_overlap):
    """
    Split text into fixed-size character chunks.

    PARAMETERS:
    - text: The cleaned article text
    - chunk_size: Maximum characters per chunk
    - chunk_overlap: Characters repeated between neighboring chunks

    RETURNS:
    - A list of chunk dictionaries
    """
    validate_chunk_settings(chunk_size, chunk_overlap)

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        # Step 1: Pick the next character window.
        end = start + chunk_size
        chunk_text = text[start:end]

        # Step 2: Keep only chunks with real content.
        if chunk_text.strip():
            chunks.append(make_chunk_record(chunk_text, chunk_index, start, min(end, len(text))))
            chunk_index = chunk_index + 1

        # Step 3: Move forward, keeping the requested overlap.
        start = end - chunk_overlap

    return chunks


def split_text_with_separator(text, separator):
    """
    Split text while keeping separators attached to earlier pieces.

    PARAMETERS:
    - text: The text to split
    - separator: The separator to split on

    RETURNS:
    - A list of text pieces
    """
    if separator not in text:
        return [text]

    raw_parts = text.split(separator)
    parts = []

    for position, part in enumerate(raw_parts):
        if position < len(raw_parts) - 1:
            parts.append(part + separator)
        else:
            parts.append(part)

    return parts


def split_large_piece(piece, chunk_size):
    """
    Split one oversized text piece using natural separators when possible.

    PARAMETERS:
    - piece: The text piece to split
    - chunk_size: Maximum characters per chunk

    RETURNS:
    - A list of smaller pieces
    """
    separators = ["\n\n", "\n", ". ", " "]

    for separator in separators:
        smaller_parts = split_text_with_separator(piece, separator)

        if len(smaller_parts) == 1:
            continue

        longest_part = 0
        for smaller_part in smaller_parts:
            if len(smaller_part) > longest_part:
                longest_part = len(smaller_part)

        if longest_part < len(piece):
            return smaller_parts

    return make_plain_character_parts(piece, chunk_size)


def make_plain_character_parts(text, chunk_size):
    """
    Split text by character count when no natural separator helps.

    PARAMETERS:
    - text: The text to split
    - chunk_size: Maximum characters per part

    RETURNS:
    - A list of text parts
    """
    parts = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        parts.append(text[start:end])
        start = end

    return parts


def pack_recursive_parts(parts, chunk_size):
    """
    Pack smaller text parts into chunks up to chunk_size.

    PARAMETERS:
    - parts: A list of text pieces
    - chunk_size: Maximum characters per chunk

    RETURNS:
    - A list of chunk text strings
    """
    packed_chunks = []
    current_chunk = ""

    for part in parts:
        # Step 1: Split oversized parts before trying to pack them.
        if len(part) > chunk_size:
            split_parts = split_large_piece(part, chunk_size)
            nested_chunks = pack_recursive_parts(split_parts, chunk_size)

            for nested_chunk in nested_chunks:
                if nested_chunk.strip():
                    packed_chunks.append(nested_chunk)

            current_chunk = ""
            continue

        # Step 2: Add the part if it still fits in the current chunk.
        if len(current_chunk) + len(part) <= chunk_size:
            current_chunk = current_chunk + part
            continue

        # Step 3: Start a new chunk when the current one would overflow.
        if current_chunk.strip():
            packed_chunks.append(current_chunk)

        current_chunk = part

    if current_chunk.strip():
        packed_chunks.append(current_chunk)

    return packed_chunks


def add_overlap_to_recursive_chunks(chunk_texts, chunk_overlap):
    """
    Add character overlap between recursive chunks.

    PARAMETERS:
    - chunk_texts: A list of chunk text strings
    - chunk_overlap: Characters copied from the previous chunk

    RETURNS:
    - A list of chunk text strings with overlap added
    """
    if chunk_overlap <= 0:
        return chunk_texts

    overlapped_chunks = []

    for position, chunk_text in enumerate(chunk_texts):
        if position == 0:
            overlapped_chunks.append(chunk_text)
            continue

        previous_chunk = chunk_texts[position - 1]
        prefix = previous_chunk[-chunk_overlap:]
        overlapped_chunks.append(prefix + chunk_text)

    return overlapped_chunks


def find_chunk_start(text, chunk_text, search_start):
    """
    Find a chunk's start position in the original article text.

    PARAMETERS:
    - text: The full article text
    - chunk_text: The chunk to find
    - search_start: Where to begin searching

    RETURNS:
    - The best character start position
    """
    found_at = text.find(chunk_text.strip(), search_start)

    if found_at >= 0:
        return found_at

    return search_start


def make_recursive_chunks(text, chunk_size, chunk_overlap):
    """
    Split text into chunks while preferring natural boundaries.

    PARAMETERS:
    - text: The cleaned article text
    - chunk_size: Maximum characters per chunk
    - chunk_overlap: Characters copied between neighboring chunks

    RETURNS:
    - A list of chunk dictionaries
    """
    validate_chunk_settings(chunk_size, chunk_overlap)

    first_parts = split_text_with_separator(text, "\n\n")
    chunk_texts = pack_recursive_parts(first_parts, chunk_size)
    chunk_texts = add_overlap_to_recursive_chunks(chunk_texts, chunk_overlap)

    chunks = []
    search_start = 0

    for chunk_index, chunk_text in enumerate(chunk_texts):
        stripped_text = chunk_text.strip()

        if not stripped_text:
            continue

        character_start = find_chunk_start(text, stripped_text, search_start)
        character_end = character_start + len(stripped_text)
        chunks.append(make_chunk_record(stripped_text, chunk_index, character_start, character_end))
        search_start = character_end

    return chunks


def chunk_article_text(text, method, chunk_size, chunk_overlap):
    """
    Chunk article text using the requested recipe method.

    PARAMETERS:
    - text: The cleaned article text
    - method: "none", "fixed_size", or "recursive"
    - chunk_size: Maximum characters per chunk
    - chunk_overlap: Characters repeated between chunks

    RETURNS:
    - A list of chunk dictionaries
    """
    if method == "none":
        return make_single_chunk(text)

    if method == "fixed_size":
        return make_fixed_chunks(text, chunk_size, chunk_overlap)

    if method == "recursive":
        return make_recursive_chunks(text, chunk_size, chunk_overlap)

    raise ValueError(f"Unknown chunking method: {method}")
