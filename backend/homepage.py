import re

from datetime import datetime, timedelta, timezone

from dedupe import fingerprint, identifiers, GENERIC


# -----------------------------------
# WHAT MATTERS RIGHT NOW
# -----------------------------------
#
# The three tabs have three different jobs:
#
#   Home        what matters right now
#   Companies   what each company is publishing
#   Discovery   what the wider field is talking about
#
# Companies and Discovery are archives, and they
# show everything they hold. Home is not: it is a
# front page, and a front page is a choice.
#
# So this layer sits on top of the store and picks.
# It never decides what gets kept — ingestion has
# already run, everything is still in the store,
# and every article this file passes over is one
# tab away. It only decides what earns the front
# page right now.
#
#     store -> score -> diversity -> top 20 -> Home
#
# Deliberately not a model. Every number below is
# a rule you can read, so when something turns up
# on Home there is an answer to why, and changing
# that answer means editing a constant rather than
# retraining anything.


# Three pages of six. The front page shows six at
# a time, so the selection is a multiple of that
# and no page ends up with a single orphan on it.
HOME_SELECTION = 18


# -----------------------------------
# 1. RECENCY
# -----------------------------------
#
# Halves every twenty hours. Something from this
# morning should beat yesterday outright, while a
# genuinely big story from yesterday can still hold
# the page against filler posted ten minutes ago.

RECENCY_WEIGHT = 45.0

RECENCY_HALF_LIFE_HOURS = 20.0


def recency_score(published, now):

    if not published:
        return 0.0

    hours = max(
        0.0,
        (now - published).total_seconds() / 3600.0
    )

    return RECENCY_WEIGHT * (
        0.5 ** (hours / RECENCY_HALF_LIFE_HOURS)
    )


# -----------------------------------
# 2. SOURCE
# -----------------------------------
#
# A company announcing its own work is the primary
# document. A newsroom reporting on it is second
# hand but edited. An aggregator is a link somebody
# upvoted, which is worth knowing and rarely worth
# the top of the page.

SOURCE_SCORES = {
    "company": 20.0,
    "publisher": 14.0,
    "aggregator": 6.0,
}


def source_score(article):

    return SOURCE_SCORES.get(
        article.get("source_tier"),
        SOURCE_SCORES["aggregator"]
    )


# -----------------------------------
# 3. IMPORTANCE
# -----------------------------------
#
# Read off the headline only. Descriptions are
# marketing copy often enough that they cost more
# in false positives than they pay back.
#
# Each rule fires once, however many of its
# patterns match, and the total is clamped so no
# single headline can win on keyword stuffing.

IMPORTANCE_CEILING = 30.0

IMPORTANCE_FLOOR = -20.0


