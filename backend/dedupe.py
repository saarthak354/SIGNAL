import re
import unicodedata

from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlparse


# -----------------------------------
# ONE STORY, ONE CARD
# -----------------------------------
#
# Discovery pulls from seven sites that all
# cover the same industry, so the same story
# arrives several times a day under several
# different headlines:
#
#   Ars Technica  "Anthropic researcher quits with a
#                  warning: self-improving AI could
#                  kill everyone"
#   TechCrunch    "Anthropic safety researcher resigns,
#                  warns self-improving AI is dangerous"
#   Hacker News   "Anthropic researcher quits over
#                  self-improving AI"
#
# Matching the URL catches only the easy case,
# where an aggregator links straight at an
# article we already hold. The rest have to be
# matched on what the headline says, so every
# title is reduced to the set of words that
# carry its meaning and two stories count as
# one when those sets mostly agree.
#
# Whoever gets there first keeps the story, so
# the order sources are fed in is the order of
# preference. Companies come before Discovery,
# and inside Discovery the sites that do their
# own reporting come before the aggregator.


# -----------------------------------
# CANONICAL URL
# -----------------------------------
#
# The same page is linked with tracking
# parameters, with and without www, as an AMP
# copy, and with or without a trailing slash.

TRACKING_SUFFIXES = [
    "/amp",
    "/amp/",
]


def canonical_url(url):

    if not url:
        return ""

    parsed = urlparse(url.strip().lower())

    host = parsed.netloc

    for prefix in ("www.", "m.", "amp."):

        if host.startswith(prefix):
            host = host[len(prefix):]

    path = parsed.path

    for suffix in TRACKING_SUFFIXES:

        if path.endswith(suffix):
            path = path[: -len(suffix)]

    path = path.rstrip("/")

    # Query strings here are campaign tags and
    # session ids, never the article identity
    return f"{host}{path}"


# -----------------------------------
# TITLE FINGERPRINT
# -----------------------------------
#
# Words every headline uses. They say nothing
# about which story this is, and leaving them
# in makes any two headlines look alike.

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "can", "did", "do", "does", "for", "from", "had", "has", "have",
    "how", "in", "into", "is", "it", "its", "of", "on", "or", "over",
    "s", "so", "than", "that", "the", "their", "them", "there",
    "these", "they", "this", "to", "up", "was", "were", "what",
    "when", "which", "who", "why", "will", "with", "you", "your",
}


# Words that are on topic for every article on
# the site. Two headlines sharing only these
# are two different stories about AI, not one
# story told twice, so a match has to rest on
# something more specific than this list.

GENERIC = {
    "ai", "model", "llm", "chatbot", "tech", "technology",
    "new", "first", "now", "more", "most", "best", "big",
    "company", "startup", "firm", "industry", "user",
    "report", "study", "say", "said", "claim", "warn",
    "launch", "release", "announce", "unveil", "reveal",
    "update", "add", "build", "make", "use", "using", "get",
    "could", "would", "may", "might", "here", "week", "year",
    "day", "today", "tool", "app", "data", "system", "way",
}


# A headline often ends with the name of the
# site that published it. That is the one word
# guaranteed to differ between two copies of
# the same story, so it goes.

PUBLISHER_TAIL = re.compile(
    r"\s+[|–—·-]\s+[^|–—·-]{1,30}$"
)


def strip_publisher_tail(title):

    stripped = PUBLISHER_TAIL.sub("", title)

    # Only if a real headline is left over. Some
    # titles genuinely read "Claude 3 - a review".
    if len(stripped.split()) >= 4:
        return stripped

    return title


def singular(word):

    # Crude on purpose: "agents" and "agent" have
    # to land on the same token, and nothing here
    # depends on the result being a real word.

    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]

    return word


def fingerprint(title):

    if not title:
        return frozenset()

    # Curly quotes and dashes, so "OpenAI's" and
    # "OpenAI's" tokenise the same way
    text = unicodedata.normalize("NFKD", title)

    text = strip_publisher_tail(text)

    text = re.sub(r"[^a-z0-9]+", " ", text.lower())

    return frozenset(
        singular(word)
        for word in text.split()
        if word not in STOPWORDS
    )


# -----------------------------------
# ARE THESE THE SAME STORY?
# -----------------------------------
#
# Two tests, because near duplicates come in
# two shapes.
#
# Jaccard, for two rewrites of one headline
# that are about the same length:
#
#     shared words / all words used
#
# Containment, for a short headline that a
# longer one simply spells out:
#
#     "OpenAI launches GPT-5"
#     "OpenAI launches GPT-5, its most capable
#      model yet"
#
#     shared words / words in the shorter one

JACCARD_THRESHOLD = 0.55

