import threading
import time

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import db

from news import fetch_rss_sources
from scrape import scrape_website
from filters import filter_articles, HOME_WINDOW_DAYS, RETENTION_DAYS
from sources import all_sources
from classify import detect_company, company_from_url
from search import search
from homepage import curate


# -----------------------------------
# CACHE
# -----------------------------------
#
# Two clocks, because there are now two jobs
# and they run at different speeds.
#
# Going out to the sources means nine network
# round trips and a few thousand entries, so it
# happens rarely and writes what it finds to the
# store. Reading the store back is one query, so
# it happens often and is all a page load needs.
#
# The practical difference: a slow or broken
# source no longer holds up a request, because
# no request is waiting on one.

INGEST_SECONDS = 600

CACHE_SECONDS = 60

_cache = {
    "articles": [],
    "ingested": 0,
    "errors": [],
    "loaded_at": 0,
    "ingested_at": 0,
}

_lock = threading.Lock()

# Set while a background refresh is in flight, so
# ten visitors arriving at once start one refresh
# between them rather than ten.
_refreshing = False

_refresh_lock = threading.Lock()


# -----------------------------------
# TAG AN ARTICLE WITH ITS SOURCE
# -----------------------------------

def tag(article, source):

    # Which feed carried a story does not decide
    # whose story it is. An aggregator linking
    # straight at a company's own site has handed
    # us that company's own post, and that belongs
    # with the rest of them: Discovery is for what
    # other people wrote, not for a company blog
    # that happened to arrive by a different road.
    if source["category"] == "company":

        company_id = source["id"]
        company_name = source["name"]

    else:

        company_id, company_name = company_from_url(
            article.get("url", "")
        )

    is_company = bool(company_id)

    article["category"] = (
        "company" if is_company else "discovery"
    )

    article["company"] = company_name

    article["company_id"] = company_id

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

    # What kind of source this is, which is what
    # the homepage ranking weighs: a company's own
    # announcement, a newsroom reporting on it, or
    # a link somebody upvoted.
    article["source_tier"] = (
        "company" if is_company
        else "aggregator" if source.get("aggregator")
        else "publisher"
    )

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
# GO OUT AND FETCH
# -----------------------------------
#
# Every source, filtered down to what belongs on
# the site. Knows nothing about where the result
# is going to be kept.

def collect():

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
    }


# -----------------------------------
# WITHOUT THE STORE
# -----------------------------------
#
# The site should not go dark because the
# database is unreachable or unconfigured. It
# falls back to what it always used to do: hold
# this run in memory and serve that.
#
# Everything still works except the part the
# store exists for, which is remembering
# anything beyond what the feeds are carrying
# right now.

def serve_from_memory(collected, reason=None):

    if reason:
        print(f"Serving from memory: {reason}")

    _cache.update({
        "articles": collected["articles"],
        "ingested": collected["ingested"],
        "errors": collected["errors"],
        "loaded_at": time.time(),
    })


# -----------------------------------
# FETCH, THEN STORE
# -----------------------------------

def refresh():

    started_at = datetime.now(timezone.utc).isoformat()

    collected = collect()

    _cache["ingested_at"] = time.time()

    if not db.configured():

        serve_from_memory(
            collected,
            "SUPABASE_URL and SUPABASE_SERVICE_KEY are not set"
        )

        return

    try:

        counts = db.sync_articles(collected["articles"])

        counts["ingested"] = collected["ingested"]

        db.record_run(
            counts,
            collected["errors"],
            started_at
        )

        print(
            f"Ingest: {counts['ingested']} entries, "
            f"{counts['kept']} kept, "
            f"{counts['inserted']} new, "
            f"{counts['replaced']} replaced"
        )

        # There is something new to read
        _cache["loaded_at"] = 0

    except Exception as error:

        serve_from_memory(
            collected,
            f"{type(error).__name__}: {error}"
        )


# -----------------------------------
# READ THE STORE
# -----------------------------------

def reload():

    articles = db.load_articles()

    run = db.latest_run() or {}

    _cache.update({
        "articles": articles,

        # What the last ingest saw, rather than
        # what this request saw, because this
        # request did not fetch anything
        "ingested": run.get("ingested", len(articles)),
        "errors": run.get("errors") or [],

        "loaded_at": time.time(),
    })


# -----------------------------------
# REFRESH WITHOUT ANYONE WAITING
# -----------------------------------
#
# Going out to the sources takes about three
# seconds: fifteen feeds, a couple of thousand
# entries, and a write to the store.
#
# That used to happen inside a request, so every
# ten minutes one visitor opened the site and sat
# in front of a loading screen for the whole of
# it while the rest queued behind the lock. They
# were paying for everybody else's freshness.
#
# The store already holds every article, so there
# is no reason for anyone to wait: the page is
# served from what we have, and the refresh runs
# behind it for the next reader. Slightly stale
# beats visibly slow -- and "stale" here means a
# feed that is up to ten minutes behind, on a
# site whose sources publish a few times a day.

def start_background_refresh():

    global _refreshing

    with _refresh_lock:

        if _refreshing:
            return

        _refreshing = True

    def work():

        global _refreshing

        try:
            refresh()

        except Exception as error:

            print(
                f"Background refresh failed: "
                f"{type(error).__name__}: {error}"
            )

        finally:

            with _refresh_lock:
                _refreshing = False

    threading.Thread(
        target=work,
        name="signal-refresh",
        daemon=True
    ).start()


# -----------------------------------
# CACHED ACCESS
# -----------------------------------

def get_articles(force=False):

    # Without a store, this process's own last
    # ingest is the only copy of anything, so it
    # has to be done here and waited for.
    if not db.configured():

        with _lock:

            if force or time.time() - _cache["ingested_at"] > INGEST_SECONDS:
                refresh()

            return _cache

    with _lock:

        # An explicit refresh is somebody asking
        # for it and willing to wait
        if force:
            refresh()

        elif time.time() - _cache["ingested_at"] > INGEST_SECONDS:
            start_background_refresh()

        stale = time.time() - _cache["loaded_at"] > CACHE_SECONDS

        if force or stale or not _cache["articles"]:

            try:
                reload()

            except Exception as error:

                print(
                    f"Could not read the store: "
                    f"{type(error).__name__}: {error}"
                )

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


def select(articles, tab=None, company_id=None, query=None):

    # Search reaches across every tab and back
    # through everything retained, not just the
    # fortnight the feed itself shows
    if query:
        return search(articles, query)

    # A single company: show its full history so
    # a quiet publisher never renders an empty page
    if company_id:

        return [
            a for a in articles
            if a.get("company_id") == company_id
        ]

    # Companies and Discovery are archives. They
    # answer "what has this company published" and
    # "what is the field talking about", so they
    # show everything they hold, newest first.
    if tab == "companies":

        return within_home_window(
            [a for a in articles if a["category"] == "company"]
        )

    if tab == "discovery":

        return within_home_window(
            [a for a in articles if a["category"] == "discovery"]
        )

    # Home answers a different question — what
    # matters right now — so it is chosen rather
    # than listed. Nothing is lost by being left
    # off it; every article is still on its own tab.
    return curate(
        within_home_window(articles)
    )


# -----------------------------------
# TRIM A FEED
# -----------------------------------
#
# A page nobody can scroll to the bottom of
# has no footer, so every list is capped.
#
# The cap is a window, not a cut off: whatever
# falls outside it is still reachable by asking
# for the next offset, so a company with a
# hundred posts keeps all hundred.

def paginate(articles, limit=None, offset=0):

    if offset:
        articles = articles[offset:]

    if not limit:
        return articles

    return articles[:limit]
