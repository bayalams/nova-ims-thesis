# Reporting Metrics

This file explains the metrics written by report manifests and by report run
evaluation files:

```bash
uv run report run ...
uv run report run-batch ...
uv run report evaluate-run shared_data/reports/<run-name>
```

Per-strategy report manifests store metrics under `metrics` and model usage
under `model_metrics`. Batch evaluation writes flattened rows to:

```text
shared_data/reports/<run-name>/evaluation.csv
shared_data/reports/<run-name>/evaluation.json
```

## Formula Conventions

- `rate(numerator, denominator) = numerator / denominator`.
- Some report rates use `max(1, denominator)` so empty denominators become `1`
  instead of causing division by zero.
- Source citations are matched with `[Source N]` or `[Sources N, M]`.
- Distinct cited source numbers are unique numbers extracted from citation
  brackets.
- A valid source number is between `1` and the number of registered source
  articles.
- Report lines are non-empty lines.
- Citation lines are non-empty lines containing a source citation.
- Temporal buckets use the report window:
  - `daily_window`: article timestamp is inside the report window.
  - `past`: article timestamp is before the report window.
  - `future`: article timestamp is after the report window.
  - `unknown`: article timestamp or report window could not be parsed.

## Citation Behavior

These metrics answer: did the report cite its evidence correctly?

### `citation_count`

- Name: citation count.
- Description: Number of citation bracket occurrences in the report text.
- Formula: count every bracket that matches `[Source ...]` or `[Sources ...]`.
- How to read: Higher means the report has more inline citations. This is often
  good for traceability, but very high values can also mean dense or repetitive
  writing.
- Examples:
  - `Claim [Source 1].` -> `citation_count = 1`.
  - `A [Source 1]. B [Sources 2, 3].` -> `citation_count = 2`.
  - `No citation here.` -> `citation_count = 0`.

### `distinct_cited_sources`

- Name: distinct cited sources.
- Description: Number of unique numbered sources cited at least once.
- Formula: `count(unique source numbers extracted from citation brackets)`.
- How to read: Higher means the report uses a wider evidence base. It is better
  when the extra sources are relevant and valid.
- Examples:
  - `[Source 1] [Source 1]` -> unique numbers `{1}` -> `1`.
  - `[Source 1] [Sources 2, 3]` -> unique numbers `{1, 2, 3}` -> `3`.
  - No citations -> unique numbers `{}` -> `0`.

### `citation_reference_validity_rate`

- Name: citation reference validity rate.
- Description: Share of distinct cited source numbers that point to registered
  source articles.
- Formula: `valid distinct cited source numbers / distinct cited source numbers`.
  If there are no cited source numbers, the value is `1.0`.
- How to read: Higher is better because citations point to real source-pool
  entries. `1.0` means every cited number is in range.
- Examples:
  - Source pool has 3 sources and report cites `{1, 2}` -> `2 / 2 = 1.00`.
  - Source pool has 3 sources and report cites `{1, 4}` -> `1 / 2 = 0.50`.
  - Report cites no sources -> `1.00`.

### `citation_out_of_range_count`

- Name: citation out-of-range count.
- Description: Number of distinct cited source numbers that do not exist in the
  source pool.
- Formula: `distinct cited source numbers - valid distinct cited source numbers`.
- How to read: Lower is better. Any value above `0` means the report cites a
  missing source number.
- Examples:
  - Source pool has 5 sources and report cites `{1, 5}` -> `0`.
  - Source pool has 5 sources and report cites `{1, 8}` -> `1`.
  - Source pool has 2 sources and report cites `{3, 4, 5}` -> `3`.

### `citation_nonstandard_count`

- Name: citation nonstandard count.
- Description: Number of citation brackets whose payload is not a clean numeric
  list.
- Formula: count citation brackets whose inside text does not match
  `N` or `N, M, K`.
- How to read: Lower is better because standard citations are easier to parse and
  audit.
- Examples:
  - `[Source 1]` -> standard -> `0`.
  - `[Sources 1, 2]` -> standard -> `0`.
  - `[Source 2, historical articles]` -> nonstandard -> `1`.

