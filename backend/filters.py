import re

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from dedupe import Deduper


# -----------------------------------
# HOW FAR BACK WE LOOK
# -----------------------------------
#
# Company blogs publish weekly, not hourly,
# so a 24 hour window hides them entirely.
#
# Two windows: the home feed stays current,
# while company pages keep enough history to
# never look empty for a quiet publisher.

HOME_WINDOW_DAYS = 14

RETENTION_DAYS = 90


# -----------------------------------
# PARSE A PUBLISH DATE
# -----------------------------------
#
# Feeds and scraped pages use different
# formats, so try each one in turn.

DATE_FORMATS = [
    "%b %d, %Y",        # Sep 1, 2026
    "%B %d, %Y",        # September 1, 2026
    "%d %b %Y",         # 1 Sep 2026
    "%d %B %Y",         # 1 September 2026
    "%Y-%m-%d",         # 2026-09-01
    "%Y/%m/%d",         # 2026/09/01
]


def parse_date(value):

    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    # RFC 2822 — the normal RSS format
    try:

        parsed = parsedate_to_datetime(value)

        if parsed:
            return to_utc(parsed)

    except (TypeError, ValueError):
        pass

    # ISO 8601 — used by some feeds and scrapers
    try:

        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        return to_utc(parsed)

    except ValueError:
        pass

    # Human readable dates from scraped pages
    for date_format in DATE_FORMATS:

        try:

            parsed = datetime.strptime(
                value,
                date_format
            )

            return to_utc(parsed)

        except ValueError:
            continue

    return None


def to_utc(value):

    # Treat dates without a timezone as UTC
    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)


# -----------------------------------
# RECENCY
# -----------------------------------

def is_within_window(published, window_days=RETENTION_DAYS):

    if not published:
        return False

    now = datetime.now(timezone.utc)

    cutoff_time = now - timedelta(
        days=window_days
    )

    # Ignore feeds with dates in the future
    if published > now + timedelta(days=1):
        return False

    return published >= cutoff_time


def is_recent(article, window_days=RETENTION_DAYS):

    return is_within_window(
        article_date(article),
        window_days
    )


# -----------------------------------
# DROP NON ARTICLE PAGES
# -----------------------------------

UNWANTED_WORDS = [
    "event",
    "events",
    "webinar",
    "job",
    "jobs",
    "careers",
    "hiring",
    "podcast",
    "newsletter",
    "subscribe",
    "pricing",
    "terms of service",
    "privacy policy",
]

UNWANTED_PATTERN = re.compile(
    "|".join(
        r"\b" + re.escape(word) + r"\b"
        for word in UNWANTED_WORDS
    ),
    re.IGNORECASE
)


def is_news(article):

    title = article.get("title", "")

    if not title.strip():
        return False

    return not UNWANTED_PATTERN.search(title)


# -----------------------------------
# AI RELEVANCE
# -----------------------------------
#
# Everything published by a dedicated AI lab
# is AI news, so those domains are trusted
# outright. Everything else (mainly Hacker
# News) has to mention AI explicitly.

TRUSTED_AI_DOMAINS = [
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "ai.google",
    "ai.meta.com",
    "mistral.ai",
    "x.ai",
    "cohere.com",
    "huggingface.co",
    "deepseek.com",
]


AI_KEYWORDS = [
    # The field
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural network",
    "generative ai",
    "agentic",
    "ai agent",
    "ai model",
    "ai safety",
    "ai research",
    "ai lab",
    "ai chip",
    "alignment",
    "foundation model",
    "frontier model",
    "large language model",
    "language model",
    "multimodal",
    "diffusion model",
    "transformer",
    "fine-tuning",
    "fine tuning",
    "inference",
    "embeddings",
    "rag",
    "reinforcement learning",
    "chain of thought",
    "reasoning model",
    "open weights",
    "open-weights",
    "benchmark",
    "hallucination",
    "prompt injection",
    "context window",
    "tokenizer",
    "gpu",
    "tpu",

    # Labs and companies
    "openai",
    "anthropic",
    "deepmind",
    "google ai",
    "meta ai",
    "microsoft ai",
    "mistral",
    "cohere",
    "hugging face",
    "deepseek",
    "stability ai",
    "perplexity",
    "nvidia",
    "xai",

    # Products and models
    "ai",
    "llm",
    "llms",
    "chatgpt",
    "gpt",
    "claude",
    "gemini",
    "llama",
    "grok",
    "copilot",
    "midjourney",
    "stable diffusion",
    "sora",
    "whisper",
    "codex",
    "qwen",
    "mistral",
]

AI_PATTERN = re.compile(
    "|".join(
        r"\b" + re.escape(keyword) + r"\b"
        for keyword in AI_KEYWORDS
    ),
    re.IGNORECASE
)


def is_trusted_ai_source(article):

    url = (article.get("url") or "").lower()

    for domain in TRUSTED_AI_DOMAINS:

        if domain in url:
            return True

    return False


def strip_brand(text, aliases):

    # A company blog says its own name on every
    # post, so its brand proves nothing about
    # whether a given post is about AI.

    for alias in aliases:

        if not alias:
            continue

        text = re.sub(
            re.escape(alias),
            " ",
            text,
            flags=re.IGNORECASE
        )

    return text


def is_relevant(article):

    # A dedicated AI lab posting on its own site
    if article.get("trusted"):
        return True

    if is_trusted_ai_source(article):
        return True

    text = " ".join([
        article.get("title", "") or "",
        article.get("description", "") or "",
        article.get("source", "") or "",
        article.get("url", "") or "",
    ])

    text = strip_brand(
        text,
        article.get("brand_aliases") or []
    )

    return bool(AI_PATTERN.search(text))


# -----------------------------------
# RESOLVE AN ARTICLE DATE
# -----------------------------------

def article_date(article):

    return parse_date(
        article.get("published")
    ) or parse_date(
        article.get("updated")
    )


# -----------------------------------
# MAIN FILTER
# -----------------------------------

def filter_articles(articles, window_days=RETENTION_DAYS):

    filtered_articles = []

    deduper = Deduper()

    for article in articles:

        if not (article.get("url") or "").strip():
            continue

        if not (article.get("title") or "").strip():
            continue

        published = article_date(article)

        if not is_within_window(published, window_days):
            continue

        if not is_news(article):
            continue

        if not is_relevant(article):
            continue

        # Last, so that an article only ever
        # displaces a later copy of itself once
        # it has earned its own place in the feed
        if not deduper.add(article, published):
            continue

        # Nothing can have been published after
        # the moment we read it. A source can still
        # date an article a few hours ahead -- most
        # often a date with no time on it, read as
        # midnight UTC while it is still the day
        # before in UTC. Stored as given, that date
        # displayed as "-219m ago", and the homepage
        # ranking read "in the future" as "zero hours
        # old" and gave it full recency, pinning it
        # to the top of the page.
        #
        # The window above still admits it -- the
        # article is real -- it just cannot be newer
        # than now.
        now = datetime.now(timezone.utc)

        if published > now:
            published = now

        # Hand the frontend one consistent
        # date format regardless of source
        article["published"] = published.isoformat()

        filtered_articles.append(article)

    if deduper.duplicates:

        print(
            f"Dropped {deduper.duplicates} duplicate "
            f"articles across sources"
        )

    # Newest first
    filtered_articles.sort(
        key=lambda item: item["published"],
        reverse=True
    )

    return filtered_articles
