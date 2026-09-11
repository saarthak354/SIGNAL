import html
import re

import feedparser
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse


# -----------------------------------
# CLEAN A FEED DESCRIPTION
# -----------------------------------
#
# Some feeds put markup in the summary, and
# Hacker News uses it only for a link back to
# its own comment thread, which is not a
# description of anything.

BOILERPLATE = {
    "comments",
    "read more",
    "continue reading",
    "link",
    "article",
}


# Some feeds escape their markup twice, so one
# pass leaves "&amp;#8217;" as "&#8217;" -- still
# an entity, just a less obvious one. Decoding
# until it stops changing handles both, and a
# bound keeps it from looping on pathological
# input.

def unescape_fully(text, rounds=3):

    for _ in range(rounds):

        decoded = html.unescape(text)

        if decoded == text:
            break

        text = decoded

    return text


def clean_text(value):
    """
    Feed text, with its markup and entities taken
    off. Used for titles as well as bodies --
    titles are escaped exactly the same way, and
    for a while only the bodies were being cleaned,
    which is how a headline came to read
    "Meta says it&#8217;s changing AI suggestions".
    """

    if not value:
        return ""

    text = re.sub(r"<[^>]+>", " ", value)

    text = unescape_fully(text)

    return re.sub(r"\s+", " ", text).strip()


def clean_description(value):

    if not value:
        return ""

    text = clean_text(value)

    if text.lower().strip(" .") in BOILERPLATE:
        return ""

    return text


# -----------------------------------
# THE ARTICLE, IF THE FEED CARRIES IT
# -----------------------------------
#
# Most feeds hand over a headline and a blurb.
# Some hand over the whole article in
# <content:encoded>, and that is worth keeping:
# it is text we already have, so summarising
# from it costs no fetch at all -- and it is the
# only text we will ever get from a publisher
# whose own pages are behind a bot check.
#
# Ars Technica is exactly that case. Its pages
# answer an AWS WAF JavaScript challenge that no
# plain HTTP client can pass, but its feed gives
# a thousand words of every story.

MAX_FEED_TEXT = 24000


def feed_text(entry):

    best = ""

    for block in entry.get("content") or []:

        value = block.get("value") or ""

        if len(value) > len(best):
            best = value

    # Some feeds put the article in the summary
    # and leave content empty
    summary = entry.get("summary") or ""

    if len(summary) > len(best):
        best = summary

    if not best:
        return ""

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", best, flags=re.S | re.I)

    text = re.sub(r"<[^>]+>", " ", text)

    text = unescape_fully(text)

    text = re.sub(r"\s+", " ", text).strip()

    return text[:MAX_FEED_TEXT]


# -----------------------------------
# GET ORIGINAL SOURCE NAME
# -----------------------------------

def get_original_source(url, fallback_source):

    if not url:
        return fallback_source

    parsed_url = urlparse(url)

    domain = parsed_url.netloc.lower()

    # Remove common prefixes
    if domain.startswith("www."):
        domain = domain[4:]

    # Known AI/company sources
    source_names = {
        "openai.com": "OpenAI",
        "anthropic.com": "Anthropic",
        "ai.google": "Google",
        "blog.google": "Google",
        "deepmind.google": "Google DeepMind",
        "ai.meta.com": "Meta AI",
        "meta.com": "Meta",
        "x.ai": "xAI",
        "grok.com": "Grok",
        "mistral.ai": "Mistral AI",
        "cohere.com": "Cohere",
        "huggingface.co": "Hugging Face",
        "microsoft.com": "Microsoft",
        "github.com": "GitHub",
        "cbsnews.com": "CBS News",
        "reuters.com": "Reuters",
        "techcrunch.com": "TechCrunch",
        "theverge.com": "The Verge",
        "arstechnica.com": "Ars Technica",
        "technologyreview.com": "MIT Technology Review",
        "wired.com": "WIRED",
        "forbes.com": "Forbes",
        "nytimes.com": "The New York Times",
    }

    if domain in source_names:
        return source_names[domain]

    # Handle subdomains
    for known_domain, name in source_names.items():

        if domain.endswith("." + known_domain):
            return name

    # Hacker News itself
    if "ycombinator.com" in domain:
        return "Hacker News"

    # Generic fallback
    return domain


# -----------------------------------
# FETCH ONE RSS FEED
# -----------------------------------

def fetch_feed(source):

    try:

        feed = feedparser.parse(source["url"])

        # feedparser reports parse errors instead
        # of raising, so check for entries
        if not feed.entries:

            print(
                f"No entries from {source['name']}"
            )

        return source, feed

    except Exception as e:

        print(
            f"RSS fetch failed for {source['name']}: {e}"
        )

        return source, None


# -----------------------------------
# FETCH ALL RSS SOURCES
# -----------------------------------

def fetch_rss_sources(sources):

    articles = []

    with ThreadPoolExecutor(max_workers=5) as executor:

        results = executor.map(fetch_feed, sources)

        for source, feed in results:

            if not feed:
                continue

            for article in feed.entries:

                article_url = article.get(
                    "link",
                    ""
                )

                # A link is the article identity
                if not article_url:
                    continue

                news_item = {

                    "title": clean_text(
                        article.get("title", "")
                    ),

                    "url": article_url,

                    "description": clean_description(
                        article.get("description", "")
                    ),

                    # A publisher's feed speaks for itself,
                    # whether that is a company blog or a
                    # newsroom like The Verge. An aggregator
                    # like Hacker News carries other people's
                    # writing, so it credits whoever it
                    # actually links out to.
                    "source": (
                        get_original_source(
                            article_url,
                            source["name"]
                        )
                        if source.get("aggregator")
                        else source["name"]
                    ),

                    "published": article.get(
                        "published",
                        ""
                    ),

                    "updated": article.get(
                        "updated",
                        ""
                    ),

                    # Kept for the summariser, not
                    # for the card
                    "feed_text": feed_text(article)
                }

                articles.append(news_item)

    return articles