## Daily Evidence Use

These metrics answer: how much of the daily article set did the report use?

### `daily_article_count`

- Name: daily article count.
- Description: Number of daily input articles registered as source articles.
- Formula: `count(registry.daily_article_ids)`.
- How to read: Contextual. It is the available daily evidence denominator, not a
  quality score by itself.
- Examples:
  - Daily IDs `[a1, a2, a3]` -> `daily_article_count = 3`.
  - Daily IDs `[]` -> `daily_article_count = 0`.
  - Daily IDs `[a1]` -> `daily_article_count = 1`.

### `cited_daily_article_count`

- Name: cited daily article count.
- Description: Number of valid cited sources whose article ID belongs to the
  daily input article set.
- Formula: count cited article IDs where `article_id in daily_article_ids`.
- How to read: Higher means the report cited more daily material. It is usually
  better for daily reports, as long as citations are relevant.
- Examples:
  - Daily IDs `{a1, a2}` and cited article IDs `[a1, a2]` -> `2`.
  - Daily IDs `{a1, a2}` and cited article IDs `[a1, kb1]` -> `1`.
  - No cited daily articles -> `0`.

### `cited_daily_article_rate`

- Name: cited daily article rate.
- Description: Share of daily articles that were cited.
- Formula: `cited_daily_article_count / max(1, daily_article_count)`.
- How to read: Higher means broader use of the daily source set. `1.0` means
  every daily article was cited at least once.
- Examples:
  - 4 cited daily articles out of 8 daily articles -> `4 / 8 = 0.50`.
  - 3 cited daily articles out of 3 daily articles -> `3 / 3 = 1.00`.
  - 0 cited daily articles and 0 daily articles -> `0 / 1 = 0.00`.

## RAG Context Use

These metrics answer: did KB-backed strategies retrieve and cite KB evidence?

### `rag_source_article_count`

- Name: RAG source article count.
- Description: Number of knowledge-base source articles registered in the report
  source pool.
- Formula: `count(registry.rag_source_article_ids)`.
- How to read: Higher means more KB articles were made citeable. It is useful
  for understanding how much retrieved context was available.
- Examples:
  - RAG IDs `[kb1, kb2, kb3]` -> `rag_source_article_count = 3`.
  - RAG IDs `[]` -> `rag_source_article_count = 0`.
  - RAG IDs `[kb1]` -> `rag_source_article_count = 1`.

### `cited_rag_article_count`

- Name: cited RAG article count.
- Description: Number of valid cited sources whose article ID belongs to the RAG
  source set.
- Formula: count cited article IDs where `article_id in rag_source_article_ids`.
- How to read: Higher means the report cited more KB evidence. It is especially
  important for ReAct-style or KB-required strategies.
- Examples:
  - RAG IDs `{kb1, kb2}` and cited article IDs `[kb1, kb2]` -> `2`.
  - RAG IDs `{kb1, kb2}` and cited article IDs `[daily1, kb2]` -> `1`.
  - No cited RAG sources -> `0`.

### `cited_rag_article_rate`

- Name: cited RAG article rate.
- Description: Share of registered RAG source articles that were cited.
- Formula: `cited_rag_article_count / max(1, rag_source_article_count)`.
- How to read: Higher means more available KB sources were used in the final
  report. Very high values are good only if those KB sources are relevant.
- Examples:
  - 2 cited RAG articles out of 4 RAG sources -> `2 / 4 = 0.50`.
  - 3 cited RAG articles out of 3 RAG sources -> `3 / 3 = 1.00`.
  - 0 cited RAG articles and 0 RAG sources -> `0 / 1 = 0.00`.

### `retrieved_chunk_count`

- Name: retrieved chunk count.
- Description: Number of KB chunk IDs retrieved while building the report.
- Formula: `len(retrieved_chunk_ids)`.
- How to read: Contextual. More chunks means more retrieved context was
  available, but can also increase noise.
- Examples:
  - Retrieved chunk IDs `[c1, c2, c3]` -> `retrieved_chunk_count = 3`.
  - Retrieved chunk IDs `[]` -> `retrieved_chunk_count = 0`.
  - Two KB searches returning 5 chunks each -> `retrieved_chunk_count = 10`.

