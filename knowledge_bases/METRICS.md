# Knowledge Base Metrics

This file explains the metrics written by:

```bash
uv run --env-file .env build-kb evaluate ...
```

Use it when reading `shared_data/knowledge_bases/evaluation_metrics.json` or the
optional comparison tables created with `--table`.

## Formula Conventions

- `rate(numerator, denominator) = numerator / denominator`.
- If a denominator is `0` or missing, the metric is `null` in JSON and `n/a` in
  Markdown tables.
- `average(values) = sum(values) / count(values)`.
- `median(values)` is the middle sorted value. If there is an even number of
  values, it is the average of the two middle values.
- Text comparisons are usually normalized by lowercasing text and collapsing
  repeated whitespace.

## Sanity Metrics

These metrics answer: did the KB build correctly, and is the comparison fair?

### `input_clean_article_count`

- Name: input clean article count.
- Description: Number of valid cleaned article JSON files available in the input
  corpus folder.
- Formula: count articles where `is_valid_article` is not false and `text` is not
  blank.
- How to read: Higher means more valid input material was available. It is only
  better when the experiment was meant to index more articles.
- Examples:
  - 10 valid files and 2 invalid files -> `input_clean_article_count = 10`.
  - 0 valid files and 5 invalid files -> `input_clean_article_count = 0`.
  - 250 valid files and 0 invalid files -> `input_clean_article_count = 250`.

### `input_invalid_article_count`

- Name: input invalid article count.
- Description: Number of input article files that evaluation could not use.
- Formula: count files that fail JSON loading, have `is_valid_article = false`,
  or have blank `text`.
- How to read: Lower is better because fewer cleaned article artifacts are
  unusable.
- Examples:
  - 10 valid files and 2 invalid files -> `input_invalid_article_count = 2`.
  - 15 valid files and 0 invalid files -> `input_invalid_article_count = 0`.
  - 8 readable files plus 1 malformed JSON file -> `input_invalid_article_count = 1`.

### `expected_article_count`

- Name: expected article count.
- Description: Number of articles the recipe was expected to index after build
  filters.
- Formula: use manifest `articles_after_filters` when present; otherwise use
  manifest `articles_loaded`; otherwise use `input_clean_article_count`.
- How to read: Contextual. It is the denominator for coverage, not a quality
  score by itself.
- Examples:
  - Manifest has `articles_after_filters = 80` and `articles_loaded = 100` ->
    `expected_article_count = 80`.
  - Manifest lacks `articles_after_filters` but has `articles_loaded = 100` ->
    `expected_article_count = 100`.
  - No manifest counts and 45 valid clean articles ->
    `expected_article_count = 45`.

### `article_count`

- Name: indexed article count.
- Description: Number of article rows stored in the KB database.
- Formula: `count(rows in articles table)`.
- How to read: Higher is better only when the expected count is also higher. For
  fairness, compare it with `expected_article_count`.
- Examples:
  - The `articles` table has 80 rows -> `article_count = 80`.
  - The database exists but has no article rows -> `article_count = 0`.
  - The `articles` table has rows for article A, B, and C -> `article_count = 3`.

### `article_coverage_rate`

- Name: article coverage rate.
- Description: Share of expected articles that were actually indexed.
- Formula: `article_count / expected_article_count`.
- How to read: Higher is better because it means the KB captured more of the
  intended corpus. `1.0` means full coverage.
- Examples:
  - 80 indexed articles out of 100 expected -> `80 / 100 = 0.80`.
  - 3 indexed articles out of 3 expected -> `3 / 3 = 1.00`.
  - 0 indexed articles out of 50 expected -> `0 / 50 = 0.00`.

### `chunk_count`

- Name: chunk count.
- Description: Number of text chunks stored in the KB database.
- Formula: `count(rows in chunks table)`.
- How to read: Contextual. More chunks may improve retrieval detail, but can also
  increase cost, redundancy, and result crowding.
- Examples:
  - 100 articles split into 1 chunk each -> `chunk_count = 100`.
  - 100 articles split into 4 chunks each -> `chunk_count = 400`.
  - No indexed chunks -> `chunk_count = 0`.

### `vector_count`

- Name: vector count.
- Description: Number of embedding vectors stored for chunks.
- Formula: `count(rows in vec1_chunks table)`. If the vector table is missing,
  evaluation falls back to manifest `vector_count` when available.
- How to read: Usually this should match `chunk_count`. A lower value means some
  chunks do not have vectors and cannot be retrieved by vector search.
- Examples:
  - 300 chunks and 300 vectors -> `vector_count = 300`.
  - 300 chunks and 250 vectors -> `vector_count = 250`.
  - Missing vector table but manifest says `vector_count = 120` ->
    `vector_count = 120`.