IMPORTANCE_RULES = [

    # New models and product launches
    (16, [
        r"\bintroduc(?:ing|es|ed)\b",
        r"\bannounc(?:ing|es|ed)\b",
        r"\bunveil(?:s|ing|ed)?\b",
        r"\blaunch(?:es|ing|ed)?\b",
        r"\bdebuts?\b",
        r"\bnow available\b",
        r"\bgenerally available\b",
        r"\bopen[- ]?sourc(?:es|ing|ed)\b",
        r"\bopen[- ]weights?\b",
    ]),

    # Money
    (14, [
        r"\bacquir(?:es|ing|ed|ition)\b",
        r"\bbuys\b",
        r"\bmerger\b",
        r"\bipo\b",
        r"\brais(?:es|ing|ed)\b",
        r"\bfunding\b",
        r"\bvaluation\b",
        r"\bvalued at\b",
        r"\$\s?\d+(?:\.\d+)?\s?(?:b|bn|billion|m|mn|million|t|trillion)\b",
    ]),

    # Research that moved the line
    (12, [
        r"\bbreakthrough\b",
        r"\bstate[- ]of[- ]the[- ]art\b",
        r"\bsota\b",
        r"\boutperform(?:s|ing|ed)?\b",
        r"\bsurpass(?:es|ing|ed)?\b",
        r"\bbeats?\b",
        r"\bfirst\s+(?:ever|time)\b",
        r"\bsolv(?:es|ed)\b",
        r"\bnew benchmark\b",
    ]),

    # Who is working with whom
    (10, [
        r"\bpartner(?:s|ship|ships)\b",
        r"\bteams? up\b",
        r"\bjoins forces\b",
        r"\bstrikes? a deal\b",
    ]),

    # Who is running the place
    (10, [
        r"\bceo\b",
        r"\bco[- ]?founder\b",
        r"\bsteps? down\b",
        r"\bresign(?:s|ing|ed)?\b",
        r"\bquits?\b",
        r"\bjoins\b",
        r"\bappoint(?:s|ing|ed)?\b",
        r"\bousted\b",
        r"\blays? off\b",
        r"\blayoffs?\b",
    ]),

    # Consequences
    (8, [
        r"\blawsuit\b",
        r"\bsu(?:es|ing)\b",
        r"\bregulat(?:e|es|ion|ors?)\b",
        r"\bban(?:s|ned|ning)?\b",
        r"\binvestigat(?:es|ing|ion)\b",
        r"\bantitrust\b",
    ]),


    # ---- and the things that should sink ----

    # Documentation wearing a headline
    (-12, [
        r"\bhow to\b",
        r"\btutorial\b",
        r"\bguide\b",
        r"\btips\b",
        r"\bwalkthrough\b",
        r"\bgetting started\b",
        r"\bstep[- ]by[- ]step\b",
        r"\bcheat sheet\b",
    ]),

    # One person's afternoon
    (-10, [
        r"\bshow hn\b",
        r"\bask hn\b",
        r"\bopinion\b",
        r"\bwhy i\b",
        r"\bi built\b",
        r"\bi made\b",
        r"\bi tried\b",
        r"\bmy \w+ (?:experience|journey|take)\b",
        r"\bthoughts on\b",
        r"\blessons learned\b",
    ]),

    # Recurring columns
    (-8, [
        r"\bweekly\b",
        r"\bmonthly\b",
        r"\bround[- ]?up\b",
        r"\bdigest\b",
        r"\bnewsletter\b",
        r"\bthis week in\b",
        r"\bchangelog\b",
        r"\brelease notes\b",
        r"\bwhat we(?:'re| are) reading\b",
    ]),

    # Housekeeping
    (-6, [
        r"\bminor\b",
        r"\bsmall (?:update|change|fix)\b",
        r"\bpatch\b",
        r"\bbug ?fix(?:es)?\b",
        r"\bdeprecat(?:es|ed|ing|ion)\b",
    ]),
]


COMPILED_RULES = [
    (
        weight,
        re.compile("|".join(patterns), re.IGNORECASE)
    )
    for weight, patterns in IMPORTANCE_RULES
]


def importance_score(article):

    title = article.get("title") or ""

    if not title:
        return 0.0

    total = 0.0

    for weight, pattern in COMPILED_RULES:

        if pattern.search(title):
            total += weight

    return max(
        IMPORTANCE_FLOOR,
        min(IMPORTANCE_CEILING, total)
    )


# -----------------------------------
# THE SCORE
# -----------------------------------

def published_at(article):

    try:

        return datetime.fromisoformat(
            article.get("published") or ""
        )

    except ValueError:

        return None


def score_breakdown(article, now):
    """
    Every term that decided this article's place,
    so a front page can always be accounted for.
    """

    recency = recency_score(
        published_at(article),
        now
    )

    source = source_score(article)

    importance = importance_score(article)

    return {
        "recency": round(recency, 2),
        "source": round(source, 2),
        "importance": round(importance, 2),
        "total": round(recency + source + importance, 2),
    }


def total_score(article, now):

    return (
        recency_score(published_at(article), now)
        + source_score(article)
        + importance_score(article)
    )


# -----------------------------------
# 4. DIVERSITY
# -----------------------------------
#
# The failure this exists to prevent:
#
#   OpenAI
#   OpenAI
#   OpenAI
#   OpenAI
#   OpenAI
#   Anthropic
#
# Home is meant to read as what is happening in AI,
# not as today's busiest RSS feed. So a subject is
# capped, and the cap counts by who the story is
# about rather than who published it — five outlets
# covering one OpenAI launch is the same crowding
# as OpenAI posting five times.

