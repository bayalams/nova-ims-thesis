"""
Embedding-prototype selector for daily tourism report candidates.
"""

import math
import re
import time

from knowledge_bases.embedding.openai_embeddings import create_embedding_batch
from knowledge_bases.embedding.openai_embeddings import estimate_input_tokens
from reporting.context.daily_articles import get_article_id
from reporting.context.daily_articles import parse_article_datetime


SELECTOR_METHOD = "embedding_prototypes_v2"
SELECTOR_TEXT_MAX_CHARS = 4000
DEFAULT_SELECTOR_MODEL = "text-embedding-3-small"
DEFAULT_POSITIVE_THRESHOLD = 0.28
DEFAULT_MARGIN_THRESHOLD = 0.03
SELECTOR_EMBEDDING_MAX_BATCH_TOKENS = 50000
SELECTOR_EMBEDDING_DELAY_SECONDS = 0.0
SELECTOR_EMBEDDING_MIN_RETRY_SECONDS = 120.0
SELECTOR_EMBEDDING_MAX_RETRIES = 3
SELECTOR_EMBEDDING_MAX_BACKOFF_SECONDS = 600.0


POSITIVE_PROTOTYPES = [
    {
        "id": "tourism_demand",
        "label": "Tourism demand and visitor flows",
        "polarity": "positive",
        "text": (
            "Tourism demand, tourist arrivals, visitors, overnight stays, "
            "travel spending, source markets, destination demand, and visitor flows."
        ),
    },
    {
        "id": "hotel_accommodation",
        "label": "Hotels and accommodation",
        "polarity": "positive",
        "text": (
            "Hotel occupancy, accommodation, hospitality businesses, guest nights, "
            "resorts, lodging demand, average daily rates, and tourism revenue."
        ),
    },
    {
        "id": "aviation_connectivity",
        "label": "Aviation and connectivity",
        "polarity": "positive",
        "text": (
            "Airline routes, airport operations, flights, aviation capacity, "
            "route launches, cancellations, travel connectivity, and transport disruption."
        ),
    },
    {
        "id": "cruise_passenger_travel",
        "label": "Cruise and passenger travel",
        "polarity": "positive",
        "text": (
            "Cruise ships, cruise passengers, ports, passenger travel, travel health "
            "incidents on ships, and itinerary disruption affecting tourists."
        ),
    },
    {
        "id": "destination_image_visitor_safety",
        "label": "Destination image and visitor safety",
        "polarity": "positive",
        "text": (
            "Destination image, tourist safety, visitor confidence, travel advisories, "
            "security incidents affecting travelers, and crisis impact on destination appeal."
        ),
    },
    {
        "id": "competitor_source_market",
        "label": "Competitor and source markets",
        "polarity": "positive",
        "text": (
            "Competitor destinations, source-market economics, exchange rates, "
            "consumer sentiment, travel budgets, and market conditions affecting outbound tourism."
        ),
    },
    {
        "id": "mobility_regulation",
        "label": "Mobility and travel regulation",
        "polarity": "positive",
        "text": (
            "Visa rules, border policy, travel regulation, mobility, strikes, "
            "infrastructure disruption, and access constraints affecting travelers."
        ),
    },
    {
        "id": "events_culture_tourism",
        "label": "Events and cultural tourism",
        "polarity": "positive",
        "text": (
            "Events, festivals, cultural tourism, museums, heritage attractions, "
            "concerts and sports events when they drive visitor demand for a destination."
        ),
    },
]


NEGATIVE_PROTOTYPES = [
    {
        "id": "generic_crime_court",
        "label": "Generic crime or court story",
        "polarity": "negative",
        "text": (
            "Crime, court case, trial, police investigation, corruption allegation, "
            "child exploitation, sexual abuse, or legal scandal with no travel or visitor impact."
        ),
    },
    {
        "id": "generic_online_child_safety",
        "label": "Generic online child safety or platform regulation",
        "polarity": "negative",
        "text": (
            "Online child safety, social media abuse, AI-generated illegal content, "
            "platform moderation, digital services regulation, and technology policy with no tourism link."
        ),
    },
    {
        "id": "generic_health",
        "label": "Generic medical or health story",
        "polarity": "negative",
        "text": (
            "Generic medical research, disease risk, obesity, infections, clinical studies, "
            "hospitals, and public health stories with no travel or tourism effect."
        ),
    },
    {
        "id": "generic_politics",
        "label": "Generic politics",
        "polarity": "negative",
        "text": (
            "General political dispute, parliamentary debate, party conflict, election tactic, "
            "or domestic policy story with no travel, mobility, aviation, or tourism implication."
        ),
    },
    {
        "id": "generic_sport",
        "label": "Generic sports result",
        "polarity": "negative",
        "text": (
            "Generic sports match result, player injury, football score, transfer rumor, "
            "or team news with no destination or visitor-demand relevance."
        ),
    },
    {
        "id": "celebrity_culture",
        "label": "Celebrity or entertainment",
        "polarity": "negative",
        "text": (
            "Celebrity gossip, entertainment controversy, film review, music industry story, "
            "royal family scandal, or cultural commentary with no visitor-demand relevance."
        ),
    },
    {
        "id": "generic_business_economy",
        "label": "Generic business or economy",
        "polarity": "negative",
        "text": (
            "Generic business, housing market, stock market, company earnings, inflation, "
            "or economic policy story with no travel, tourism, hospitality, or aviation link."
        ),
    },
]