### `chunk_size_characters`

- Name: chunk size characters.
- Description: Summary of chunk text lengths, in characters.
- Formula:
  - `average = sum(chunk lengths) / count(chunks)`
  - `median = median(chunk lengths)`
  - `min = smallest chunk length`
  - `max = largest chunk length`
- How to read: Contextual. Larger chunks preserve more context, while smaller
  chunks can retrieve narrower passages. Very tiny or very large chunks can be a
  warning sign.
- Examples:
  - Chunk lengths `[100, 200, 300]` -> average `200`, median `200`, min `100`,
    max `300`.
  - Chunk lengths `[50, 70]` -> average `60`, median `60`, min `50`, max `70`.
  - No chunks -> all summary values are `null`.

### `chunks_per_article`

- Name: chunks per article.
- Description: Summary of how many chunks each indexed article produced.
- Formula:
  - Count chunks for each indexed article.
  - Summarize those counts with average, median, min, and max.
- How to read: Contextual. Higher values mean articles are split more heavily.
  Very high values may cause retrieval results to crowd around long articles.
- Examples:
  - Article chunk counts `[1, 1, 1]` -> average `1`, median `1`, min `1`, max `1`.
  - Article chunk counts `[1, 2, 6]` -> average `3`, median `2`, min `1`, max `6`.
  - Article chunk counts `[0, 2]` -> average `1`, median `1`, min `0`, max `2`.

### `metadata_missing_rates`

- Name: metadata missing rates.
- Description: Missing-value rates for required article metadata fields:
  `source`, `title`, `url`, `published_at`, and `indexed_at`.
- Formula for each field: `missing rows for that field / article_count`.
- Formula for `any_required`: `rows missing at least one required field / article_count`.
- How to read: Lower is better because metadata is needed for source labels,
  citations, filtering, and time-aware retrieval.
- Examples:
  - 10 article rows, 2 missing `source` -> `source = 2 / 10 = 0.20`.
  - 4 article rows, 1 missing `title`, 1 missing `url`, and they are different
    rows -> `title = 0.25`, `url = 0.25`, `any_required = 2 / 4 = 0.50`.
  - 5 article rows and no missing required fields -> every field rate is `0.00`
    and `any_required = 0.00`.

### `embedding_batch_count`

- Name: embedding batch count.
- Description: Number of embedding request batches recorded in the KB database.
- Formula: `count(rows in embedding_batches table)`. If the table is missing, the
  value is `0`.
- How to read: Contextual. More batches usually means more embedding work was
  needed.
- Examples:
  - 10 rows in `embedding_batches` -> `embedding_batch_count = 10`.
  - No `embedding_batches` table -> `embedding_batch_count = 0`.
  - One build made 3 successful batches and 1 failed batch ->
    `embedding_batch_count = 4`.

### `failed_embedding_batch_count`

- Name: failed embedding batch count.
- Description: Number of embedding batches whose status is not `success`.
- Formula: `count(embedding_batches rows where lower(status) != "success")`.
- How to read: Lower is better because failed batches mean embedding work had
  errors.
- Examples:
  - Statuses `[success, success, failed]` -> `failed_embedding_batch_count = 1`.
  - Statuses `[success, success]` -> `failed_embedding_batch_count = 0`.
  - Statuses `[failed, timeout, success, error]` -> `failed_embedding_batch_count = 3`.

### `embedding_failure_rate`

- Name: embedding failure rate.
- Description: Share of embedding batches that failed.
- Formula: `failed_embedding_batch_count / embedding_batch_count`.
- How to read: Lower is better. `0.0` means every recorded batch succeeded.
- Examples:
  - 1 failed batch out of 2 batches -> `1 / 2 = 0.50`.
  - 0 failed batches out of 10 batches -> `0 / 10 = 0.00`.
  - 3 failed batches out of 12 batches -> `3 / 12 = 0.25`.

### `db_size_bytes`

- Name: database size bytes.
- Description: Size of the SQLite KB on disk, including `kb.sqlite`,
  `kb.sqlite-wal`, and `kb.sqlite-shm` when those sidecar files exist.
- Formula: `size(kb.sqlite) + size(kb.sqlite-wal) + size(kb.sqlite-shm)`.
- How to read: Lower is cheaper and easier to store, but very small databases may
  also mean the KB indexed less information.
- Examples:
  - `kb.sqlite = 1,000,000`, no sidecars -> `db_size_bytes = 1,000,000`.
  - `kb.sqlite = 1,000,000`, WAL `200,000`, SHM `32,768` ->
    `db_size_bytes = 1,232,768`.
  - Missing database -> `db_size_bytes = 0`.

### `db_size_mb`