### `retrieved_to_cited_rate`

- Name: retrieved-to-cited rate.
- Description: Ratio of valid cited source articles to retrieved chunk IDs.
- Formula: `valid cited article count / retrieved_chunk_count`. If no chunks were
  retrieved, the value is `0.0`.
- How to read: Higher means retrieved context was converted into cited evidence.
  It is contextual because the numerator counts cited articles while the
  denominator counts chunks.
- Examples:
  - 4 valid cited articles and 8 retrieved chunks -> `4 / 8 = 0.50`.
  - 2 valid cited articles and 0 retrieved chunks -> `0.00`.
  - 6 valid cited articles and 3 retrieved chunks -> `6 / 3 = 2.00`.

### `kb_search_call_count`

- Name: KB search call count.
- Description: Number of recorded `search_knowledge_base` tool calls.
- Formula: count tool log entries where `tool_name == "search_knowledge_base"`.
- How to read: Contextual. For KB strategies, `0` usually means the strategy did
  not use its KB search tool.
- Examples:
  - Tool calls `[search, search, read_article]` -> `2`.
  - Tool calls `[read_article]` -> `0`.
  - Empty tool log -> `0`.

### `successful_kb_search_call_count`

- Name: successful KB search call count.
- Description: Number of KB search tool calls whose status is `ok`.
- Formula: count tool log entries where `tool_name == "search_knowledge_base"`
  and `status == "ok"`.
- How to read: Higher means more successful KB searches. For KB-required
  strategies, this must meet the required minimum.
- Examples:
  - Search statuses `[ok, error]` -> `1`.
  - Search statuses `[ok, ok, ok]` -> `3`.
  - No search calls -> `0`.

### `read_article_call_count`

- Name: read article call count.
- Description: Number of recorded `read_article` tool calls.
- Formula: count tool log entries where `tool_name == "read_article"`.
- How to read: Contextual. It is mainly relevant for `react-triage`, where the
  model can inspect full candidate articles.
- Examples:
  - Tool calls `[read_article, search]` -> `1`.
  - Tool calls `[read_article, read_article]` -> `2`.
  - Empty tool log -> `0`.

### `kb_requirement_satisfied`

- Name: KB requirement satisfied.
- Description: Whether a strategy met its required KB-search policy.
- Formula:
  - If no minimum KB search calls are required, return `true`.
  - Otherwise return whether `successful_kb_search_call_count >= minimum`.
- How to read: `true` is better. `false` means a KB-required strategy did not
  actually perform enough successful KB searches.
- Examples:
  - Simple strategy with no KB requirement -> `true`.
  - Required minimum `1`, successful searches `1` -> `true`.
  - Required minimum `1`, successful searches `0` -> `false`.

## Citation Density

These metrics answer: how citation-heavy is the report text?

### `report_line_count`

- Name: report line count.
- Description: Number of non-empty lines in the report text.
- Formula: count lines where `line.strip()` is not empty.
- How to read: Contextual. More lines often means a longer or more structured
  report.
- Examples:
  - `"# Report\n\nOne line"` -> non-empty lines `2`.
  - Empty report text -> `0`.
  - Three bullet lines and one heading -> `4`.

### `cited_line_count`

- Name: cited line count.
- Description: Number of non-empty report lines containing a source citation.
- Formula: count non-empty lines where citation regex matches.
- How to read: Higher means more lines are explicitly cited. It is useful with
  `cited_line_ratio`.
- Examples:
  - 5 non-empty lines, 4 with citations -> `cited_line_count = 4`.
  - 3 non-empty lines, 0 with citations -> `cited_line_count = 0`.
  - 1 non-empty line with two citations -> `cited_line_count = 1`.

### `cited_line_ratio`

- Name: cited line ratio.
- Description: Share of non-empty report lines that contain at least one source
  citation.
- Formula: `cited_line_count / max(1, report_line_count)`.
- How to read: Higher means more report lines are backed by citations. For this
  repo's report style, higher is usually better.