def prototype_definitions():
    """
    Return the fixed selector prototypes.
    """
    prototypes = []

    for item in POSITIVE_PROTOTYPES:
        prototypes.append(dict(item))

    for item in NEGATIVE_PROTOTYPES:
        prototypes.append(dict(item))

    return prototypes


def normalize_whitespace(value):
    """
    Collapse repeated whitespace in one string.
    """
    return re.sub(r"\s+", " ", str(value or "")).strip()


def article_selector_text(article, max_chars=SELECTOR_TEXT_MAX_CHARS):
    """
    Build the text embedded for candidate selection.
    """
    metadata = article.get("metadata", {}) or {}
    tags = metadata.get("tags", "") or ""
    if isinstance(tags, list):
        tags_text = " ".join(str(item) for item in tags)
    else:
        tags_text = str(tags)

    pieces = [
        metadata.get("title", ""),
        metadata.get("source", ""),
        tags_text,
        metadata.get("summary", ""),
        article.get("text", ""),
        article.get("clean_text", ""),
        article.get("content", ""),
    ]
    text = normalize_whitespace("\n".join(str(piece or "") for piece in pieces if piece))
    return text[:max_chars]


def vector_norm(vector):
    """
    Return the Euclidean norm of one vector.
    """
    total = 0.0
    for value in vector:
        total = total + float(value) * float(value)

    return math.sqrt(total)


def cosine_similarity(left, right):
    """
    Return cosine similarity for two same-length vectors.
    """
    if not left or not right:
        return 0.0

    if len(left) != len(right):
        return 0.0

    left_norm = vector_norm(left)
    right_norm = vector_norm(right)
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0

    total = 0.0
    for index, left_value in enumerate(left):
        total = total + float(left_value) * float(right[index])

    return total / (left_norm * right_norm)


def best_similarity(article_embedding, prototype_embeddings, polarity):
    """
    Find the closest prototype for one polarity.
    """
    best_score = -1.0
    best_prototype = None

    for prototype in prototype_embeddings:
        if prototype.get("polarity") != polarity:
            continue

        similarity = cosine_similarity(article_embedding, prototype.get("embedding", []))
        if similarity > best_score:
            best_score = similarity
            best_prototype = prototype

    if best_score < 0.0:
        best_score = 0.0

    return best_score, best_prototype


def score_article_embedding(
    article_embedding,
    prototype_embeddings,
    positive_threshold=DEFAULT_POSITIVE_THRESHOLD,
    margin_threshold=DEFAULT_MARGIN_THRESHOLD,
):
    """
    Score one article embedding against positive and negative prototypes.
    """
    positive_similarity, positive_prototype = best_similarity(
        article_embedding,
        prototype_embeddings,
        "positive",
    )
    negative_similarity, negative_prototype = best_similarity(
        article_embedding,
        prototype_embeddings,
        "negative",
    )
    margin = positive_similarity - negative_similarity
    is_selected = positive_similarity >= positive_threshold and margin >= margin_threshold

    positive_label = "unknown"
    positive_id = ""
    if positive_prototype:
        positive_label = positive_prototype.get("label", "unknown")
        positive_id = positive_prototype.get("id", "")

    negative_label = "unknown"
    negative_id = ""
    if negative_prototype:
        negative_label = negative_prototype.get("label", "unknown")
        negative_id = negative_prototype.get("id", "")

    reason = (
        f"positive={positive_label} similarity={positive_similarity:.4f}; "
        f"negative={negative_label} similarity={negative_similarity:.4f}; "
        f"margin={margin:.4f}"
    )

    return {
        "score": margin,
        "margin": margin,
        "is_selected": is_selected,
        "reason": reason,
        "positive_similarity": positive_similarity,
        "negative_similarity": negative_similarity,
        "positive_prototype_id": positive_id,
        "negative_prototype_id": negative_id,
    }