- Name: database size megabytes.
- Description: Comparison-table version of `db_size_bytes`, converted to MiB.
- Formula: `db_size_bytes / 1,048,576`.
- How to read: Same as `db_size_bytes`. Lower is more storage-efficient when
  coverage is comparable.
- Examples:
  - `1,048,576 bytes / 1,048,576 = 1.00 MiB`.
  - `524,288 bytes / 1,048,576 = 0.50 MiB`.
  - `0 bytes / 1,048,576 = 0.00 MiB`.

### `build_time_seconds`

- Name: build time seconds.
- Description: Build runtime recorded in the recipe manifest.
- Formula: `build_end_time - build_start_time`, rounded by the builder.
- How to read: Lower is faster. Compare only builds with similar corpus sizes,
  model settings, and machine conditions.
- Examples:
  - Build starts at second `100.0` and ends at `112.5` ->
    `build_time_seconds = 12.5`.
  - Build starts at `0.0` and ends at `2.35` -> `build_time_seconds = 2.35`.
  - Manifest has no build time -> `build_time_seconds = null`.

### `query_latency_ms`

- Name: query latency milliseconds.
- Description: Average local KB search time per retrieval evaluation query.
- Formula: average elapsed milliseconds around each SQLite ANN or exact search,
  after query embeddings have already been created.
- How to read: Lower is better because searches return faster. This excludes
  OpenAI query embedding time, so it is useful for comparing KB search behavior
  across recipes.
- Examples:
  - Retrieval queries take `4 ms`, `6 ms`, and `8 ms` ->
    `query_latency_ms = 6`.
  - Evaluation run without retrieval metrics -> `query_latency_ms = null`.
  - Missing database evaluation -> `query_latency_ms = null`.

### `failed_to_index_article_count`

- Name: failed-to-index article count.
- Description: Number of expected articles that are not present in the KB
  article table.
- Formula: `max(expected_article_count - article_count, 0)`.
- How to read: Lower is better because fewer intended articles were lost.
- Examples:
  - 100 expected and 95 indexed -> `max(100 - 95, 0) = 5`.
  - 3 expected and 3 indexed -> `max(3 - 3, 0) = 0`.
  - 10 expected and 12 indexed -> `max(10 - 12, 0) = 0`.

### `skipped_too_large_article_count`

- Name: skipped too-large article count.
- Description: Number of articles skipped because a single embedding input would
  exceed the safe model token limit.
- Formula: manifest `skipped_too_large_article_count`, defaulting to `0` when
  missing.
- How to read: Lower is better. A high value means the chunking strategy may not
  handle long articles well.
- Examples:
  - Manifest says `skipped_too_large_article_count = 0` -> value `0`.
  - No-chunking recipe skips 7 long articles -> value `7`.
  - Manifest lacks the field -> value `0`.

## Thesis Metrics

These metrics evaluate whether the KB keeps news article meaning intact and
whether retrieval returns useful, timely context. The first structure metrics
are deterministic checks over articles and chunks. `entity_pair_preservation_rate`
uses precomputed local GLiNER entities, and the final five metrics are derived
from the retrieval evaluation queries.

### `article_reconstruction_accuracy`

- Name: article reconstruction accuracy.
- Description: Average share of each source article covered by that article's
  chunk character spans.
- Formula:
  - For each article, merge chunk intervals `[character_start, character_end]`.
  - `article score = covered source characters / source article characters`.
  - `article_reconstruction_accuracy = average(article scores)`.
- How to read: Higher is better because more of each article can be reconstructed
  from its chunks. `1.0` means full span coverage for every checked article.
- Examples:
  - One 100-character article with chunk interval `[0, 100]` ->
    `100 / 100 = 1.00`.
  - One 100-character article with intervals `[0, 40]` and `[60, 100]` ->
    `80 / 100 = 0.80`.
  - Two articles with scores `1.00` and `0.50` ->
    `(1.00 + 0.50) / 2 = 0.75`.

### `lead_paragraph_intact_rate`

- Name: lead paragraph intact rate.
- Description: Share of checked articles whose first chunk starts with the full
  first paragraph.
- Formula:
  - Extract the first non-empty paragraph from the source article.
  - Normalize the lead paragraph and first chunk.
  - `intact_count / checked_article_count`.
- How to read: Higher is better because the beginning of a news story often
  contains the core facts.
- Examples:
  - 10 checked articles and all 10 have intact leads -> `10 / 10 = 1.00`.
  - 5 checked articles and 4 intact leads -> `4 / 5 = 0.80`.
  - 2 checked articles and 0 intact leads -> `0 / 2 = 0.00`.

### `boundary_break_rate`