- Examples:
  - 4 cited lines out of 5 report lines -> `4 / 5 = 0.80`.
  - 0 cited lines out of 3 report lines -> `0 / 3 = 0.00`.
  - 0 cited lines and 0 report lines -> `0 / 1 = 0.00`.

## Report Shape

These metrics answer: how large and structured is the generated report?

### `report_word_count`

- Name: report word count.
- Description: Number of word-like tokens in the report text.
- Formula: count regex matches for `\b\w+\b`.
- How to read: Contextual. Higher means a longer report. Better depends on the
  expected report length and density.
- Examples:
  - `Hotel demand rises.` -> words `Hotel`, `demand`, `rises` -> `3`.
  - `# Daily Report` -> words `Daily`, `Report` -> `2`.
  - Empty report -> `0`.

### `section_count`

- Name: section count.
- Description: Number of Markdown heading lines in the report text.
- Formula: count lines matching `^#+\s+`.
- How to read: Contextual. More sections can mean better structure, but too many
  sections can fragment a short report.
- Examples:
  - `# Report` -> `section_count = 1`.
  - `# Report\n## Demand\n## Risks` -> `section_count = 3`.
  - No Markdown headings -> `0`.

## Source Spread

These metrics answer: does the report cite a balanced set of publications?

### `cited_source_entropy`

- Name: cited source entropy.
- Description: Shannon entropy of source names among valid cited sources.
- Formula: `-sum(p(source) * log2(p(source)))`, rounded to 4 decimals.
- How to read: Higher means cited evidence is spread across more sources. `0`
  means all cited sources come from one publication, or there are no valid cited
  sources.
- Examples:
  - Sources `[PUBLICO, PUBLICO]` -> entropy `0.0000`.
  - Sources `[PUBLICO, RTP]` -> `-(0.5 log2 0.5 + 0.5 log2 0.5) = 1.0000`.
  - Sources `[A, A, B, C]` -> entropy about `1.5000`.

### `cited_source_hhi`

- Name: cited source HHI.
- Description: Herfindahl-Hirschman concentration of source names among valid
  cited sources.
- Formula: `sum(p(source)^2)`, rounded to 4 decimals.
- How to read: Lower means a more diverse source mix. Higher means citations are
  concentrated in fewer publications.
- Examples:
  - Sources `[A, A]` -> `1.0^2 = 1.0000`.
  - Sources `[A, B]` -> `0.5^2 + 0.5^2 = 0.5000`.
  - Sources `[A, A, B, C]` -> `0.5^2 + 0.25^2 + 0.25^2 = 0.3750`.

### `top_cited_source_share`

- Name: top cited source share.
- Description: Share of valid cited sources belonging to the most common source
  name.
- Formula: `max(count by source) / valid cited source count`, rounded to 4
  decimals.
- How to read: Lower usually means less dependence on one publication. `1.0`
  means every valid cited source came from the same source name.
- Examples:
  - Sources `[A, A, A]` -> `3 / 3 = 1.0000`.
  - Sources `[A, A, B, C]` -> `2 / 4 = 0.5000`.
  - No valid cited sources -> `0.0000`.

## Operational Metrics

These metrics answer: how much model work and time did the strategy use?

### `llm_prompt_tokens`

- Name: LLM prompt tokens.
- Description: Total prompt/input tokens recorded across model calls for the
  strategy.
- Formula: sum `prompt_tokens` from each model call result.
- How to read: Lower is cheaper and usually faster, assuming quality is similar.
- Examples:
  - Calls with prompt tokens `[100, 50]` -> `150`.
  - One call with `0` recorded prompt tokens -> `0`.
  - Calls with `[10, 20, 30]` -> `60`.

### `llm_completion_tokens`

- Name: LLM completion tokens.
- Description: Total completion/output tokens recorded across model calls.
- Formula: sum `completion_tokens` from each model call result.
- How to read: Lower is cheaper and often more concise, assuming report quality
  is similar.
- Examples:
  - Calls with completion tokens `[40, 20]` -> `60`.
  - One call with `0` recorded completion tokens -> `0`.
  - Calls with `[5, 6, 50]` -> `61`.

