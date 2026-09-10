import os
import threading

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from dedupe import Deduper, canonical_url
from filters import RETENTION_DAYS, article_date, parse_date


# -----------------------------------
# ENVIRONMENT
# -----------------------------------
#
# Spelled out rather than left to load_dotenv()
# to find on its own.
#
# Given no path it guesses one, by walking the
# call stack for the first frame belonging to a
# real file and searching upwards from there.
# That guess is right when a script is run from
# a file and wrong in most other cases: under
# "python -c", in a REPL, in a notebook, or in a
# frozen build it falls back to the working
# directory instead, so the backend loses its
# settings the moment it is started from
# anywhere but its own folder.
#
# The file sits next to this one and always has,
# so there is nothing to search for.

ENV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".env"
)

load_dotenv(ENV_FILE)


# -----------------------------------
# THE STORE
# -----------------------------------
#
# Supabase holds the articles, and the site
# reads from here rather than from the feeds.
#
# The two jobs are now separate. Ingestion goes
# out to the sources and writes what it finds
# into these tables; a page load only ever reads
# them back. So a source being slow, or down, or
# quietly dropping an old post costs nothing at
# read time, and nothing that has ever been
# ingested falls off the site again.


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()

SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    or os.environ.get("SUPABASE_KEY", "").strip()
)


ARTICLES = "articles"

INGEST_RUNS = "ingest_runs"

SUBMISSIONS = "submissions"


# PostgREST caps a single response, so reads are
# paged, and writes go up in batches rather than
# as one enormous request body.

PAGE_SIZE = 1000

BATCH_SIZE = 200


_client = None

_client_lock = threading.Lock()


class DatabaseUnavailable(RuntimeError):
    pass


def configured():

    return bool(SUPABASE_URL and SUPABASE_KEY)


def client():
    """
    The Supabase client, built once.

    Imported here rather than at the top of the
    file so that a machine without the package
    installed still gets a clear error about the
    database instead of failing to start at all.
    """

    global _client

    if _client is not None:
        return _client

    with _client_lock:

        if _client is not None:
            return _client

        if not configured():

            raise DatabaseUnavailable(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are not set. "
                "Copy .env.example to .env and fill them in."
            )

        try:
            from supabase import create_client

        except ImportError as error:

            raise DatabaseUnavailable(
                f"The supabase package is not installed: {error}. "
                "Run: pip install -r requirements.txt"
            ) from error

        _client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY
        )

        return _client


# -----------------------------------
# ROWS AND ARTICLES
# -----------------------------------
#
# The rest of the backend passes articles around
# as plain dictionaries and has done since before
# there was a database. These two functions are
# the only place that shape meets the table, so
# nothing else has to know a database exists.

COLUMNS = (
    "id, url, url_key, title, description, source, via, source_tier, "
    "category, company, company_id, related_company, related_company_id, "
    "published, updated"
)


def to_row(article):

    published = article.get("published")

    updated = parse_date(article.get("updated"))

    return {
        "url": article.get("url"),
        "url_key": canonical_url(article.get("url")),

        "title": article.get("title"),
        "description": article.get("description") or "",

        "source": article.get("source") or "",
        "via": article.get("via") or "",
        "source_tier": article.get("source_tier") or "aggregator",

        "category": article.get("category") or "discovery",

        "company": article.get("company"),
        "company_id": article.get("company_id"),
        "related_company": article.get("related_company"),
        "related_company_id": article.get("related_company_id"),

        # Ingestion has already resolved this to
        # an ISO string; the column is the only
        # thing that ever needed it to be one.
        "published": published,
        "updated": updated.isoformat() if updated else None,
    }


def to_article(row):

    return {
        "title": row.get("title"),
        "url": row.get("url"),
        "description": row.get("description") or "",
        "source": row.get("source") or "",
        "published": row.get("published"),
        "updated": row.get("updated") or "",

        "category": row.get("category"),
        "company": row.get("company"),
        "company_id": row.get("company_id"),
        "via": row.get("via") or "",

        "related_company": row.get("related_company"),
        "related_company_id": row.get("related_company_id"),

        "source_tier": row.get("source_tier") or "aggregator",
    }


def cutoff(window_days):

    moment = datetime.now(timezone.utc) - timedelta(
        days=window_days
    )

    return moment.isoformat()


# -----------------------------------
# READ
# -----------------------------------

def read_rows(columns, window_days=RETENTION_DAYS):
    """
    Every article inside the window, newest
    first, a page at a time.
    """

    supabase = client()

    rows = []

    start = 0

    while True:

        response = (
            supabase.table(ARTICLES)
            .select(columns)
            .gte("published", cutoff(window_days))
            .order("published", desc=True)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )

        page = response.data or []

        rows.extend(page)

        if len(page) < PAGE_SIZE:
            return rows

        start += PAGE_SIZE