- Name: boundary break rate.
- Description: Share of chunks whose start or end offset cuts through the middle
  of an alphanumeric word.
- Formula: `broken_boundary_chunk_count / checked_chunk_count`.
- How to read: Lower is better because broken word boundaries can damage text
  readability and embedding quality.
- Examples:
  - Text `Hotel demand`, chunk `[0, 5]` ends before a space -> no break, so
    `0 / 1 = 0.00`.
  - Text `Hotel demand`, chunk `[2, 12]` starts inside `Hotel` -> break, so
    `1 / 1 = 1.00`.
  - 2 broken chunks out of 5 checked chunks -> `2 / 5 = 0.40`.

### `boilerplate_contamination_rate`

- Name: boilerplate contamination rate.
- Description: Share of chunks containing known boilerplate phrases such as
  `newsletter`, `privacy policy`, `cookies`, or `subscribe`.
- Formula: `contaminated_chunk_count / chunk_count`.
- How to read: Lower is better because boilerplate text wastes embedding space
  and can pollute retrieval.
- Examples:
  - 1 chunk containing `subscribe` out of 4 chunks -> `1 / 4 = 0.25`.
  - 0 contaminated chunks out of 10 chunks -> `0 / 10 = 0.00`.
  - No chunks -> value is `null`.

### `entity_pair_preservation_rate`

- Name: entity pair preservation rate.
- Description: Share of nearby source-article entity pairs that still co-occur
  inside at least one indexed chunk from the same article.
- Formula:
  - Select a stable sample of indexed articles. The default sample size is 100.
  - Extract or reuse cached entities from clean article text with local GLiNER
    model `urchade/gliner_multi-v2.1`.
  - Use English labels `person`, `organization`, `location`, `event`,
    `facility`, `product`, `law`, and `date` for every corpus language.
  - Build source pairs when two distinct normalized entities occur within 300
    characters.
  - Count a pair as preserved when both normalized entity texts appear in one
    same-article chunk.
  - `preserved source entity pairs / source entity pairs`.
- How to read: Higher is better. It means chunking preserved more entity
  relationships from the source articles.
- Examples:
  - 10 source entity pairs and 8 preserved pairs -> `8 / 10 = 0.80`.
  - 4 source entity pairs and 0 preserved pairs -> `0 / 4 = 0.00`.
  - No source entity pairs -> `null`.

### `story_level_top_k_diversity`

- Name: story-level top-k diversity.
- Description: Average share of retrieved result slots represented by distinct
  article IDs.
- Formula: for each retrieval query, `distinct article IDs in top k / returned
  result count`, then average across queries.
- How to read: Higher is better when broad context is desired. Low values mean
  retrieval is crowded by repeated chunks from the same story.
- Examples:
  - Results `[A, B, C]` -> `3 / 3 = 1.00`.
  - Results `[A, A, B]` -> `2 / 3 = 0.67`.
  - No retrieval queries -> `null`.

### `article_self_retrieval_top_5_rate`

- Name: article self-retrieval top-5 rate.
- Description: Share of title and summary self-retrieval queries where the
  source article appears in the first five results.
- Formula: same value as
  `retrieval_metrics.self_retrieval.combined_top_5_rate`.
- How to read: Higher is better. `1.0` means every article query found its own
  source article within five results.
- Examples:
  - Match ranks `[1, 5, missing]` -> `2 / 3 = 0.67`.
  - Match ranks `[6, missing]` -> `0 / 2 = 0.00`.
  - No retrieval queries -> `null`.

### `hard_negative_separation_margin`

- Name: hard negative separation margin.
- Description: Average distance gap between the best wrong result and the best
  correct result for self-retrieval queries.
- Formula: for each query, `best wrong-result distance - best correct-result
  distance`, then average scored queries.
- How to read: Higher is better. Positive values mean the correct article is
  closer than the most competitive wrong result. Missing correct articles score
  `0.0`.
- Examples:
  - Correct distance `0.10`, best wrong distance `0.25` -> `0.15`.
  - Correct distance `0.35`, best wrong distance `0.20` -> `-0.15`.
  - Correct article missing -> `0.0`.

### `retrieval_hubness_rate`

- Name: retrieval hubness rate.
- Description: Share of result slots occupied by article IDs that appear across
  more than 10% of retrieval queries.
- Formula:
  - `article_query_share = queries where article appears / query_count`.
  - A hub article has `article_query_share > 0.10`.
  - `result slots occupied by hub article IDs / total result slots`.
- How to read: Lower is better. High values mean retrieval is dominated by a
  small set of repeatedly returned articles.
- Examples:
  - No article crosses the hub threshold -> `0.00`.
  - 20 hub article result slots out of 100 result slots -> `0.20`.
  - No result slots -> `null`.