def article_sort_timestamp(article):
    """
    Return a numeric timestamp for sorting candidate articles.
    """
    parsed = parse_article_datetime(article)
    if parsed is None:
        return 0.0

    return parsed.timestamp()


def make_excluded_example(article, score):
    """
    Build a compact manifest example for one excluded article.
    """
    metadata = article.get("metadata", {}) or {}
    return {
        "article_id": get_article_id(article),
        "title": metadata.get("title", "Untitled") or "Untitled",
        "source": metadata.get("source", "Unknown") or "Unknown",
        "score": score.get("score", 0.0),
        "reason": score.get("reason", ""),
    }


def select_articles_from_scores(articles, score_by_article_id, candidate_limit=None):
    """
    Keep selected articles, sort by score, and return a manifest summary.
    """
    selected_items = []
    excluded_items = []

    for article in articles:
        article_id = get_article_id(article)
        score = score_by_article_id.get(article_id, {
            "is_selected": False,
            "score": 0.0,
            "margin": 0.0,
            "reason": "missing selector score",
        })
        item = {
            "article": article,
            "article_id": article_id,
            "score": score,
        }

        if score.get("is_selected"):
            selected_items.append(item)
        else:
            excluded_items.append(item)

    selected_items.sort(
        key=lambda item: (
            -float(item["score"].get("score", 0.0)),
            -article_sort_timestamp(item["article"]),
            item["article_id"],
        )
    )

    if candidate_limit is not None:
        selected_items = selected_items[:candidate_limit]

    kept_article_ids = set()
    selected_articles = []
    for item in selected_items:
        kept_article_ids.add(item["article_id"])
        selected_articles.append(item["article"])

    for article in articles:
        article_id = get_article_id(article)
        if article_id in kept_article_ids:
            continue
        score = score_by_article_id.get(article_id, {"reason": "not selected", "score": 0.0})
        excluded_items.append({
            "article": article,
            "article_id": article_id,
            "score": score,
        })

    excluded_examples = []
    seen_excluded_ids = set()
    for item in excluded_items:
        article_id = item["article_id"]
        if article_id in seen_excluded_ids:
            continue
        seen_excluded_ids.add(article_id)
        if len(excluded_examples) >= 10:
            break
        excluded_examples.append(make_excluded_example(item["article"], item["score"]))

    selection = {
        "method": SELECTOR_METHOD,
        "raw_count": len(articles),
        "kept_count": len(selected_articles),
        "excluded_count": max(0, len(articles) - len(selected_articles)),
        "candidate_limit": candidate_limit,
        "positive_threshold": DEFAULT_POSITIVE_THRESHOLD,
        "margin_threshold": DEFAULT_MARGIN_THRESHOLD,
        "excluded_examples": excluded_examples,
    }

    return {
        "articles": selected_articles,
        "selection": selection,
    }


def build_prototype_embeddings(client, model_name):
    """
    Embed the fixed selector prototypes.
    """
    prototypes = prototype_definitions()
    texts = []

    for prototype in prototypes:
        texts.append(prototype["text"])

    embedding_result = create_selector_embedding_batch_with_backoff(
        client,
        texts,
        model_name,
        "prototype",
    )
    vectors = embedding_result["vectors"]

    prototype_embeddings = []
    for index, prototype in enumerate(prototypes):
        record = dict(prototype)
        record["embedding"] = vectors[index]
        prototype_embeddings.append(record)

    return prototype_embeddings


def split_embedding_records(records, max_batch_tokens):
    """
    Split embedding records into batches under a safe estimated token total.
    """
    batches = []
    current_batch = []
    current_tokens = 0

    for record in records:
        text = record.get("text", "")
        estimated_tokens = estimate_input_tokens(text)
        if estimated_tokens < 1:
            estimated_tokens = 1

        if current_batch and current_tokens + estimated_tokens > max_batch_tokens:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(record)
        current_tokens = current_tokens + estimated_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


def selector_error_is_rate_limit(error):
    """
    Return True when one selector embedding error looks like a rate limit.
    """
    error_text = str(error).lower()
    error_name = error.__class__.__name__.lower()

    if "ratelimit" in error_name:
        return True

    if "rate limit" in error_text:
        return True

    if "429" in error_text:
        return True

    return False


def extract_selector_retry_seconds(error):
    """
    Extract a suggested retry delay from one rate-limit error message.
    """
    error_text = str(error)

    match = re.search(r"try again in ([0-9.]+)s", error_text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))

    match = re.search(r"retry after ([0-9.]+) seconds", error_text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))

    return 5.0


