import os
import sys
import time

from dotenv import load_dotenv

import db

from extract import extract


# -----------------------------------
# WRITE THE SUMMARY
# -----------------------------------
#
# Every article gets one, written when it first
# arrives rather than when somebody clicks it.
#
# Reading is meant to feel like opening a page,
# not like waiting for one to be written, and
# the work is the same either way: dedupe has
# already guaranteed one row per story, so this
# costs one summary per story however many
# people read it.
#
#     article URL -> extract -> model -> stored
#
# Runs on its own:
#
#     python summarize.py            everything outstanding
#     python summarize.py 20         at most twenty


ENV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".env"
)

load_dotenv(ENV_FILE)


API_KEY = (
    os.environ.get("GEMINI_API_KEY", "").strip()
    or os.environ.get("GOOGLE_API_KEY", "").strip()
)


# Gemini's Flash models are free to call, which
# is the whole reason for this choice.
#
# Not the newest one. On the free tier the newer
# a model is the smaller its daily allowance, and
# gemini-3.5-flash allows twenty requests a day --
# enough to summarise a twentieth of one day's
# ingest. The allowance matters more here than
# the last few points of quality, because an
# article that never gets summarised scores
# nothing at all.
#
# Overridable, because Google renames these often
# and the good name today is not the good name
# next year.

MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
).strip()


# Tried in order when the configured model will
# not answer -- because it has been renamed, or
# because it is briefly overloaded.
# Ordered by how much of them the free tier will
# give you, not by how good they are.
FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]


# The free tier answers 503 "high demand" and 429
# often enough that a run of a few hundred
# articles will meet both. Neither says anything
# is wrong with the request, so both are worth
# waiting out rather than recording as a failure.
RETRIES_PER_MODEL = 3

BACKOFF_SECONDS = 4


# Gemini's 3.x models reason before answering,
# and that reasoning is spent out of the same
# allowance as the answer. Left on, it ate 1149
# of 1200 tokens here and the summary stopped
# in the middle of its second sentence.
#
# Nothing in this task needs it. The article is
# right there in the prompt and the job is to
# retell it, so the thinking is turned off and
# the whole allowance goes to the summary.
#
# Kept generous anyway: a model that ignores the
# setting should still have room to finish.
MAX_OUTPUT_TOKENS = 4000


# The free tier is rate limited per minute, so
# the job paces itself rather than firing every
# article at once and collecting 429s.
PAUSE_SECONDS = float(os.environ.get("GEMINI_PAUSE", "1.5"))


# Below this the feed gave a blurb, not an
# article, and a summary of a blurb is worse than
# the blurb itself.
MIN_FEED_TEXT = 700


class NotConfigured(RuntimeError):
    pass


# -----------------------------------
# WHEN THE PAGE WILL NOT OPEN
# -----------------------------------
#
# Ars Technica answers every plain HTTP client
# with an AWS WAF JavaScript challenge, so its
# pages cannot be read at all -- twenty of the
# thirty-five articles we could not summarise
# were its. It is not a paywall and there is
# nothing to log into; the article is public, and
# its own feed hands over a thousand words of it.
#
# So when a page will not open, the feeds get
# asked. Built once per run and kept, because it
# is the same fifteen requests ingestion already
# makes and there is no sense repeating them per
# article.
#
# Only a fallback. A feed excerpt is shorter than
# the article, so the page is always tried first.

_feed_index = None


def build_feed_index():

    from news import feed_text
    from sources import all_sources
    from dedupe import canonical_url

    import feedparser

    index = {}

    for source in all_sources():

        if source["method"] != "rss":
            continue

        try:
            parsed = feedparser.parse(source["url"])

        except Exception:
            continue

        for entry in parsed.entries:

            link = entry.get("link")

            if not link:
                continue

            text = feed_text(entry)

            if len(text) >= MIN_FEED_TEXT:
                index[canonical_url(link)] = text

    return index


def from_feed(url):
    """
    The article as its feed gave it, or "" when
    no feed carried enough of it.
    """

    global _feed_index

    if _feed_index is None:

        try:
            _feed_index = build_feed_index()

            print(
                f"  (feeds carry the text of "
                f"{len(_feed_index)} articles)",
                flush=True
            )

        except Exception as error:

            print(f"  (could not read the feeds: {error})", flush=True)

            _feed_index = {}

    from dedupe import canonical_url

    return _feed_index.get(canonical_url(url), "")


_client = None


def configured():

    return bool(API_KEY)


def client():

    global _client

    if _client is not None:
        return _client

    if not configured():

        raise NotConfigured(
            "GEMINI_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/apikey "
            "and add it to backend/.env"
        )

    try:
        from google import genai

    except ImportError as error:

        raise NotConfigured(
            f"The google-genai package is not installed: {error}. "
            "Run: pip install -r requirements.txt"
        ) from error

    _client = genai.Client(api_key=API_KEY)

    return _client


