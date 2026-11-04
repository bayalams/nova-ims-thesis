# nova-ims-thesis
# Automated Tourism Market Intelligence

  This repository contains the software developed for a master’s thesis at NOVA Information Management School.

  ## Project overview

  Tourism organizations need to monitor large volumes of information from news outlets, travel publications, and other online sources. Reading and organizing this material manually is time-consuming, particularly when information is
  published continuously across many sources and countries.

  This project explores how an automated pipeline can support tourism market intelligence. The system collects news articles, extracts and cleans their content, organizes the information in searchable knowledge bases, and uses large
  language models to produce evidence-based tourism intelligence reports.

  The objective is not only to generate reports. The project also investigates how different technical decisions affect the quality and efficiency of the final output. These decisions include:

  - how articles are divided into smaller text chunks;
  - which embedding model is used to represent the text;
  - how information is stored and retrieved;
  - how much historical context is provided to the language model;
  - how the model searches for additional evidence;
  - how retrieved information is converted into a cited report.

  The system therefore functions as both a working reporting pipeline and an experimental environment for comparing different knowledge-base and report-generation strategies.

  ## How the system works

  The complete workflow is:

 
  RSS feeds
    → indexed article links
    → downloaded article pages
    → cleaned and structured articles
    → vector knowledge bases
    → relevant information retrieval
    → tourism intelligence reports
    → evaluation and comparison

  ### 1. News collection

  The collector monitors RSS feeds from tourism publications and general news organizations.

  For each source, the system:

  1. reads the RSS feed;
  2. records the available article links;
  3. downloads article pages;
  4. stores the original article information;
  5. extracts the useful article text;
  6. removes source-specific page elements and irrelevant content.

  The original and cleaned versions are stored separately. This preserves the source material while allowing the cleaning process to be inspected and improved.

  Repeated collection runs skip articles that have already been processed unless overwriting is explicitly requested.

  ### 2. Corpus inspection and quality control

  Cleaned articles can be inspected through a local browser application.

  The corpus inspector creates a searchable local index that helps identify:

  - missing or unusually short article text;
  - possible extraction problems;
  - duplicated or incomplete content;
  - differences between raw and cleaned articles;
  - the distribution of articles across sources and dates.

  This step helps verify the quality of the corpus before it is used in the knowledge-base and reporting experiments.

  ### 3. Knowledge-base construction

  The cleaned articles are transformed into searchable vector knowledge bases.

  Several knowledge-base recipes are included to compare different configurations:

  - complete articles without chunking;
  - fixed-size chunks with overlap;
  - recursively generated chunks;
  - different chunk sizes;
  - different OpenAI embedding models.

  Each recipe produces a separate SQLite database. Article metadata, chunks, and embedding vectors are stored together, while SQLite Vec1 provides vector similarity search.

  The knowledge bases are incremental. Articles that have already been processed are skipped when their content has not changed. Modified articles can be rebuilt without recreating the entire database.

  ### 4. Knowledge-base evaluation

  The project evaluates whether each knowledge-base configuration preserves the source material and retrieves useful information.

  The evaluation includes metrics related to:

  - article and vector coverage;
  - chunk size and chunks per article;
  - missing metadata;
  - embedding failures;
  - database size;
  - build time;
  - article reconstruction;
  - paragraph and sentence boundary preservation;
  - duplicated or overlapping chunks;
  - retrieval quality;
  - retrieval diversity;
  - same-article result crowding;
  - named-entity preservation.

  These metrics make it possible to study the trade-offs between retrieval quality, storage requirements, processing time, and embedding cost.

  ### 5. Report generation

  The reporting pipeline generates tourism intelligence reports for a selected date or time window.

  The system first identifies the articles available for the report period. Depending on the selected strategy, it can use only those daily articles or search a knowledge base for additional historical context.

  The project includes several context-construction strategies:

  - simple — generates the report from the selected daily articles;
  - react-basic — allows the model to perform knowledge-base searches;
  - react-map-reduce — processes evidence in smaller groups before combining it;
  - react-triage — prioritizes articles before constructing the report;
  - react-hybrid — combines multiple context-selection techniques;
  - react-progressive — builds the report through progressive evidence gathering.

  The knowledge-base strategies use time boundaries when retrieving articles. This prevents a historical report from intentionally using information that was indexed after the report date.

  Reports contain numbered source references so that claims can be traced back to the articles used as evidence.

  ### 6. Report evaluation

  Multiple report strategies can be run as a batch and compared under the same conditions.

  The evaluation examines aspects such as:

  - number and validity of citations;
  - proportion of daily articles cited;
  - use of retrieved historical evidence;
  - source diversity;
  - information coverage;
  - groundedness in the available sources;
  - retrieval activity;
  - model token usage;
  - execution time;
  - estimated generation cost.

  The project can create CSV and JSON evaluation files, comparison plots, and a local HTML viewer for inspecting reports and their supporting evidence side by side.

  ## Project structure

  collector/
    RSS indexing, article downloading, cleaning, and quality checks

  knowledge_bases/
    chunking, embeddings, SQLite storage, vector retrieval, and evaluation

  reporting/
    article selection, context construction, prompts, report generation,
    citations, and report evaluation

  explorer/
    analysis scripts, visualizations, notebooks, and local web applications

  tests/
    automated tests for the collection, knowledge-base, reporting,
    and exploration components

  shared_data/
    local corpus, databases, reports, and analysis outputs
    (not included in the public repository)

  ## Requirements

  The project requires:

  - Python 3.12;
  - uv (https://docs.astral.sh/uv/) for environment and dependency management;
  - a ScrapingBee API key for downloading article pages;
  - an OpenAI API key for embeddings and report generation.

  Install the dependencies from the repository root:

  uv sync

  Create a local .env file based on .env.example:

  SCRAPINGBEE_API_KEY=your_key_here
  OPENAI_API_KEY=your_key_here

  The .env file is ignored by Git and must not be committed.

  ## Main commands

  View the available commands:

  uv run collect --help
  uv run build-kb --help
  uv run report --help
  uv run explore --help

  Run the automated tests:

  uv run test

  ### Collect and clean articles

  uv run collect index-rss all
  uv run --env-file .env collect fetch-articles all
  uv run collect clean-articles all

  ### Build a knowledge base

  uv run build-kb setup-vec1
  uv run --env-file .env build-kb run news_recursive_2000_overlap_3large

  ### Evaluate knowledge bases

  uv run --env-file .env build-kb evaluate all --table

  ### Generate a report

  uv run --env-file .env report run \
    daily_tourism_intelligence \
    --context-strategy simple \
    --article-date YYYY-MM-DD \
    --yes

  ### Compare report-generation strategies

  uv run --env-file .env report run-batch \
    daily_tourism_intelligence \
    --article-date YYYY-MM-DD \
    --knowledge-base-recipe news_recursive_2000_overlap_3large \
    --run-name strategy_comparison \
    --yes

  ## Data privacy

  The collected article corpus is not included in this public repository because it contains third-party news content.

  The following generated artifacts are also excluded:

  - raw and cleaned articles;
  - generated knowledge-base databases;
  - embedding vectors;
  - generated reports;
  - local indexes;
  - evaluation outputs;
  - API credentials.

  The repository contains only the source code, configuration recipes, prompts, tests, and documentation needed to understand and reproduce the pipeline with independently collected data.