### `llm_call_count`

- Name: LLM call count.
- Description: Number of model calls made during the strategy run.
- Formula: increment by `1` for each model call recorded with
  `record_model_usage`.
- How to read: Lower is cheaper and simpler, assuming quality is similar. ReAct
  strategies often need more calls than simple strategies.
- Examples:
  - One draft call -> `llm_call_count = 1`.
  - Two tool-loop calls plus final report call -> `3`.
  - No model calls recorded -> `0`.

### `runtime_seconds`

- Name: runtime seconds.
- Description: Wall-clock runtime recorded for the strategy.
- Formula: `strategy_end_time - strategy_start_time`.
- How to read: Lower is faster, assuming quality is similar.
- Examples:
  - Start `0.0`, end `12.5` -> `12.5`.
  - Start `100.0`, end `103.25` -> `3.25`.
  - Missing runtime metric -> `0.0`.

## Temporal Validity

These metrics answer: did the report use evidence from the correct time window?

### `cited_daily_window_article_count`

- Name: cited daily-window article count.
- Description: Number of cited source articles whose timestamp falls inside the
  report window.
- Formula: count cited source rows with temporal bucket `daily_window`.
- How to read: Higher means more cited evidence came from the intended daily
  window.
- Examples:
  - Cited buckets `[daily_window, past, future]` -> `1`.
  - Cited buckets `[daily_window, daily_window]` -> `2`.
  - No cited daily-window articles -> `0`.

### `cited_past_article_count`

- Name: cited past article count.
- Description: Number of cited source articles dated before the report window.
- Formula: count cited source rows with temporal bucket `past`.
- How to read: Contextual. Past evidence can be useful background, but a daily
  report should not rely only on old evidence.
- Examples:
  - Cited buckets `[past, daily_window]` -> `1`.
  - Cited buckets `[past, past, future]` -> `2`.
  - No cited past articles -> `0`.

### `cited_future_article_count`

- Name: cited future article count.
- Description: Number of cited source articles dated after the report window.
- Formula: count cited source rows with temporal bucket `future`.
- How to read: Lower is better. A future citation means the report used evidence
  that should not have been available at the report time.
- Examples:
  - Cited buckets `[daily_window, future]` -> `1`.
  - Cited buckets `[past, daily_window]` -> `0`.
  - Cited buckets `[future, future, unknown]` -> `2`.

### `cited_unknown_date_article_count`

- Name: cited unknown-date article count.
- Description: Number of cited source articles whose timestamp or report window
  could not be parsed.
- Formula: count cited source rows with temporal bucket `unknown`.
- How to read: Lower is better because unknown dates make temporal validity
  harder to audit.
- Examples:
  - Cited buckets `[unknown, daily_window]` -> `1`.
  - Cited buckets `[unknown, unknown]` -> `2`.
  - Cited buckets `[past, daily_window]` -> `0`.

### `cited_temporal_validity_rate`

- Name: cited temporal validity rate.
- Description: Share of cited known-date evidence that is not future evidence.
- Formula:
  - `known = daily_window + past + future`.
  - `valid = daily_window + past`.
  - `valid / known`. If `known` is `0`, the value is `1.0`.
- How to read: Higher is better. `1.0` means no known-date cited evidence comes
  from the future.
- Examples:
  - Cited counts daily `1`, past `1`, future `1` -> `(1 + 1) / 3 = 0.67`.
  - Cited counts daily `2`, past `0`, future `0` -> `2 / 2 = 1.00`.
  - Cited counts daily `0`, past `0`, future `0`, unknown `3` -> `1.00`.

### `source_daily_window_article_count`

- Name: source daily-window article count.
- Description: Number of all registered source-pool articles inside the report
  window.
- Formula: count all source rows with temporal bucket `daily_window`.
- How to read: Higher means more of the available source pool is daily-window
  evidence.
- Examples:
  - Source buckets `[daily_window, past, future]` -> `1`.
  - Source buckets `[daily_window, daily_window]` -> `2`.
  - Empty source pool -> `0`.

