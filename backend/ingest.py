import threading
import time

from concurrent.futures import ThreadPoolExecutor

from news import fetch_rss_sources
from scrape import scrape_website
from filters import filter_articles, HOME_WINDOW_DAYS, RETENTION_DAYS
from sources import all_sources
from classify import detect_company


# -----------------------------------
# CACHE
# -----------------------------------
#
# Ingesting means nine network round trips
# and a few thousand entries, which is far
# too slow to redo on every page load.

CACHE_SECONDS = 600

_cache = {
    "articles": [],
    "ingested": 0,
    "errors": [],
    "fetched_at": 0,
}

_lock = threading.Lock()


# -----------------------------------
# TAG AN ARTICLE WITH ITS SOURCE
# -----------------------------------

def tag(article, source):

    is_company = source["category"] == "company"

    article["category"] = source["category"]

    article["company"] = (
        source["name"] if is_company else None
    )

    article["company_id"] = (
        source["id"] if is_company else None
    )

    # Which feed carried the story. For Discovery
    # the card credits the site being linked to,
    # so this is the only record of the aggregator
    # it actually came through.
    article["via"] = source["name"]

    # Discovery articles are published by someone
    # who is not a company, so work out who the
    # story is actually about.
    #
    # Kept separate from "company" on purpose: the
    # Companies tab lists what a company published
    # itself, and Discovery is everything else. One
    # article should never appear under both.
    if is_company:

        article["related_company"] = None
        article["related_company_id"] = None

    else:

        related_id, related_name = detect_company(article)

        article["related_company"] = related_name
        article["related_company_id"] = related_id

    # Used by the relevance filter, then dropped
    article["trusted"] = source.get("trusted", False)

    article["brand_aliases"] = source.get(
        "brand_aliases",
        [source["name"]]
    )

    return article


INTERNAL_FIELDS = [
    "trusted",
    "brand_aliases",
]


def clean(article):

    return {
        key: value
        for key, value in article.items()
        if key not in INTERNAL_FIELDS
    }


# -----------------------------------
# FETCH ONE SOURCE
# -----------------------------------

def fetch_source(source):

    try:

        if source["method"] == "rss":
            articles = fetch_rss_sources([source])

        else:
            articles = scrape_website(source)

        return source, articles, None

    except Exception as e:

        return source, [], f"{type(e).__name__}: {e}"


# -----------------------------------
# INGEST EVERYTHING
# -----------------------------------

def ingest():

    sources = all_sources()

    collected = []
    errors = []
    ingested = 0

    with ThreadPoolExecutor(max_workers=10) as executor:

        results = executor.map(fetch_source, sources)

        for source, articles, error in results:

            if error:

                print(f"{source['name']} failed: {error}")

                errors.append({
                    "source": source["name"],
                    "error": error
                })

                continue

            ingested += len(articles)

            collected.append((
                source,
                [tag(a, source) for a in articles]
            ))

    # Company sources go first so that when the
    # same story reaches us twice, the company
    # keeps it and Discovery loses the duplicate.
    ordered = []

    for category in ("company", "discovery"):

        for source, articles in collected:

            if source["category"] == category:
                ordered.extend(articles)

    filtered = filter_articles(
        ordered,
        window_days=RETENTION_DAYS
    )

    return {
        "articles": [clean(a) for a in filtered],
        "ingested": ingested,
        "errors": errors,
        "fetched_at": time.time(),
    }


# -----------------------------------
# CACHED ACCESS
# -----------------------------------

def get_articles(force=False):

    with _lock:

        age = time.time() - _cache["fetched_at"]

        if force or age > CACHE_SECONDS or not _cache["articles"]:

            _cache.update(ingest())

        return _cache


# -----------------------------------
# VIEWS
# -----------------------------------

def within_home_window(articles):

    from filters import is_recent

    return [
        a for a in articles
        if is_recent(a, HOME_WINDOW_DAYS)
    ]


def select(articles, tab=None, company_id=None, limit=None):

    # A single company: show its full history so
    # a quiet publisher never renders an empty page
    if company_id:

        return [
            a for a in articles
            if a.get("company_id") == company_id
        ]

    if tab == "companies":
        pool = [a for a in articles if a["category"] == "company"]

    elif tab == "discovery":
        pool = [a for a in articles if a["category"] == "discovery"]

    else:
        pool = articles

    return within_home_window(pool)


# -----------------------------------
# TRIM A FEED
# -----------------------------------
#
# A page nobody can scroll to the bottom of
# has no footer, so every list is capped.

def paginate(articles, limit=None):

    if not limit:
        return articles

    return articles[:limit]
