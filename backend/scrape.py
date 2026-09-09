import re

import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# -----------------------------------
# SELECTOR HELPERS
# -----------------------------------
#
# Sites ship hashed CSS class names that
# change on every redeploy, so each field
# gets a list of selectors to try in order.
#
# The selector "self" means "use the text of
# the card element itself".

def as_selector_list(value, fallback):

    if value is None:
        return fallback

    if isinstance(value, str):
        return [value]

    return list(value)


def select_text(card, selectors, skip=(), min_length=0):

    skip = {
        value.strip()
        for value in skip
        if value
    }

    for selector in selectors:

        if selector == "self":
            elements = [card]

        else:
            elements = card.select(selector)

        for element in elements:

            # A date is never a title or a body
            if element.name == "time":
                continue

            if element is not card and element.find("time"):
                continue

            text = element.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            # Don't repeat a field we already have
            if text in skip:
                continue

            # Category chips ("Product", "Research")
            # sit in the same containers as bodies
            if len(text) < min_length:
                continue

            return text

    return ""


# -----------------------------------
# DATE FROM FREE TEXT
# -----------------------------------
#
# Tailwind-style sites label dates with no
# <time> tag and no useful class name, so
# fall back to reading the card's own text.

DATE_TEXT_PATTERN = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\.?\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE
)


def date_from_text(card):

    match = DATE_TEXT_PATTERN.search(
        card.get_text(" ", strip=True)
    )

    return match.group(0) if match else ""


# -----------------------------------
# DATE FROM THE URL
# -----------------------------------
#
# Plenty of sites put the publish date in the
# link even when the listing page hides it.

def date_from_url(url, pattern, century=""):

    if not pattern:
        return ""

    match = re.search(pattern, url)

    if not match:
        return ""

    year, month, day = match.groups()[:3]

    return f"{century}{year}-{month}-{day}"


# -----------------------------------
# FETCH A PAGE
# -----------------------------------

def get_soup(url):

    response = requests.get(
        url,
        timeout=20,
        headers=HEADERS
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


# -----------------------------------
# FIND THE ARTICLE CARDS
# -----------------------------------
#
# Some listings wrap each article in a
# container; on others the link itself is
# the whole card.

def find_cards(soup, source):

    container_selectors = source.get(
        "container_selector"
    )

    if not container_selectors:

        return [
            (link, link)
            for link in soup.find_all("a", href=True)
        ]

    cards = []

    for selector in as_selector_list(container_selectors, []):

        for container in soup.select(selector):

            link = container.select_one("a[href]")

            if link:
                cards.append((container, link))

        if cards:
            break

    return cards


# -----------------------------------
# SCRAPE ONE WEBSITE
# -----------------------------------

def scrape_website(source):

    soup = get_soup(source["url"])

    path_filter = source.get("path_filter", "")

    base_url = source.get(
        "base_url",
        source["url"]
    )

    # A few sites only render their full index
    # on an article page, so hop there first.
    if source.get("follow_link"):

        first = None

        for link in soup.find_all("a", href=True):

            if path_filter and path_filter in link["href"]:

                first = urljoin(base_url, link["href"])
                break

        if first:
            soup = get_soup(first)


    title_selectors = as_selector_list(
        source.get("title_selector"),
        ["h2", "h3", "h4", "[class*='title']", "[class*='heading']"]
    )

    description_selectors = as_selector_list(
        source.get("description_selector"),
        ["p", "[class*='description']"]
    )

    date_selectors = as_selector_list(
        source.get("date_selector"),
        ["time", "[class*='date']", "[datetime]"]
    )

    date_url_pattern = source.get("date_url_pattern")

    date_url_century = source.get("date_url_century", "")

    exclude_patterns = source.get(
        "exclude_url_patterns",
        []
    )

    min_title_length = source.get(
        "min_title_length",
        0
    )


    articles = []
    seen_urls = set()


    for card, link in find_cards(soup, source):

        href = link.get("href")

        if not href:
            continue

        # Only consider links pointing to articles
        if path_filter and path_filter not in href:
            continue

        article_url = urljoin(
            base_url,
            href
        )

        # Translations, tag pages, share links
        if any(bad in article_url for bad in exclude_patterns):
            continue

        # Prevent duplicate articles
        if article_url in seen_urls:
            continue


        # -----------------------------------
        # DATE
        # -----------------------------------
        #
        # Read first so the title and the body
        # can be told apart from it.

        published = ""

        for selector in date_selectors:

            element = card.select_one(selector)

            if not element:
                continue

            # Prefer a machine readable date
            published = element.get(
                "datetime",
                ""
            ) or element.get_text(
                " ",
                strip=True
            )

            if published:
                break

        if not published:
            published = date_from_text(card)

        if not published:

            published = date_from_url(
                article_url,
                date_url_pattern,
                date_url_century
            )


        # -----------------------------------
        # TITLE
        # -----------------------------------

        title = select_text(
            card,
            title_selectors,
            skip=[published],
            min_length=min_title_length
        )

        # Navigation and language links live in the
        # same markup, so a card only counts once it
        # has produced a real title
        if not title:
            continue

        seen_urls.add(article_url)


        # -----------------------------------
        # DESCRIPTION
        # -----------------------------------
        #
        # Cards without a body exist, and an
        # empty description beats a wrong one.

        description = select_text(
            card,
            description_selectors,
            skip=[published, title],
            min_length=40
        )


        articles.append({

            "title": title,

            "url": article_url,

            "description": description,

            "source": source["name"],

            "published": published,

            "updated": ""
        })

    return articles