def load_articles(window_days=RETENTION_DAYS):

    return [
        to_article(row)
        for row in read_rows(COLUMNS, window_days)
    ]


# -----------------------------------
# WHO KEEPS THE STORY
# -----------------------------------
#
# Ingestion already drops duplicates inside a
# single run, and feeds company sources in first
# so a company keeps its own announcement.
#
# Across runs that ordering is gone. A newsroom
# writing up a launch at nine o'clock is stored
# hours before the company's own post arrives,
# and on the old rules the company's post would
# be turned away as a duplicate of the write up
# and never appear on its own page.
#
# So a stored story is not final. A better source
# for the same story takes its place.

TIER_RANK = {
    "company": 3,
    "publisher": 2,
    "aggregator": 1,
}


def outranks(article, row):

    return (
        TIER_RANK.get(article.get("source_tier"), 0)
        > TIER_RANK.get(row.get("source_tier"), 0)
    )


# -----------------------------------
# WRITE
# -----------------------------------

def batched(items, size=BATCH_SIZE):

    for start in range(0, len(items), size):
        yield items[start:start + size]


def sync_articles(articles, window_days=RETENTION_DAYS):
    """
    Fold a finished ingest into the store.

    Returns what it did, so the run can be
    recorded and reported.
    """

    supabase = client()

    stored = read_rows(
        "id, url_key, title, source_tier, published",
        window_days
    )

    held = {}

    deduper = Deduper()

    for row in stored:

        key = row["url_key"]

        held[key] = row

        deduper.record(
            row["title"],
            parse_date(row["published"]),
            key,
            row
        )

    fresh = []
    seen_again = []
    superseded = []

    # A stored row can only be replaced once, or
    # two write ups of one story would each claim
    # it and both get in
    claimed = set()

    for article in articles:

        key = canonical_url(article.get("url"))

        # The same link, already held
        if key in held:

            seen_again.append(key)
            continue

        index = deduper.match(article, article_date(article))

        if index is not None:

            row = deduper.payload(index)

            # Filed under a story ingested moments
            # ago in this same pass, not a stored
            # row: it is a duplicate, and there is
            # nothing to replace
            if row is None:
                continue

            if row["id"] in claimed or not outranks(article, row):
                continue

            claimed.add(row["id"])

            superseded.append(row["id"])

        fresh.append(to_row(article))

        # So the rest of this pass can see it
        deduper.record(
            article.get("title"),
            article_date(article),
            key
        )

    now = datetime.now(timezone.utc).isoformat()

    # Out first, so the row a replacement collides
    # with on url_key is already gone
    for chunk in batched(superseded):

        supabase.table(ARTICLES).delete().in_("id", chunk).execute()

    for chunk in batched(fresh):

        # A second ingest running alongside this
        # one can have written the same link, and
        # losing that race should not lose the run
        supabase.table(ARTICLES).upsert(
            chunk,
            on_conflict="url_key"
        ).execute()

    # An article still being carried by a live
    # feed, which is the difference between an
    # archived story and a current one
    for chunk in batched(seen_again, PAGE_SIZE):

        supabase.table(ARTICLES).update(
            {"last_seen_at": now}
        ).in_("url_key", chunk).execute()

    return {
        "kept": len(articles),
        "inserted": len(fresh),
        "refreshed": len(seen_again),
        "replaced": len(superseded),
    }


# -----------------------------------
# INGEST RUNS
# -----------------------------------

def record_run(counts, errors, started_at):

    supabase = client()

    row = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ingested": counts.get("ingested", 0),
        "kept": counts.get("kept", 0),
        "inserted": counts.get("inserted", 0),
        "refreshed": counts.get("refreshed", 0),
        "replaced": counts.get("replaced", 0),
        "errors": errors or [],
    }

    supabase.table(INGEST_RUNS).insert(row).execute()

    return row


def latest_run():
    """
    What the last ingest saw. A page load no
    longer fetches anything itself, so this is
    where the feed's own stats come from.
    """

    supabase = client()

    response = (
        supabase.table(INGEST_RUNS)
        .select("*")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    return rows[0] if rows else None


# -----------------------------------
# SUBMISSIONS
# -----------------------------------

def save_submission(entry):

    supabase = client()

    response = supabase.table(SUBMISSIONS).insert({
        "type": entry["type"],
        "name": entry["name"],
        "message": entry["message"],
        "submitted_at": entry["submitted_at"],
    }).execute()

    rows = response.data or []

    return rows[0] if rows else entry


# -----------------------------------
# HOUSEKEEPING
# -----------------------------------
#
# Never called on a schedule. The store is an
# archive and articles are meant to stay in it;
# this is here for when one has to be taken out
# on purpose.

def prune_articles(older_than_days):

    supabase = client()

    response = (
        supabase.table(ARTICLES)
        .delete()
        .lt("published", cutoff(older_than_days))
        .execute()
    )

    return len(response.data or [])