### `source_past_article_count`

- Name: source past article count.
- Description: Number of all registered source-pool articles before the report
  window.
- Formula: count all source rows with temporal bucket `past`.
- How to read: Contextual. Past source-pool articles can be useful background
  evidence.
- Examples:
  - Source buckets `[past, daily_window]` -> `1`.
  - Source buckets `[past, past, future]` -> `2`.
  - No past source-pool articles -> `0`.

### `source_future_article_count`

- Name: source future article count.
- Description: Number of all registered source-pool articles after the report
  window.
- Formula: count all source rows with temporal bucket `future`.
- How to read: Lower is better because future evidence should not be available
  to a report for an earlier date.
- Examples:
  - Source buckets `[future, daily_window]` -> `1`.
  - Source buckets `[past, daily_window]` -> `0`.
  - Source buckets `[future, future]` -> `2`.

### `source_unknown_date_article_count`

- Name: source unknown-date article count.
- Description: Number of all registered source-pool articles with unknown
  temporal bucket.
- Formula: count all source rows with temporal bucket `unknown`.
- How to read: Lower is better because source dates are needed for temporal
  auditing.
- Examples:
  - Source buckets `[unknown, past]` -> `1`.
  - Source buckets `[unknown, unknown]` -> `2`.
  - No unknown source-pool articles -> `0`.

### `source_temporal_validity_rate`

- Name: source temporal validity rate.
- Description: Share of all registered known-date source articles that are not
  future evidence.
- Formula:
  - `known = daily_window + past + future`.
  - `valid = daily_window + past`.
  - `valid / known`. If `known` is `0`, the value is `1.0`.
- How to read: Higher is better. It checks the whole source pool, not only cited
  sources.
- Examples:
  - Source counts daily `1`, past `1`, future `1` -> `(1 + 1) / 3 = 0.67`.
  - Source counts daily `3`, past `2`, future `0` -> `5 / 5 = 1.00`.
  - Only unknown-date sources -> `1.00`.

### `rag_daily_window_article_count`

- Name: RAG daily-window article count.
- Description: Number of registered RAG source articles inside the report window.
- Formula: count source rows whose `article_id` is in `rag_source_article_ids`
  and whose temporal bucket is `daily_window`.
- How to read: Higher means retrieved KB context included more report-window
  evidence.
- Examples:
  - RAG buckets `[daily_window, past]` -> `1`.
  - RAG buckets `[daily_window, daily_window]` -> `2`.
  - No RAG sources -> `0`.

### `rag_past_article_count`

- Name: RAG past article count.
- Description: Number of registered RAG source articles before the report
  window.
- Formula: count RAG source rows with temporal bucket `past`.
- How to read: Contextual. Past RAG evidence can add background, but should not
  replace fresh daily evidence.
- Examples:
  - RAG buckets `[past, daily_window]` -> `1`.
  - RAG buckets `[past, past]` -> `2`.
  - No past RAG articles -> `0`.

### `rag_future_article_count`

- Name: RAG future article count.
- Description: Number of registered RAG source articles after the report window.
- Formula: count RAG source rows with temporal bucket `future`.
- How to read: Lower is better. A value above `0` means retrieved KB context
  included future evidence.
- Examples:
  - RAG buckets `[future, past]` -> `1`.
  - RAG buckets `[daily_window, past]` -> `0`.
  - RAG buckets `[future, future, unknown]` -> `2`.

### `rag_unknown_date_article_count`

- Name: RAG unknown-date article count.
- Description: Number of registered RAG source articles with unknown temporal
  bucket.
- Formula: count RAG source rows with temporal bucket `unknown`.
- How to read: Lower is better because unknown KB source dates make temporal
  auditing weaker.
- Examples:
  - RAG buckets `[unknown, past]` -> `1`.
  - RAG buckets `[unknown, unknown]` -> `2`.
  - No unknown RAG articles -> `0`.

### `rag_temporal_validity_rate`

- Name: RAG temporal validity rate.
- Description: Share of known-date RAG source articles that are not future
  evidence.
