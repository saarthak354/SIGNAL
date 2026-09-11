import os

from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS

import db
import summarize

from ingest import get_articles, select, paginate
from sources import companies
from submissions import validate, save
from homepage import score_breakdown


app = Flask(__name__)


# -----------------------------------
# WHO MAY CALL THIS
# -----------------------------------
#
# The frontend is served from somewhere else --
# a static host -- so every request it makes is
# cross origin and CORS is what allows it.
#
# In development that was every origin, which is
# fine on a laptop and wrong in public: this API
# writes submissions and spends an API key, and
# neither should be reachable from any page that
# cares to ask.
#
# ALLOWED_ORIGINS is a comma separated list set
# on the host. Left unset, it falls back to the
# local frontend, so nothing has to change to
# keep working on a laptop.

LOCAL_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",

    # Opening index.html straight off disk sends
    # a null origin
    "null",
]


def allowed_origins():

    configured = os.environ.get("ALLOWED_ORIGINS", "").strip()

    if not configured:
        return LOCAL_ORIGINS

    return [
        origin.strip()
        for origin in configured.split(",")
        if origin.strip()
    ]


CORS(
    app,
    origins=allowed_origins(),

    # The API is public data and carries no
    # cookies or auth, so there is nothing for a
    # credentialed request to leak
    supports_credentials=False,
)


# -----------------------------------
# ARTICLES
# -----------------------------------
#
#   /api/articles                  home
#   /api/articles?tab=discovery    non company sources
#   /api/articles?tab=companies    company sources only
#   /api/articles?company=openai   one company
#   /api/articles?q=gpt-5          search everything
#   /api/articles?limit=15         cap the feed
#   /api/articles?offset=15        skip the first page
#   /api/articles?explain=1        show the ranking maths

MAX_LIMIT = 200


def positive_argument(name, default=None):

    raw = request.args.get(name)

    if not raw:
        return default

    try:
        value = int(raw)

    except ValueError:
        return default

    if value < 0:
        return default

    return value


def requested_limit():

    limit = positive_argument("limit")

    if not limit:
        return None

    return min(limit, MAX_LIMIT)


def requested_offset():

    return positive_argument("offset", 0)


@app.route("/api/articles")
def articles():

    cache = get_articles()

    selected = select(
        cache["articles"],
        tab=request.args.get("tab"),
        company_id=request.args.get("company"),
        query=request.args.get("q")
    )

    offset = requested_offset()

    shown = paginate(
        selected,
        requested_limit(),
        offset
    )

    payload = {
        "total_ingested": cache["ingested"],

        # How many matched before the cap, so the
        # page can say what it is not showing, and
        # work out whether there is a page after
        # this one
        "total_available": len(selected),

        "total_filtered": len(shown),

        # Where this page starts, so the range it
        # is showing can be named
        "offset": offset,

        "errors": cache["errors"],

        "articles": shown
    }

    # The point of ranking by rules rather than by
    # model is that there is always an answer to
    # why something is on the front page. This is
    # that answer, on request.
    if request.args.get("explain"):

        now = datetime.now(timezone.utc)

        payload["ranking"] = [
            {
                "title": article.get("title"),
                **score_breakdown(article, now)
            }
            for article in shown
        ]

    return jsonify(payload)


# -----------------------------------
# COMPANIES
# -----------------------------------
#
# Each company plus how much we currently
# hold for it, so the tab can show counts.

@app.route("/api/companies")
def company_list():

    cache = get_articles()

    counts = {}
    latest = {}

    for article in cache["articles"]:

        company_id = article.get("company_id")

        if not company_id:
            continue

        counts[company_id] = counts.get(company_id, 0) + 1

        if company_id not in latest:
            latest[company_id] = article["published"]

    return jsonify({
        "companies": [
            {
                **company,
                "count": counts.get(company["id"], 0),
                "latest": latest.get(company["id"])
            }
            for company in companies()
        ]
    })


# -----------------------------------
# CONTACT FORMS
# -----------------------------------
#
# Feedback and source suggestions from the
# footer. Kept on the server so a visitor
# never has to leave the page or open a
# mail client.

@app.route("/api/submissions", methods=["POST"])
def submit():

    entry, error = validate(
        request.get_json(silent=True)
    )

    if error:

        return jsonify({"error": error}), 400

    save(entry)

    return jsonify({"ok": True})


# -----------------------------------
# ONE ARTICLE
# -----------------------------------
#
# What the reader gets when they open a card:
# the article, and a summary long enough to
# stand in for it.
#
# Nearly always this is a single read, because
# the summary was written when the article was
# ingested. The fallback is for the gap between
# an article arriving and the summariser reaching
# it -- and for anyone running the server without
# the cron job. In that case one reader waits a
# few seconds and everybody after them does not.

@app.route("/api/articles/<int:article_id>")
def one_article(article_id):

    try:
        article = db.article(article_id)

    except Exception as error:

        return jsonify({
            "error": f"Could not read the store: {type(error).__name__}"
        }), 503

    if not article:
        return jsonify({"error": "No such article."}), 404

    if article.get("summary_status") == "ok":
        return jsonify({"article": article})

    # Nothing written yet, and no key to write it
    if not summarize.configured():
        return jsonify({"article": article})

    # A page we already know we cannot read
    if article.get("summary_status") == "thin":
        return jsonify({"article": article})

    summary, status, error = summarize.summarize({
        "id": article_id,
        "url": article["url"],
        "title": article["title"],
        "source": article["source"],
    })

    try:
        db.save_summary(
            article_id,
            summary,
            status,
            model=summarize.MODEL if status == "ok" else None,
            error=error
        )

    except Exception:

        # The reader still gets their summary even
        # if we could not keep it
        pass

    article["summary"] = summary
    article["summary_status"] = status

    return jsonify({"article": article})


# -----------------------------------
# HEALTH
# -----------------------------------
#
# Whether the store is reachable and when it was
# last filled, without loading the site to find
# out. Deliberately does not trigger an ingest:
# the point is to report the state, not change
# it.

@app.route("/api/health")
def health():

    if not db.configured():

        return jsonify({
            "database": "unconfigured",
            "detail": (
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are not set. "
                "The feed is being served from memory."
            )
        }), 503

    try:
        run = db.latest_run()

    except Exception as error:

        return jsonify({
            "database": "unreachable",
            "detail": f"{type(error).__name__}: {error}"
        }), 503

    if not run:

        return jsonify({
            "database": "empty",
            "detail": "Connected, but nothing has been ingested yet. Run: python refresh.py"
        })

    try:
        summaries = db.summary_counts()

    except Exception:
        summaries = None

    return jsonify({
        "database": "ok",
        "summaries": summaries,
        "summariser": summarize.MODEL if summarize.configured() else "unconfigured",
        "last_ingest": {
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "ingested": run["ingested"],
            "kept": run["kept"],
            "inserted": run["inserted"],
            "refreshed": run["refreshed"],
            "replaced": run["replaced"],
            "errors": run.get("errors") or [],
        }
    })


# -----------------------------------
# RUN SERVER
# -----------------------------------

# In production a WSGI server imports "app" from
# this file and this block never runs. It is only
# how the site starts on a laptop.
#
# debug is read from the environment and off
# unless asked for, because the Werkzeug debugger
# is an interactive Python prompt: reachable from
# the internet, it is remote code execution, not
# a convenience.

if __name__ == "__main__":

    # Not port 5000: on macOS the AirPlay Receiver
    # already listens there, which either stops
    # Flask from starting or answers the frontend
    # with a 403 on http://localhost:5000.
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5050)),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
