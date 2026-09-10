from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS

from ingest import get_articles, select, paginate
from sources import companies
from submissions import validate, save
from homepage import score_breakdown


app = Flask(__name__)
CORS(app)


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
# RUN SERVER
# -----------------------------------

if __name__ == "__main__":

    # Not port 5000: on macOS the AirPlay Receiver
    # already listens there, which either stops
    # Flask from starting or answers the frontend
    # with a 403 on http://localhost:5000.
    app.run(
        debug=True,
        port=5050
    )
