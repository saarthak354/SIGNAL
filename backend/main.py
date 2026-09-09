from flask import Flask, jsonify, request
from flask_cors import CORS

from ingest import get_articles, select, paginate
from sources import companies
from submissions import validate, save


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
#   /api/articles?limit=15         cap the feed

MAX_LIMIT = 200


def requested_limit():

    raw = request.args.get("limit")

    if not raw:
        return None

    try:
        limit = int(raw)

    except ValueError:
        return None

    if limit < 1:
        return None

    return min(limit, MAX_LIMIT)


@app.route("/api/articles")
def articles():

    cache = get_articles()

    selected = select(
        cache["articles"],
        tab=request.args.get("tab"),
        company_id=request.args.get("company")
    )

    shown = paginate(
        selected,
        requested_limit()
    )

    return jsonify({
        "total_ingested": cache["ingested"],

        # How many matched before the cap, so the
        # page can say what it is not showing
        "total_available": len(selected),

        "total_filtered": len(shown),

        "errors": cache["errors"],

        "articles": shown
    })


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