- Formula:
  - `known = daily_window + past + future`.
  - `valid = daily_window + past`.
  - `valid / known`. If `known` is `0`, the value is `1.0`.
- How to read: Higher is better. It checks whether retrieved KB context respects
  the report time boundary.
- Examples:
  - RAG counts daily `1`, past `1`, future `1` -> `(1 + 1) / 3 = 0.67`.
  - RAG counts daily `0`, past `4`, future `0` -> `4 / 4 = 1.00`.
  - No known-date RAG sources -> `1.00`.

## Run Summary Metrics

These metrics are written in `evaluation.json` under `summary`. They summarize
all strategy rows in a report batch.

### `strategy_count`

- Name: strategy count.
- Description: Number of strategy rows in the batch evaluation.
- Formula: `len(evaluation rows)`.
- How to read: Contextual. It tells you how many strategies were evaluated.
- Examples:
  - Strategies `[simple, react-basic]` -> `2`.
  - Six configured strategies -> `6`.
  - Empty run manifest strategy list -> `0`.

### `error_count`

- Name: error count.
- Description: Number of strategy rows whose status is not `ok`.
- Formula: count rows where `status != "ok"`.
- How to read: Lower is better. It shows how many strategies failed or produced
  non-ok results.
- Examples:
  - Statuses `[ok, ok, error]` -> `1`.
  - Statuses `[ok, ok]` -> `0`.
  - Statuses `[error, missing, ok]` -> `2`.

### `future_citation_count`

- Name: future citation count.
- Description: Total number of cited future articles across all strategy rows.
- Formula: sum `cited_future_article_count` across rows.
- How to read: Lower is better. It measures temporal leakage across the whole
  batch.
- Examples:
  - Row future counts `[1, 0, 2]` -> `3`.
  - Row future counts `[0, 0]` -> `0`.
  - Missing row values are treated as `0`.

### `kb_requirement_failure_count`

- Name: KB requirement failure count.
- Description: Number of successful strategy rows that did not satisfy their KB
  search requirement.
- Formula: count rows where `status == "ok"` and `kb_requirement_satisfied` is
  false-like (`false`, `0`, or `no`).
- How to read: Lower is better. It identifies reports that completed but did not
  actually use required KB search.
- Examples:
  - Rows `[ok false, ok true, error false]` -> `1`.
  - Rows `[ok true, ok true]` -> `0`.
  - Rows `[error false]` -> `0` because errored rows are not counted here.

### `total_prompt_tokens`

- Name: total prompt tokens.
- Description: Sum of prompt tokens across all evaluated strategies.
- Formula: sum row `llm_prompt_tokens`, converting missing or malformed values to
  `0`.
- How to read: Lower is cheaper, assuming report quality is comparable.
- Examples:
  - Prompt token rows `[100, 200]` -> `300`.
  - Prompt token rows `[100, missing]` -> `100`.
  - No rows -> `0`.

### `total_completion_tokens`

- Name: total completion tokens.
- Description: Sum of completion tokens across all evaluated strategies.
- Formula: sum row `llm_completion_tokens`, converting missing or malformed
  values to `0`.
- How to read: Lower is cheaper, assuming report quality is comparable.
- Examples:
  - Completion token rows `[20, 30]` -> `50`.
  - Completion token rows `[20, missing]` -> `20`.
  - No rows -> `0`.

### `total_runtime_seconds`

- Name: total runtime seconds.
- Description: Sum of runtime seconds across all evaluated strategies.
- Formula: sum row `runtime_seconds`, skipping values that cannot be parsed, then
  round to 4 decimals.
- How to read: Lower is faster for the full batch, assuming report quality is
  comparable.
- Examples:
  - Runtime rows `[1.25, 2.75]` -> `4.0`.
  - Runtime rows `[1.11111, 2.22222]` -> `3.3333`.
  - Runtime rows `[missing, 2.0]` -> `2.0`.

## Evaluation Row Fields

The CSV and JSON strategy rows also include these identifying fields. They are
not quality scores, but they help trace each metric row back to the artifact that
produced it.

### `strategy`