# Two, not three. Three leaves room for a pair of
# write ups of one event to sit together where the
# word rules above could not tell they were the
# same — and a front page that visibly repeats
# itself is the exact failure this section exists
# to prevent. Reaching a little deeper for the
# twentieth article costs less than that.
MAX_PER_SUBJECT = 2


def subject_key(article):

    return (
        article.get("company_id")
        or article.get("related_company_id")
        or article.get("source")
        or article.get("via")
        or ""
    )


# -----------------------------------
# 5. THE SAME STORY TWICE
# -----------------------------------
#
# Ingestion has already dropped outright duplicates,
# and it is deliberately strict, because dropping a
# real article there loses it from the site.
#
# Nothing is lost here, so this is allowed to be
# suspicious: two headlines only have to be near
# each other to stop both taking front page space.
# The one that scored lower stays on its own tab.

HOME_OVERLAP = 0.6

MIN_SHARED_WORDS = 2


# Two newsrooms writing up one event rarely reuse
# each other's words, so plain overlap misses them:
#
#   "The AI researcher who just quit Anthropic says
#    it's crunch time for humanity"
#   "Anthropic researcher quits with a warning:
#    self-improving AI could kill everyone"
#
# Three words in common out of eight. But they are
# about the same company, hours apart, and those
# three words are the story. That combination is
# the signal plain overlap cannot see.

SAME_EVENT_SHARED_WORDS = 3

SAME_EVENT_DAYS = 2


def story_of(article):
    """
    Everything comparing two front page candidates
    needs: what the headline says, who it is about,
    and when it ran.
    """

    return {
        "words": fingerprint(article.get("title")),
        "subject": subject_key(article),
        "published": published_at(article),
    }


def close_in_time(left, right):

    if not left or not right:
        return True

    return abs(left - right) <= timedelta(days=SAME_EVENT_DAYS)


def covers_same_ground(left, right):

    left_words = left["words"]
    right_words = right["words"]

    if not left_words or not right_words:
        return False

    # A different release is a different story,
    # however alike the two headlines read
    left_ids = identifiers(left_words)
    right_ids = identifiers(right_words)

    if left_ids and right_ids and left_ids != right_ids:
        return False

    left_specific = left_words - GENERIC
    right_specific = right_words - GENERIC

    if not left_specific or not right_specific:
        return False

    shared = left_specific & right_specific

    if len(shared) < MIN_SHARED_WORDS:
        return False

    smallest = min(
        len(left_specific),
        len(right_specific)
    )

    # Two tellings of one headline
    if len(shared) / smallest >= HOME_OVERLAP:
        return True

    # Two newsrooms on one event
    return bool(
        left["subject"]
        and left["subject"] == right["subject"]
        and len(shared) >= SAME_EVENT_SHARED_WORDS
        and close_in_time(left["published"], right["published"])
    )


# -----------------------------------
# BUILD THE FRONT PAGE
# -----------------------------------

def curate(articles, limit=HOME_SELECTION, now=None):

    if now is None:
        now = datetime.now(timezone.utc)

    scored = [
        (total_score(article, now), article)
        for article in articles
    ]

    # Best first, and the newer story takes a tie.
    # Dates are ISO strings by now, so they sort
    # correctly as text.
    scored.sort(
        key=lambda pair: (
            pair[0],
            pair[1].get("published") or ""
        ),
        reverse=True
    )

    selected = []
    held_back = []

    counts = {}
    seen_stories = []

    for _, article in scored:

        if len(selected) >= limit:
            break

        key = subject_key(article)

        if counts.get(key, 0) >= MAX_PER_SUBJECT:

            held_back.append(article)
            continue

        story = story_of(article)

        already_covered = any(
            covers_same_ground(story, seen)
            for seen in seen_stories
        )

        if already_covered:

            held_back.append(article)
            continue

        selected.append(article)

        counts[key] = counts.get(key, 0) + 1

        seen_stories.append(story)

    # A quiet week can leave the rules holding back
    # more than they let through. A short front page
    # is worse than a slightly repetitive one, so
    # the best of what they stopped fills the rest.
    for article in held_back:

        if len(selected) >= limit:
            break

        selected.append(article)

    return selected
