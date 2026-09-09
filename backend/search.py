import re


# -----------------------------------
# SEARCH
# -----------------------------------
#
# The feed only ever shows the last two weeks,
# so anything older is reachable only by asking
# for it. Search therefore runs over everything
# still retained, across every tab at once: a
# visitor looking for "gpt-5" wants the story
# wherever it was published, not the story
# filtered down to whichever tab they happened
# to be standing on.

MAX_QUERY_LENGTH = 100


# Where a word turns up says how much it counts.
# A headline is what an article is about; a
# description only mentions things in passing.

TITLE_WEIGHT = 3

SOURCE_WEIGHT = 2

BODY_WEIGHT = 1


# Split on punctuation, but keep the characters
# that live inside real names, so "gpt-4.5"
# stays searchable and "c++" survives.

SPLIT_PATTERN = re.compile(r"[^a-z0-9.+#]+")


def terms(query):

    if not query:
        return []

    trimmed = query.strip().lower()[:MAX_QUERY_LENGTH]

    return [
        word
        for word in SPLIT_PATTERN.split(trimmed)
        if word
    ]


# -----------------------------------
# SCORE ONE ARTICLE
# -----------------------------------
#
# Matching on substrings rather than whole
# words, so "openai" finds "OpenAI's" and
# "gpt" finds "GPT-5" without needing the
# visitor to type the exact form.

def score(article, words):

    title = (article.get("title") or "").lower()

    body = (article.get("description") or "").lower()

    # Every name the card can display, so the
    # site itself is searchable: "wired", "ars",
    # "anthropic" all find their own articles.
    names = " ".join([
        article.get("source") or "",
        article.get("via") or "",
        article.get("company") or "",
        article.get("related_company") or "",
    ]).lower()

    total = 0

    for word in words:

        found = 0

        if word in title:
            found += TITLE_WEIGHT

        if word in names:
            found += SOURCE_WEIGHT

        if word in body:
            found += BODY_WEIGHT

        # Every word has to land somewhere, so
        # adding a word narrows the results
        # instead of widening them
        if not found:
            return 0

        total += found

    return total


# -----------------------------------
# RUN A SEARCH
# -----------------------------------

def search(articles, query):

    words = terms(query)

    if not words:
        return []

    matches = []

    for article in articles:

        relevance = score(article, words)

        if relevance:

            matches.append((relevance, article))

    # Best match first, and the newer story wins
    # whenever two match equally well. Dates are
    # ISO strings by this point, so they sort
    # correctly as text.
    matches.sort(
        key=lambda pair: (
            pair[0],
            pair[1].get("published") or ""
        ),
        reverse=True
    )

    return [article for _, article in matches]