### `recency_aware_retrieval_score`

- Name: recency-aware retrieval score.
- Description: Average rank-weighted freshness score for retrieval results.
- Formula:
  - Use the query article `published_at` as the reference date.
  - `rank_credit = 1 / rank`.
  - `recency_credit = 0.5 ** (age_days / 14)`.
  - Result score is `rank_credit * recency_credit`.
  - Average result scores per query, then average across queries.
- How to read: Higher is better. Recent high-ranked results receive the most
  credit.
- Examples:
  - Rank 1 result from same day -> `1.0 * 1.0 = 1.0`.
  - Rank 2 result 14 days old -> `0.5 * 0.5 = 0.25`.
  - No parseable retrieval dates -> `null`.

### Entity Mention Artifacts

Entity-pair evaluation writes inspectable generated artifacts under:

```text
shared_data/knowledge_bases/evaluation/entities.sqlite
shared_data/knowledge_bases/evaluation/entity_mentions.jsonl
```

`entities.sqlite` stores reusable GLiNER output keyed by cleaned article text,
NER configuration, windowing settings, and resolved device. Normal evaluation
computes missing entities on demand only for sampled articles. Build or refresh
the cache ahead of time only when useful:

```bash
uv run build-kb precompute-entities all
```

The default GLiNER path uses Apple MPS when available, splits long articles into
350-token windows with 50-token overlap, batches 8 GLiNER windows at a time, and
prints elapsed time plus an ETA during explicit precompute runs.
`entity_mentions.jsonl` stores the latest evaluation's sampled entities and
entity pairs, including whether each pair was preserved in a chunk.

These files are generated shared data and are not committed.

## Diagnostic Metrics

These metrics explain why a KB behaves the way it does.

### `duplicate_chunk_rate`

- Name: duplicate chunk rate.
- Description: Share of chunks whose normalized text repeats a previous chunk.
- Formula: `duplicate_after_first_count / chunk_count`.
- How to read: Lower is better because duplicate chunks waste storage and can
  crowd retrieval results.
- Examples:
  - Chunks `[A, B, C]` -> no repeats -> `0 / 3 = 0.00`.
  - Chunks `[A, A, B]` -> one repeated chunk -> `1 / 3 = 0.33`.
  - Chunks `[A, A, A]` -> two repeats after the first -> `2 / 3 = 0.67`.

### `same_article_max_chunk_share`

- Name: same-article max chunk share.
- Description: Largest share of all chunks that come from one article.
- Formula: `max(chunks from one article) / chunk_count`.
- How to read: Lower usually means the chunk set is less dominated by one long
  article. It is contextual because genuinely long articles may need more
  chunks.
- Examples:
  - Chunk counts by article `{A: 2, B: 2, C: 2}` -> `2 / 6 = 0.33`.
  - Chunk counts by article `{A: 8, B: 1, C: 1}` -> `8 / 10 = 0.80`.
  - One article with 5 chunks -> `5 / 5 = 1.00`.

### `average_adjacent_overlap_rate`

- Name: average adjacent overlap rate.
- Description: Average exact character overlap between adjacent chunks from the
  same article.
- Formula:
  - For each adjacent chunk pair, find the longest suffix of the previous chunk
    that equals the prefix of the current chunk.
  - `pair overlap rate = overlap characters / min(previous length, current length)`.
  - Average all pair overlap rates.
- How to read: Lower means less repeated text. Some overlap can be intentional,
  but high values mean storage and context are being spent on repeated content.
- Examples:
  - `abcDEF` followed by `DEFghi` -> overlap `3`, denominator `6`, rate `0.50`.
  - `abcdef` followed by `ghijkl` -> overlap `0`, denominator `6`, rate `0.00`.
  - Pair rates `[0.50, 0.00]` -> average `(0.50 + 0.00) / 2 = 0.25`.

### `empty_chunk_rate`

- Name: empty chunk rate.
- Description: Share of chunks whose text is blank after trimming whitespace.
- Formula: `empty_chunk_count / chunk_count`.
- How to read: Lower is better. Empty chunks should normally be `0`.
- Examples:
  - Chunk texts `["A", "B", ""]` -> `1 / 3 = 0.33`.
  - Chunk texts `["A", "   ", "C", ""]` -> `2 / 4 = 0.50`.
  - Chunk texts `["A", "B"]` -> `0 / 2 = 0.00`.

### `article_rows_with_zero_chunks`

- Name: article rows with zero chunks.
- Description: Count of indexed article rows that have no chunk rows.
- Formula: count article IDs in `articles` with chunk count `0`.
- How to read: Lower is better because every indexed article should normally
  have at least one searchable chunk.