# -----------------------------------
# THE PROMPT
# -----------------------------------
#
# Two rules do most of the work here.
#
# The summary has to stand on its own, because
# the whole point is that a reader does not have
# to open the original to find out what happened.
# So it carries the actual claims -- the numbers,
# the names, what changed -- rather than
# describing the article from the outside.
#
# And it must not editorialise. This sits under a
# masthead, and a summary that argues with its
# source is a different product.

SYSTEM = """You write article summaries for SIGNAL, an AI news reader.

Your summary REPLACES the article for most readers, so it must be
complete enough to leave them genuinely informed. Someone who reads
only your summary should know what happened, who is involved, what
the specifics are, and why it matters.

Rules:
- 150-250 words. Never shorter than 150.
- Two or three short paragraphs, separated by a blank line.
- Carry the concrete detail: names, numbers, model versions, dollar
  amounts, dates, benchmark results. These are the point. Never write
  "significant funding" when the article says "$300 million".
- Open with what actually happened, not with throat-clearing. Never
  begin "This article discusses" or "The piece explores".
- Report, do not editorialise. No opinions of your own, no advice to
  the reader, no closing thought about what the future holds.
- Write plainly, in the register of a good newsroom.

Formatting - use Markdown, sparingly and with intent:
- **Bold** only the few things that carry the story: the product or
  model name, the organisation at the centre of it, the single most
  decisive number. At most five or six spans in the whole summary.
  Bold on every proper noun is noise and defeats the point.
- *Italics* for a genuine quoted phrase from the source, or a term
  being introduced. Rarer than bold.
- No headings, no bullet lists, no links. Prose only.

Return only the summary itself. No preamble, no title, no sign-off."""


def prompt_for(article, body):

    return (
        f"Headline: {article.get('title')}\n"
        f"Publication: {article.get('source')}\n\n"
        f"Article text:\n{body}\n\n"
        "Write the summary."
    )


# -----------------------------------
# ONE ARTICLE
# -----------------------------------

def ask_model(article, body, model=None, thinking=False):

    from google.genai import types

    settings = {
        "system_instruction": SYSTEM,

        # Reporting, not writing. Low, but not
        # zero: at zero the model leans on the
        # article's own sentences.
        "temperature": 0.3,

        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }

    if not thinking:

        settings["thinking_config"] = types.ThinkingConfig(
            thinking_budget=0
        )

    response = client().models.generate_content(
        model=model or MODEL,
        contents=prompt_for(article, body),
        config=types.GenerateContentConfig(**settings),
    )

    # A summary that stops mid-sentence is worse
    # than none: it would be stored, shown, and
    # never looked at again. Better to record it
    # as a failure and let the retry catch it.
    if _ran_out_of_room(response):

        raise RuntimeError(
            "the summary was cut off before it finished"
        )

    return (response.text or "").strip()


def _ran_out_of_room(response):

    try:
        reason = str(response.candidates[0].finish_reason)

    except (AttributeError, IndexError):
        return False

    return "MAX_TOKENS" in reason


def summarize(article):
    """
    (summary, status, error) for one article.

    Never raises. A story we cannot summarise is
    an ordinary outcome, and the article stays on
    the site either way.
    """

    body, problem = extract(article["url"])

    # The page would not be read. Some publishers
    # carry the article in their own feed anyway,
    # so that is not the end of the road.
    if problem:

        carried = from_feed(article["url"])

        if carried:
            body, problem = carried, None

        else:
            return None, "thin", problem

    text, error = ask_with_retry(article, body)

    if error:
        return None, "failed", error

    if not text:
        return None, "failed", "the model returned nothing"

    return text, "ok", None


def ask_with_retry(article, body):
    """
    Work down the models, waiting out the
    temporary refusals and moving on from the
    permanent ones.
    """

    models = [MODEL] + [
        name for name in FALLBACK_MODELS
        if name != MODEL
    ]

    last_error = None

    for index, model in enumerate(models):

        for attempt in range(RETRIES_PER_MODEL):

            try:
                text = ask_model(article, body, model)

                if index:
                    print(f"    (used {model})", flush=True)

                return text, None

            except Exception as error:

                last_error = f"{type(error).__name__}: {error}"

                # Gone or renamed: no amount of
                # waiting brings it back
                if _is_model_error(last_error):
                    break

                # Today's allowance for this model
                # is spent. Waiting will not bring
                # it back either.
                if _is_daily_quota(last_error):
                    break

                # A model that will not be told not
                # to think. Ask again and let it,
                # and rely on the allowance being
                # large enough to finish anyway.
                if _rejected_config(last_error):

                    try:
                        return ask_model(
                            article, body, model, thinking=True
                        ), None

                    except Exception as second:

                        last_error = f"{type(second).__name__}: {second}"

                        break

                if not _is_transient(last_error):
                    return None, last_error

                # Busy. Wait longer each time, and
                # not at all after the last try,
                # because the next model is next.
                if attempt < RETRIES_PER_MODEL - 1:
                    time.sleep(BACKOFF_SECONDS * (attempt + 1))

    return None, last_error