# Deliberately strict. Loosening this by even
# 0.05 starts folding "Introducing Grok 4.6"
# into "Grok 4.6 in Amazon Bedrock", and losing
# a real article costs more than showing two
# cards about one story.
CONTAINMENT_THRESHOLD = 0.8

# Below this a headline has too few words for
# either ratio to mean anything, so it has to
# match exactly.
MIN_TOKENS = 4

# However the ratios land, the overlap has to
# include real subject matter.
MIN_SHARED = 3

MIN_SHARED_SPECIFIC = 2

# Two headlines can score well on words alone
# and still be about different things:
#
#   "Google DeepMind unveils new weather model"
#   "Google DeepMind unveils new protein model"
#
# Five of seven words agree, and the two that
# do not are the entire story. So the words
# that carry meaning have to agree in their own
# right, not just help the total look good.
SPECIFIC_CONTAINMENT_THRESHOLD = 0.7

# The same story can take a couple of days to
# work its way around. Two months apart it is
# a different story that happens to rhyme.
MAX_DAYS_APART = 7


# -----------------------------------
# WHICH RELEASE IS THIS?
# -----------------------------------
#
# On an AI news site, the words separating two
# otherwise identical headlines are usually a
# version number or a model tier:
#
#   "Anthropic releases Claude Opus 4.5"
#   "Anthropic releases Claude Haiku 4.5"
#
# Getting those two wrong is the worst mistake
# this file can make, so when both headlines
# name a release and they name different ones,
# that settles it before any ratio is looked at.

# Written as singular() leaves them, which is
# why "opus" is spelled "opu" here.

MODEL_TIERS = {
    "opu", "sonnet", "haiku", "turbo", "mini", "nano",
    "pro", "ultra", "flash", "max", "lite", "preview",
    "instruct", "thinking", "reasoning",
}


def identifiers(words):

    return {
        word
        for word in words
        if any(character.isdigit() for character in word)
        or word in MODEL_TIERS
    }


def is_same_story(left, right):

    if not left or not right:
        return False

    if len(left) < MIN_TOKENS or len(right) < MIN_TOKENS:
        return left == right

    shared = left & right

    if len(shared) < MIN_SHARED:
        return False

    left_specific = left - GENERIC
    right_specific = right - GENERIC

    shared_specific = left_specific & right_specific

    if len(shared_specific) < MIN_SHARED_SPECIFIC:
        return False

    # Different release, different story
    left_ids = identifiers(left)
    right_ids = identifiers(right)

    if left_ids and right_ids and left_ids != right_ids:
        return False

    # One word apart, and it is the word doing all
    # the work:
    #
    #   "Hugging Face releases a new speech dataset"
    #   "Hugging Face releases a new vision dataset"
    #
    # Nobody rewrites a headline by changing a
    # single noun, so this is two stories filed
    # off the same template.
    if (
        len(left_specific - right_specific) == 1
        and len(right_specific - left_specific) == 1
    ):
        return False

    smallest_specific = min(
        len(left_specific),
        len(right_specific)
    )

    if not smallest_specific:
        return False

    specific_ratio = len(shared_specific) / smallest_specific

    if specific_ratio < SPECIFIC_CONTAINMENT_THRESHOLD:
        return False

    union = len(left | right)

    if union and len(shared) / union >= JACCARD_THRESHOLD:
        return True

    smaller = min(len(left), len(right))

    return len(shared) / smaller >= CONTAINMENT_THRESHOLD


def close_in_time(left, right):

    # An undated article is rare and gets the
    # benefit of the doubt
    if not left or not right:
        return True

    return abs(left - right) <= timedelta(days=MAX_DAYS_APART)


# -----------------------------------
# THE RUNNING SET
# -----------------------------------
#
# Comparing every article against every other
# one is quadratic, and most pairs share no
# words at all. So each kept story is filed
# under its own words, and a new story is only
# compared against the ones filed under a word
# it uses.

class Deduper:

    def __init__(self):

        self._urls = set()

        self._stories = []

        self._by_word = defaultdict(list)

        self.duplicates = 0


    def _candidates(self, words):

        seen = set()

        # Generic words are filed too, but they
        # match half the feed, so start from the
        # specific ones
        for word in (words - GENERIC) or words:

            for index in self._by_word.get(word, ()):
                seen.add(index)

        return seen


    def add(self, article, published=None):
        """
        Record an article, unless we already hold
        this story. Returns True when it is new.
        """

        url = canonical_url(article.get("url"))

        if url and url in self._urls:

            self.duplicates += 1
            return False

        words = fingerprint(article.get("title"))

        for index in self._candidates(words):

            other_words, other_date = self._stories[index]

            if not is_same_story(words, other_words):
                continue

            if not close_in_time(published, other_date):
                continue

            self.duplicates += 1
            return False

        if url:
            self._urls.add(url)

        index = len(self._stories)

        self._stories.append((words, published))

        for word in words:
            self._by_word[word].append(index)

        return True