def create_selector_embedding_batch_with_backoff(
    client,
    texts,
    model_name,
    batch_number,
    max_retries=SELECTOR_EMBEDDING_MAX_RETRIES,
):
    """
    Create one selector embedding batch with simple rate-limit backoff.
    """
    attempt = 1

    while True:
        try:
            return create_embedding_batch(client, texts, model_name)
        except Exception as error:
            if not selector_error_is_rate_limit(error):
                raise

            if attempt > max_retries:
                raise ValueError(
                    f"Selector embedding batch {batch_number} kept failing after {max_retries} retries"
                ) from error

            suggested_seconds = extract_selector_retry_seconds(error)
            wait_seconds = suggested_seconds + 1.0
            if wait_seconds < SELECTOR_EMBEDDING_MIN_RETRY_SECONDS:
                wait_seconds = SELECTOR_EMBEDDING_MIN_RETRY_SECONDS
            wait_seconds = min(wait_seconds, SELECTOR_EMBEDDING_MAX_BACKOFF_SECONDS)
            print(
                f"[WARNING] Selector embedding rate limit on batch {batch_number}. "
                f"Waiting {wait_seconds:.1f}s before retry {attempt}/{max_retries}"
            )
            time.sleep(wait_seconds)
            attempt = attempt + 1


def build_article_embeddings(
    client,
    articles,
    model_name,
    max_batch_tokens=SELECTOR_EMBEDDING_MAX_BATCH_TOKENS,
):
    """
    Embed the selector text for each article.
    """
    records = []

    for article in articles:
        records.append({
            "article_id": get_article_id(article),
            "text": article_selector_text(article),
        })

    batches = split_embedding_records(records, max_batch_tokens)

    article_embeddings = {}
    for batch_number, batch in enumerate(batches, start=1):
        texts = []
        for record in batch:
            texts.append(record["text"])

        embedding_result = create_selector_embedding_batch_with_backoff(
            client,
            texts,
            model_name,
            batch_number,
        )
        vectors = embedding_result["vectors"]

        for index, record in enumerate(batch):
            article_embeddings[record["article_id"]] = vectors[index]

        if SELECTOR_EMBEDDING_DELAY_SECONDS > 0 and batch_number < len(batches):
            print(
                f"[INFO] Waiting {SELECTOR_EMBEDDING_DELAY_SECONDS:.1f}s "
                f"before selector embedding batch {batch_number + 1}"
            )
            time.sleep(SELECTOR_EMBEDDING_DELAY_SECONDS)

    return article_embeddings


def select_report_candidates(
    articles,
    client,
    model_name=DEFAULT_SELECTOR_MODEL,
    candidate_limit=None,
    positive_threshold=DEFAULT_POSITIVE_THRESHOLD,
    margin_threshold=DEFAULT_MARGIN_THRESHOLD,
):
    """
    Select tourism-relevant daily articles with embedding prototypes.
    """
    print(f"[INFO] Candidate selector: {SELECTOR_METHOD}")
    selector_label = model_name
    if isinstance(model_name, dict):
        selector_label = model_name.get("embedding_model", "")

    print(f"      Selector model: {selector_label}")
    print(f"      Raw daily articles: {len(articles)}")

    if not articles:
        return {
            "articles": [],
            "selection": {
                "method": SELECTOR_METHOD,
                "raw_count": 0,
                "kept_count": 0,
                "excluded_count": 0,
                "candidate_limit": candidate_limit,
                "positive_threshold": positive_threshold,
                "margin_threshold": margin_threshold,
                "excluded_examples": [],
            },
        }

    prototype_embeddings = build_prototype_embeddings(client, model_name)
    article_embeddings = build_article_embeddings(client, articles, model_name)
    score_by_article_id = {}

    for article in articles:
        article_id = get_article_id(article)
        score = score_article_embedding(
            article_embeddings.get(article_id, []),
            prototype_embeddings,
            positive_threshold=positive_threshold,
            margin_threshold=margin_threshold,
        )
        score_by_article_id[article_id] = score

    result = select_articles_from_scores(
        articles,
        score_by_article_id,
        candidate_limit=candidate_limit,
    )
    result["selection"]["positive_threshold"] = positive_threshold
    result["selection"]["margin_threshold"] = margin_threshold
    result["selection"]["selector_model"] = selector_label

    print(f"      Selected tourism candidates: {len(result['articles'])}")
    print(f"      Excluded articles: {result['selection']['excluded_count']}")

    return result