- Examples:
  - Article chunk counts `{A: 1, B: 2, C: 1}` -> `0`.
  - Article chunk counts `{A: 0, B: 2, C: 0}` -> `2`.
  - No indexed articles -> `0`.

## Retrieval Metrics

These metrics run by default when evaluation is called. They embed title and
summary queries, search the KB, and inspect the ranked results.

### `config.sample_size`

- Name: retrieval sample size.
- Description: Number of sorted indexed articles selected for retrieval metric
  queries.
- Formula: CLI `--retrieval-sample-size`, default `100`.
- How to read: Contextual. Higher samples give broader estimates but cost more
  embedding work.
- Examples:
  - Default evaluation -> `sample_size = 100`.
  - CLI `--retrieval-sample-size 25` -> `sample_size = 25`.
  - Only 10 indexed articles exist with `sample_size = 100` -> config still says
    `100`, but only available articles can produce queries.

### `config.top_k`

- Name: retrieval top k.
- Description: Number of ranked results requested for each retrieval query.
- Formula: CLI `--retrieval-top-k`, default `10`.
- How to read: Contextual. Higher `top_k` inspects more results but may include
  weaker matches.
- Examples:
  - Default retrieval evaluation -> `top_k = 10`.
  - CLI `--retrieval-top-k 5` -> `top_k = 5`.
  - CLI `--retrieval-top-k 20` -> `top_k = 20`.

### `config.query_count`

- Name: retrieval query count.
- Description: Number of title and summary queries actually evaluated.
- Formula: `title_query_count + summary_query_count`.
- How to read: Higher means more retrieval checks were run. It is contextual,
  not automatically better.
- Examples:
  - 10 sampled articles, each with title and summary -> `10 + 10 = 20`.
  - 10 sampled articles, titles only, no summaries -> `10 + 0 = 10`.
  - No sampled articles -> `0 + 0 = 0`.

### `config.title_query_count`

- Name: title query count.
- Description: Number of evaluated queries created from article titles.
- Formula: count sampled articles with a nonblank clean title, falling back to
  database title when the clean title is blank.
- How to read: Higher gives a stronger title-retrieval estimate.
- Examples:
  - 50 sampled articles and 50 usable titles -> `title_query_count = 50`.
  - 50 sampled articles and 45 usable titles -> `title_query_count = 45`.
  - 10 sampled articles and no titles -> `title_query_count = 0`.

### `config.summary_query_count`

- Name: summary query count.
- Description: Number of evaluated queries created from clean article summaries.
- Formula: count sampled articles with nonblank clean `summary`.
- How to read: Higher gives a stronger summary-retrieval estimate.
- Examples:
  - 50 sampled articles and 50 summaries -> `summary_query_count = 50`.
  - 50 sampled articles and 20 summaries -> `summary_query_count = 20`.
  - 10 sampled articles and no summaries -> `summary_query_count = 0`.

### `self_retrieval.title_mrr`

- Name: title mean reciprocal rank.
- Description: Average reciprocal rank for title queries finding their own
  article.
- Formula:
  - For each title query, find the first rank where `result.article_id` equals
    the query article ID.
  - Query score is `1 / rank`, or `0` if missing.
  - `title_mrr = average(title query scores)`.
- How to read: Higher is better. `1.0` means every title query found its article
  at rank 1.
- Examples:
  - Title match ranks `[1, 1, 1]` -> `(1 + 1 + 1) / 3 = 1.00`.
  - Title match ranks `[1, 2, missing]` -> `(1 + 0.5 + 0) / 3 = 0.50`.
  - No title queries -> `title_mrr = null`.

### `self_retrieval.summary_mrr`

- Name: summary mean reciprocal rank.
- Description: Average reciprocal rank for summary queries finding their own
  article.
- Formula:
  - For each summary query, score `1 / rank` for the first matching article, or
    `0` if missing.
  - `summary_mrr = average(summary query scores)`.
- How to read: Higher is better. It shows whether summary-like queries retrieve
  the right article.
- Examples:
  - Summary match ranks `[1, 5]` -> `(1 + 0.2) / 2 = 0.60`.
  - Summary match ranks `[5, missing, missing]` -> `(0.2 + 0 + 0) / 3 = 0.07`.
  - No summary queries -> `summary_mrr = null`.

### `self_retrieval.combined_mrr`

- Name: combined mean reciprocal rank.
- Description: Average reciprocal rank across title and summary queries together.
- Formula: `average(all title and summary reciprocal-rank scores)`.
- How to read: Higher is better because the correct article appears earlier in
  ranked results across all query types.
- Examples:
  - Query scores `[1.0, 0.5, 0.0]` -> `(1.0 + 0.5 + 0.0) / 3 = 0.50`.
  - Query scores `[0.2, 0.2, 0.2]` -> `0.20`.
  - No queries -> `combined_mrr = null`.

