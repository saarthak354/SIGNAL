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

import sys

import db

from ingest import refresh


def main():

    if not db.configured():

        print(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY are not set, "
            "so there is nowhere to write to.\n"
            "Copy .env.example to .env and fill them in."
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

    return 0


if __name__ == "__main__":

    sys.exit(main())
