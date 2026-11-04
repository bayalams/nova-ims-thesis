"""
Constants used by knowledge-base evaluation.
"""

from pathlib import Path


DEFAULT_EVALUATION_OUTPUT_PATH = Path("shared_data/knowledge_bases/evaluation_metrics.json")

COMPARISON_TABLE_COLUMNS = [
    {"key": "recipe", "markdown_header": "Recipe", "format": "text"},
    {"key": "status", "markdown_header": "Status", "format": "text"},
    {"key": "embedding_model", "markdown_header": "Embedding model", "format": "text"},
    {"key": "chunking_method", "markdown_header": "Chunking", "format": "text"},
    {"key": "chunk_size_characters", "markdown_header": "Chunk size", "format": "integer"},
    {"key": "chunk_overlap_characters", "markdown_header": "Overlap", "format": "integer"},
    {"key": "expected_articles", "markdown_header": "Expected articles", "format": "integer"},
    {"key": "indexed_articles", "markdown_header": "Indexed articles", "format": "integer"},
    {"key": "article_coverage_rate", "markdown_header": "Coverage", "format": "percent"},
    {"key": "chunks", "markdown_header": "Chunks", "format": "integer"},
    {"key": "vectors", "markdown_header": "Vectors", "format": "integer"},
    {"key": "average_chunk_characters", "markdown_header": "Avg chunk chars", "format": "number"},
    {"key": "median_chunk_characters", "markdown_header": "Median chunk chars", "format": "number"},
    {"key": "average_chunks_per_article", "markdown_header": "Avg chunks/article", "format": "number"},
    {"key": "metadata_missing_rate", "markdown_header": "Metadata missing", "format": "percent"},
    {"key": "embedding_failure_rate", "markdown_header": "Embedding failure", "format": "percent"},
    {"key": "db_size_mb", "markdown_header": "DB size MB", "format": "number"},
    {"key": "build_time_seconds", "markdown_header": "Build seconds", "format": "number"},
    {"key": "query_latency_ms", "markdown_header": "Query latency ms", "format": "number"},
    {"key": "failed_to_index_articles", "markdown_header": "Failed to index", "format": "integer"},
    {"key": "article_reconstruction_rate", "markdown_header": "Reconstruction", "format": "percent"},
    {"key": "lead_paragraph_intact_rate", "markdown_header": "Lead intact", "format": "percent"},
    {"key": "boundary_break_rate", "markdown_header": "Boundary breaks", "format": "percent"},
    {"key": "boilerplate_contamination_rate", "markdown_header": "Boilerplate", "format": "percent"},
    {"key": "entity_pair_preservation_rate", "markdown_header": "Entity pairs", "format": "percent"},
    {"key": "story_level_top_k_diversity", "markdown_header": "Story diversity", "format": "percent"},
    {"key": "article_self_retrieval_top_5_rate", "markdown_header": "Article self top 5", "format": "percent"},
    {"key": "hard_negative_separation_margin", "markdown_header": "Hard negative margin", "format": "number"},
    {"key": "retrieval_hubness_rate", "markdown_header": "Hubness", "format": "percent"},
    {"key": "recency_aware_retrieval_score", "markdown_header": "Recency retrieval", "format": "number"},
    {"key": "duplicate_chunk_rate", "markdown_header": "Duplicate chunks", "format": "percent"},
    {"key": "average_adjacent_overlap_rate", "markdown_header": "Adjacent overlap", "format": "percent"},
    {"key": "title_self_retrieval_mrr", "markdown_header": "Title MRR", "format": "number"},
    {"key": "summary_self_retrieval_mrr", "markdown_header": "Summary MRR", "format": "number"},
    {"key": "combined_self_retrieval_top_5_rate", "markdown_header": "Top-5 self", "format": "percent"},
    {"key": "unique_articles_top_10", "markdown_header": "Unique articles top 10", "format": "number"},
    {"key": "max_same_article_share", "markdown_header": "Max same article", "format": "percent"},
    {"key": "overlap_waste_rate", "markdown_header": "Overlap waste", "format": "percent"},
]

REQUIRED_METADATA_FIELDS = [
    "source",
    "title",
    "url",
    "published_at",
    "indexed_at",
]

BOILERPLATE_PHRASES = [
    "advertisement",
    "all rights reserved",
    "cookie policy",
    "cookies",
    "newsletter",
    "privacy policy",
    "related articles",
    "sign up",
    "subscribe",
]

PENDING_METRICS = []

DEFAULT_ENTITY_CACHE_PATH = Path("shared_data/knowledge_bases/evaluation/entity_cache.jsonl")
DEFAULT_ENTITY_MENTIONS_PATH = Path("shared_data/knowledge_bases/evaluation/entity_mentions.jsonl")
DEFAULT_ENTITY_STORE_PATH = Path("shared_data/knowledge_bases/evaluation/entities.sqlite")
DEFAULT_ENTITY_SAMPLE_SIZE = 100
DEFAULT_ENTITY_WINDOW_BATCH_SIZE = 8

DEFAULT_THESIS_METRIC_CONFIG = {
    "ner_backend": "gliner",
    "ner_model": "urchade/gliner_multi-v2.1",
    "ner_labels": [
        "person",
        "organization",
        "location",
        "event",
        "facility",
        "product",
        "law",
        "date",
    ],
    "ner_threshold": 0.5,
    "entity_processing_version": "windowed-v2",
    "entity_window_tokens": 350,
    "entity_window_overlap_tokens": 50,
    "entity_window_batch_size": DEFAULT_ENTITY_WINDOW_BATCH_SIZE,
    "entity_pair_window_characters": 300,
    "hubness_query_share_threshold": 0.10,
    "recency_half_life_days": 14,
}
