#!/usr/bin/env bash

# Run the full news collector pipeline for every enabled source.
#
# This script intentionally keeps the steps explicit and boring:
# 1. Index RSS links
# 2. Fetch missing raw articles
# 3. Clean missing raw articles
# 4. Write a quality report
#
# Existing files are skipped by default by the collector commands. This means
# repeated runs should only process new work unless you add overwrite flags.

set -e

echo "[INFO] Starting full news collector pipeline"

# Step 1: Move to the repository root so every relative path works.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Step 2: Choose simple defaults.
WORKERS=8
SAMPLE_PER_SOURCE=10
RUN_TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
QUALITY_REPORT_DIR="shared_data/quality_reports/news_cleaning/${RUN_TIMESTAMP}"

echo "[INFO] Repository root: ${REPO_ROOT}"
echo "[INFO] Workers: ${WORKERS}"
echo "[INFO] Quality report folder: ${QUALITY_REPORT_DIR}"

# Step 3: Index RSS links for all enabled sources.
echo "[INFO] Step 1/4: Indexing RSS links for all sources"
uv run collect index-rss all --workers "${WORKERS}"

# Step 4: Fetch articles for any indexed links that do not have raw article JSON yet.
# The fetcher needs SCRAPINGBEE_API_KEY. This loads it from .env.
echo "[INFO] Step 2/4: Fetching missing raw articles for all sources"
uv run --env-file .env collect fetch-articles all --workers "${WORKERS}"

# Step 5: Clean raw articles that do not have clean article JSON yet.
echo "[INFO] Step 3/4: Cleaning missing articles for all sources"
uv run collect clean-articles all --workers "${WORKERS}"

# Step 6: Produce passive quality reports for human review.
echo "[INFO] Step 4/4: Writing cleaning quality report"
uv run collect quality-cleaning all \
  --sample-per-source "${SAMPLE_PER_SOURCE}" \
  --sample-mode suspicious \
  --output-dir "${QUALITY_REPORT_DIR}"

echo "[INFO] Pipeline complete"
echo "[INFO] Open the HTML report:"
echo "       ${QUALITY_REPORT_DIR}/report.html"
