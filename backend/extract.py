import re

import requests

from bs4 import BeautifulSoup

from scrape import HEADERS


# -----------------------------------
# READ AN ARTICLE
# -----------------------------------
#
# Everything else in this backend reads listing
# pages: a feed, or an index of cards. This is
# the only place that opens an article itself.
#
# It exists because there was nothing to
# summarise. What ingestion collects is a
# headline and whatever blurb the listing
# carried, which runs to a median of about two
# dozen words and is missing altogether on a
# quarter of what we hold. A summary written
# from that would say less than the card above
# it already does.


# Long enough to hold a full article, short
# enough that a page which turns out to be an
# index does not get sent to a model as one.
MAX_BODY = 24000

# Under this there is no article here: a paywall
# gate, a cookie wall, a page that builds itself
# in the browser, or a redirect we followed to
# somewhere that is not a story.
MIN_BODY = 700

TIMEOUT = 20


# -----------------------------------
# WHAT IS NOT THE ARTICLE
# -----------------------------------

FURNITURE = [
    "script", "style", "noscript", "nav", "header",
    "footer", "aside", "form", "iframe", "svg",
    "figure", "figcaption", "button",
]


# Wrappers a site puts its actual story in. Tried
# in order; the first one that holds enough text
# wins, and if none do the whole page is read.

CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    "[class*='article-body']",
    "[class*='article-content']",
    "[class*='post-content']",
    "[class*='entry-content']",
    "[itemprop='articleBody']",
]


# Lines that are furniture wearing a paragraph
# tag. They survive the tag strip above because
# they really are paragraphs; they are just not
# part of the story.

BOILERPLATE = re.compile(
    r"^(share this|sign up|subscribe|advertisement|related( stories| reading)?"
    r"|read more|follow us|copyright|all rights reserved|cookie"
    r"|by continuing|you may also like|most popular|newsletter)",
    re.IGNORECASE
)


def is_prose(text):

    # A caption, a byline, a nav item and a date
    # are all short. Real paragraphs are not.
    if len(text) < 60:
        return False

    if BOILERPLATE.match(text.strip()):
        return False

    # A line with no sentence in it is a label
    if "." not in text and "?" not in text:
        return False

    return True


def paragraphs_from(node):

    found = []

    for element in node.find_all(["p", "li"]):

        text = element.get_text(" ", strip=True)

        if is_prose(text):
            found.append(text)

    return found


def clean_body(text):

    text = re.sub(r"\s+", " ", text)

    return text.strip()[:MAX_BODY]


# -----------------------------------
# FETCH AND READ
# -----------------------------------

def extract(url):
    """
    The text of an article, or ("", reason) when
    there is not enough of one to summarise.

    Never raises: a page that cannot be read is
    an ordinary outcome here, not an error, and
    the caller records the reason rather than
    losing the article over it.
    """

    try:

        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers=HEADERS
        )

    except requests.RequestException as error:

        return "", f"unreachable: {type(error).__name__}"

    if response.status_code != 200:
        return "", f"http {response.status_code}"

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(FURNITURE):
        tag.decompose()

    best = []

    for selector in CONTENT_SELECTORS:

        for node in soup.select(selector):

            found = paragraphs_from(node)

            if len(" ".join(found)) > len(" ".join(best)):
                best = found

        if len(" ".join(best)) >= MIN_BODY:
            break

    # No wrapper worth the name, so read the page
    if len(" ".join(best)) < MIN_BODY:

        whole = paragraphs_from(soup)

        if len(" ".join(whole)) > len(" ".join(best)):
            best = whole

    body = clean_body(" ".join(best))

    if len(body) < MIN_BODY:

        # Almost always a paywall, a consent wall,
        # or a page that renders in the browser
        return "", f"too thin ({len(body)} chars)"

    return body, None
