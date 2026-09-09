import re

from urllib.parse import urlparse

from sources import COMPANY_SOURCES


# -----------------------------------
# WHICH COMPANY IS THIS ABOUT?
# -----------------------------------
#
# A Discovery article is published by someone
# who is not a company, so its subject has to
# be read out of the text itself.
#
# Titles carry the subject far more reliably
# than a body or a URL, so they count more.

TITLE_WEIGHT = 3

BODY_WEIGHT = 1


def build_domains():

    domains = []

    for source in COMPANY_SOURCES:

        for domain in source.get("domains") or []:

            domains.append(
                (domain, source["id"], source["name"])
            )

    return domains


DOMAINS = build_domains()


def company_from_url(url):

    if not url:
        return None, None

    host = urlparse(url).netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    for domain, company_id, name in DOMAINS:

        if host == domain or host.endswith("." + domain):
            return company_id, name

    return None, None


def build_patterns():

    patterns = {}

    for source in COMPANY_SOURCES:

        aliases = source.get("aliases") or [source["name"]]

        patterns[source["id"]] = (
            source["name"],
            re.compile(
                "|".join(
                    r"\b" + re.escape(alias) + r"\b"
                    for alias in aliases
                ),
                re.IGNORECASE
            )
        )

    return patterns


PATTERNS = build_patterns()


def detect_company(article):

    # Linking straight to a company settles it
    company_id, name = company_from_url(
        article.get("url", "")
    )

    if company_id:
        return company_id, name

    title = article.get("title", "") or ""

    body = " ".join([
        article.get("description", "") or "",
        article.get("url", "") or "",
    ])

    best_id = None
    best_name = None
    best_score = 0
    best_position = None

    for company_id, (name, pattern) in PATTERNS.items():

        title_hits = pattern.findall(title)
        body_hits = pattern.findall(body)

        score = (
            len(title_hits) * TITLE_WEIGHT
            + len(body_hits) * BODY_WEIGHT
        )

        if not score:
            continue

        match = pattern.search(title)

        # Earlier in the title wins a tie
        position = match.start() if match else len(title) + 1

        better = (
            score > best_score
            or (score == best_score and position < best_position)
        )

        if better:

            best_id = company_id
            best_name = name
            best_score = score
            best_position = position

    return best_id, best_name
