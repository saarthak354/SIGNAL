"""
Go out to the sources and write what they have
into the store.

    python refresh.py

Nothing else needs to run for this to work, and
nothing waits on it. The site reads the store,
so this is the only thing that ever has to talk
to the feeds — which makes it the thing to put
on a schedule:

    */10 * * * *  cd /path/to/backend && python refresh.py
"""

import os
import sys

import db
import summarize

from ingest import refresh


def missing_settings_advice():
    """
    Where the missing values are meant to come
    from, which depends on where this is running.
    Telling a GitHub Actions run to copy
    .env.example is advice it cannot follow.
    """

    if os.environ.get("GITHUB_ACTIONS") == "true":

        return (
            "This is running in GitHub Actions, where the values come "
            "from repository secrets.\n"
            "Add SUPABASE_URL, SUPABASE_SERVICE_KEY and GEMINI_API_KEY under "
            "Settings -> Secrets and variables -> Actions -> "
            "New repository secret."
        )

    return "Copy .env.example to .env and fill them in."


def main():

    if not db.configured():

        # Named individually, because "both are not
        # set" hides which one was actually missed
        missing = [
            name for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
            if not os.environ.get(name, "").strip()
        ]

        print(
            f"Missing: {', '.join(missing) or 'SUPABASE_URL / SUPABASE_SERVICE_KEY'} "
            f"-- there is nowhere to write to.\n"
            f"{missing_settings_advice()}",
            flush=True
        )

        return 1

    refresh()

    run = db.latest_run()

    if not run:

        print("The run was not recorded.")

        return 1

    for failure in run.get("errors") or []:

        print(f"  {failure['source']}: {failure['error']}")

    print(
        f"{run['ingested']} entries seen, "
        f"{run['kept']} kept, "
        f"{run['inserted']} new, "
        f"{run['refreshed']} still live, "
        f"{run['replaced']} replaced by a better source"
    )

    # Written here rather than when a reader opens
    # the article, so opening one is a database
    # read and nothing else.
    if not summarize.configured():

        print(
            "\nGEMINI_API_KEY is not set, so nothing was summarised.\n"
            "Get a free key at https://aistudio.google.com/apikey"
        )

        return 0

    print("\nSummarising what is new")

    done = summarize.run()

    print(
        f"{done['ok']} written, "
        f"{done['thin']} had no readable article, "
        f"{done['failed']} failed"
    )

    return 0


if __name__ == "__main__":

    sys.exit(main())