# Nothing is wrong with the request; the far end
# is just busy or we have gone too fast.
TRANSIENT_SIGNS = (
    "503", "unavailable", "high demand", "overloaded",
    "429", "resource_exhausted", "rate limit",
    "500", "internal", "timeout", "deadline",
)


def _is_transient(message):

    lowered = message.lower()

    return any(sign in lowered for sign in TRANSIENT_SIGNS)


# A per-minute limit is worth waiting out. A daily
# one is not: nothing changes for hours, so the
# only useful move is the next model.

def _is_daily_quota(message):

    lowered = message.lower()

    return "perday" in lowered or "per day" in lowered


# Some models refuse to be told not to think, and
# say so only as "invalid argument". Worth one
# more go with thinking left on rather than
# writing the article off.

def _rejected_config(message):

    lowered = message.lower()

    return "invalid_argument" in lowered or "invalid argument" in lowered


def _is_model_error(message):

    lowered = message.lower()

    return (
        "not found" in lowered
        or "404" in lowered
        or "not supported" in lowered
    )


# -----------------------------------
# THE JOB
# -----------------------------------

def run(limit=None, verbose=True):

    done = {"ok": 0, "thin": 0, "failed": 0}

    while True:

        batch = db.articles_needing_summary(
            limit=min(limit, 50) if limit else 50
        )

        if not batch:
            break

        for row in batch:

            summary, status, error = summarize(row)

            db.save_summary(
                row["id"],
                summary,
                status,
                model=MODEL if status == "ok" else None,
                error=error,
                attempts=row.get("summary_attempts") or 0,
            )

            done[status] = done.get(status, 0) + 1

            if verbose:

                mark = {"ok": "+", "thin": "~", "failed": "!"}[status]

                note = "" if status == "ok" else f"  ({error})"

                # Flushed, because this is a job
                # people watch. Redirected to a
                # file Python buffers by default,
                # and a log that stays empty for
                # ten minutes looks like a hang.
                print(f"  {mark} {row['title'][:58]}{note}", flush=True)

            total = sum(done.values())

            if limit and total >= limit:
                return done

            time.sleep(PAUSE_SECONDS)

    return done


def retry_unreadable():
    """
    Put the articles we could not read back in
    the queue.

    "thin" means the page would not open, which
    is usually permanent -- but not always. When
    a new way of reading a source is added, the
    articles it already gave up on are exactly
    the ones worth trying again.
    """

    supabase = db.client()

    response = (
        supabase.table(db.ARTICLES)
        .update({"summary_status": "pending", "summary_attempts": 0})
        .eq("summary_status", "thin")
        .gte("published", db.cutoff(90))
        .execute()
    )

    return len(response.data or [])


USAGE = """Usage:
  python summarize.py            write every summary still outstanding
  python summarize.py 20         stop after twenty
  python summarize.py --retry-thin   try the pages that would not open again
"""


def main():

    limit = None
    retry = False

    for argument in sys.argv[1:]:

        if argument == "--retry-thin":
            retry = True

        elif argument in ("-h", "--help"):
            print(USAGE)
            return 0

        else:

            try:
                limit = int(argument)

            except ValueError:
                print(f"Not a number: {argument}\n\n{USAGE}")
                return 1

    if not db.configured():
        print("The database is not configured. See backend/.env")
        return 1

    if not configured():
        print(
            "GEMINI_API_KEY is not set.\n"
            "Get a free key at https://aistudio.google.com/apikey "
            "and add it to backend/.env"
        )
        return 1

    if retry:

        requeued = retry_unreadable()

        print(f"Queued {requeued} unreadable articles to try again\n")

    print(f"Summarising with {MODEL}\n", flush=True)

    done = run(limit)

    print(
        f"\n{done['ok']} written, "
        f"{done['thin']} had no readable article, "
        f"{done['failed']} failed"
    )

    tally = db.summary_counts()

    print(
        f"Store now: {tally['ok']} summarised, "
        f"{tally['pending']} pending, "
        f"{tally['thin']} unreadable, "
        f"{tally['failed']} failed"
    )

    return 0


if __name__ == "__main__":

    sys.exit(main())