### `self_retrieval.combined_top_5_rate`

- Name: combined top-5 self-retrieval rate.
- Description: Share of all retrieval queries where the correct article appears
  within the first 5 results.
- Formula: `queries with first matching rank <= 5 / query_count`.
- How to read: Higher is better. `1.0` means every title or summary query found
  its article in the top 5.
- Examples:
  - Match ranks `[1, 5, missing]` -> `2 / 3 = 0.67`.
  - Match ranks `[6, 10]` -> `0 / 2 = 0.00`.
  - Match ranks `[2, 3, 4, 5]` -> `4 / 4 = 1.00`.

### `self_retrieval.combined_top_10_rate`

- Name: combined top-10 self-retrieval rate.
- Description: Share of all retrieval queries where the correct article appears
  within the first 10 results.
- Formula: `queries with first matching rank <= 10 / query_count`.
- How to read: Higher is better. It is less strict than top-5.
- Examples:
  - Match ranks `[1, 5, missing]` -> `2 / 3 = 0.67`.
  - Match ranks `[6, 10, 11]` -> `2 / 3 = 0.67`.
  - Match ranks `[11, missing]` -> `0 / 2 = 0.00`.

### `context_efficiency.unique_article_share`

- Name: unique article share.
- Description: Share of returned result rows represented by unique nonblank
  article IDs.
- Formula: `unique returned article IDs / total returned results`.
- How to read: Higher means more article variety in retrieved context. This is
  usually good, but some queries may legitimately need multiple chunks from one
  article.
- Examples:
  - Results from articles `[A, B, C]` -> `3 / 3 = 1.00`.
  - Results from articles `[A, A, B]` -> `2 / 3 = 0.67`.
  - No returned results -> `unique_article_share = null`.

### `context_efficiency.unique_source_share`

- Name: unique source share.
- Description: Share of returned result rows represented by unique nonblank news
  sources.
- Formula: `unique returned source values / total returned results`.
- How to read: Higher means more source variety. This can help avoid reports
  overusing one publication.
- Examples:
  - Sources `[PUBLICO, OBSERVADOR, RTP]` -> `3 / 3 = 1.00`.
  - Sources `[PUBLICO, PUBLICO, RTP]` -> `2 / 3 = 0.67`.
  - No returned results -> `unique_source_share = null`.

### `context_efficiency.unique_date_share`

- Name: unique date share.
- Description: Share of returned result rows represented by unique publication
  dates.
- Formula: `unique published_at date prefixes / total returned results`, where
  the date prefix is the first 10 characters of `published_at`.
- How to read: Higher means retrieved context spans more dates. Whether this is
  better depends on the query and the report date.
- Examples:
  - Dates `[2026-05-01, 2026-05-02, 2026-05-03]` -> `3 / 3 = 1.00`.
  - Dates `[2026-05-01, 2026-05-01, 2026-05-02]` -> `2 / 3 = 0.67`.
  - No returned results -> `unique_date_share = null`.

### `context_efficiency.duplicate_text_share`

- Name: duplicate text share.
- Description: Share of returned chunks whose normalized text repeats a previous
  returned chunk.
- Formula: `duplicate returned text count after first occurrence / total returned results`.
- How to read: Lower is better because duplicate context wastes top-k space.
- Examples:
  - Returned texts `[A, B, C]` -> `0 / 3 = 0.00`.
  - Returned texts `[A, A, B]` -> `1 / 3 = 0.33`.
  - Returned texts `[A, A, A, B]` -> `2 / 4 = 0.50`.

### `context_efficiency.overlap_waste_rate`

- Name: overlap waste rate.
- Description: Share of returned characters that are repeated overlap between
  adjacent ranked results from neighboring chunks of the same article.
- Formula:
  - Count overlap characters only for adjacent result pairs where the two results
    have the same `article_id` and neighboring `chunk_index` values.
  - `overlap_waste_rate = overlap characters / total returned chunk characters`.
- How to read: Lower is better because less returned context is repeated text.
- Examples:
  - Returned chunk texts have total length `300` and overlap `0` ->
    `0 / 300 = 0.00`.
  - Total returned length `300` and neighboring overlap `30` ->
    `30 / 300 = 0.10`.
  - No returned text characters -> `overlap_waste_rate = null`.

### `top_k_crowding.max_same_article_share`

- Name: max same-article share.
- Description: For each query, the largest share of its ranked results that come
  from one article, then averaged across queries.
- Formula:
  - Per query: `max(results from one article) / result_count`.
  - Overall: average of per-query shares.
- How to read: Lower is usually better because top-k results are less crowded by
  one article.