- Name: strategy.
- Description: Strategy label from the batch run, such as `simple` or
  `react-basic`.
- Formula: copied from the strategy result in `run_manifest.json`.
- How to read: Use it to compare rows by strategy.
- Examples:
  - Simple row -> `strategy = simple`.
  - ReAct basic row -> `strategy = react-basic`.
  - Missing strategy value -> empty string.

### `status`

- Name: status.
- Description: Strategy result status.
- Formula: copied from the strategy result in `run_manifest.json`.
- How to read: `ok` means the row has normal artifacts. Other values indicate an
  error or incomplete result.
- Examples:
  - Successful strategy -> `status = ok`.
  - Failed strategy -> `status = error`.
  - Missing manifest path can still leave a row with its copied status.

### `error`

- Name: error.
- Description: Error text recorded for a failed strategy.
- Formula: copied from the strategy result in `run_manifest.json`.
- How to read: Empty is better. Non-empty text explains why a strategy failed.
- Examples:
  - Successful strategy -> `error = ""`.
  - KB unavailable -> `error = "KB unavailable"`.
  - Missing API key -> `error = "OPENAI_API_KEY is not set"`.

### `context_strategy`

- Name: context strategy.
- Description: Context-construction strategy recorded in the strategy manifest.
- Formula: manifest `context_strategy`.
- How to read: Use it to group rows by the actual report-generation method.
- Examples:
  - Simple manifest -> `context_strategy = simple`.
  - Hybrid manifest -> `context_strategy = react-hybrid`.
  - Missing manifest -> empty string.

### `knowledge_base_recipe`

- Name: knowledge base recipe.
- Description: KB recipe used by the report strategy.
- Formula: manifest `knowledge_base_recipe`, with older run-level fallbacks in
  the batch metadata.
- How to read: Use it to compare reports generated against different KB builds.
- Examples:
  - Recursive KB -> `news_recursive_2000_overlap_3large`.
  - Simple non-KB run -> empty string.
  - Missing manifest -> empty string.

### `report_path`

- Name: report path.
- Description: Path to the Markdown report artifact for the strategy.
- Formula: copied from the strategy result in `run_manifest.json`.
- How to read: Use it to open the report behind a row.
- Examples:
  - Simple report -> `shared_data/reports/run/simple.md`.
  - Failed strategy -> empty string.
  - Absolute report path -> preserved as written.

### `manifest_path`

- Name: manifest path.
- Description: Path to the per-strategy manifest JSON.
- Formula: copied from the strategy result in `run_manifest.json`.
- How to read: Use it to inspect the full metrics, source registry, model usage,
  and tool log.
- Examples:
  - Simple manifest -> `shared_data/reports/run/simple_manifest.json`.
  - Failed strategy -> empty string.
  - Absolute manifest path -> preserved as written.

## Metric Families

`evaluation.json` groups metrics into these families:

| Family | Metrics |
| --- | --- |
| `citation_behavior` | `citation_count`, `distinct_cited_sources`, `citation_reference_validity_rate`, `citation_out_of_range_count`, `citation_nonstandard_count` |
| `daily_evidence_use` | `daily_article_count`, `cited_daily_article_count`, `cited_daily_article_rate` |
| `citation_density` | `report_line_count`, `cited_line_count`, `cited_line_ratio` |
| `rag_context_use` | `retrieved_chunk_count`, `rag_source_article_count`, `cited_rag_article_count`, `cited_rag_article_rate`, `kb_search_call_count`, `successful_kb_search_call_count`, `read_article_call_count`, `kb_requirement_satisfied` |
| `report_shape` | `report_word_count`, `section_count` |
| `source_spread` | `cited_source_entropy`, `cited_source_hhi`, `top_cited_source_share` |
| `operational` | `llm_prompt_tokens`, `llm_completion_tokens`, `llm_call_count`, `runtime_seconds` |
| `temporal_validity` | `cited_future_article_count`, `cited_past_article_count`, `cited_daily_window_article_count`, `cited_unknown_date_article_count`, `cited_temporal_validity_rate`, `source_future_article_count`, `rag_future_article_count` |