- Examples:
  - One query results `[A, B, C]` -> `1 / 3 = 0.33`.
  - One query results `[A, A, B]` -> `2 / 3 = 0.67`.
  - Two query shares `[0.50, 1.00]` -> average `0.75`.

### `top_k_crowding.unique_articles_top_5`

- Name: unique articles top 5.
- Description: Average number of unique nonblank article IDs in the first 5
  results for each query.
- Formula: `average(count unique article_id values in results[0:5])`.
- How to read: Higher means more article diversity in the top 5. Maximum is `5`.
- Examples:
  - Top 5 article IDs `[A, B, C, D, E]` -> `5`.
  - Top 5 article IDs `[A, A, B, B, C]` -> `3`.
  - Two query counts `[5, 3]` -> average `4`.

### `top_k_crowding.unique_sources_top_5`

- Name: unique sources top 5.
- Description: Average number of unique nonblank source values in the first 5
  results for each query.
- Formula: `average(count unique source values in results[0:5])`.
- How to read: Higher means more source diversity in the top 5. Maximum is `5`.
- Examples:
  - Top 5 sources `[A, B, C, D, E]` -> `5`.
  - Top 5 sources `[A, A, A, B, B]` -> `2`.
  - Two query counts `[4, 2]` -> average `3`.

### `top_k_crowding.unique_articles_top_10`

- Name: unique articles top 10.
- Description: Average number of unique nonblank article IDs in the first 10
  results for each query.
- Formula: `average(count unique article_id values in results[0:10])`.
- How to read: Higher means more article diversity in the top 10. Maximum is
  `10`.
- Examples:
  - Top 10 article IDs are all different -> `10`.
  - Top 10 article IDs contain 4 unique articles -> `4`.
  - Two query counts `[10, 4]` -> average `7`.

### `top_k_crowding.unique_sources_top_10`

- Name: unique sources top 10.
- Description: Average number of unique nonblank source values in the first 10
  results for each query.
- Formula: `average(count unique source values in results[0:10])`.
- How to read: Higher means more source diversity in the top 10. Maximum is `10`.
- Examples:
  - Top 10 sources are all different -> `10`.
  - Top 10 sources contain 3 unique publications -> `3`.
  - Two query counts `[8, 3]` -> average `5.5`.

### `top_k_crowding.adjacent_chunk_pair_count`

- Name: adjacent chunk pair count.
- Description: Total number of adjacent ranked result pairs that are neighboring
  chunks from the same article.
- Formula: count adjacent result pairs where `article_id` matches and
  `abs(first.chunk_index - second.chunk_index) == 1`.
- How to read: Lower is usually better because many neighboring chunks in the
  same top-k list can crowd out other articles.
- Examples:
  - Results `[A0, A1, B0]` -> `A0` and `A1` are neighboring -> count `1`.
  - Results `[A0, A2, B0]` -> not neighboring indexes -> count `0`.
  - Two queries with pair counts `1` and `2` -> total `3`.

## Comparison Table Aliases

The Markdown and CSV tables flatten some JSON names:

| Table column | JSON metric |
| --- | --- |
| `expected_articles` | `sanity_metrics.expected_article_count` |
| `indexed_articles` | `sanity_metrics.article_count` |
| `coverage` / `article_coverage_rate` | `sanity_metrics.article_coverage_rate` |
| `chunks` | `sanity_metrics.chunk_count` |
| `vectors` | `sanity_metrics.vector_count` |
| `average_chunk_characters` | `sanity_metrics.chunk_size_characters.average` |
| `median_chunk_characters` | `sanity_metrics.chunk_size_characters.median` |
| `average_chunks_per_article` | `sanity_metrics.chunks_per_article.average` |
| `metadata_missing_rate` | `sanity_metrics.metadata_missing_rates.any_required` |
| `db_size_mb` | `sanity_metrics.db_size_bytes / 1048576` |
| `failed_to_index_articles` | `sanity_metrics.failed_to_index_article_count` |
| `article_reconstruction_rate` | `thesis_metrics.article_reconstruction_accuracy` |
| `title_self_retrieval_mrr` | `retrieval_metrics.self_retrieval.title_mrr` |
| `summary_self_retrieval_mrr` | `retrieval_metrics.self_retrieval.summary_mrr` |
| `combined_self_retrieval_top_5_rate` | `retrieval_metrics.self_retrieval.combined_top_5_rate` |
| `unique_articles_top_10` | `retrieval_metrics.top_k_crowding.unique_articles_top_10` |
| `max_same_article_share` | `retrieval_metrics.top_k_crowding.max_same_article_share` |
| `overlap_waste_rate` | `retrieval_metrics.context_efficiency.overlap_waste_rate` |
