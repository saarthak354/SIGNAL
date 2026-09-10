"""
Move the submissions that collected in
data/submissions.jsonl into the database.

    python migrate_submissions.py

Safe to run twice: a submission already in the
table is left alone, matched on who wrote it and
when. The file is not deleted, so this can be
checked before anything is thrown away.
"""

import json
import sys

import db

from submissions import SUBMISSIONS_FILE, validate


def read_file():

    entries = []

    try:
        handle = open(SUBMISSIONS_FILE, encoding="utf-8")

    except FileNotFoundError:

        return entries

    with handle:

        for number, line in enumerate(handle, start=1):

            line = line.strip()

            if not line:
                continue

            try:
                payload = json.loads(line)

            except json.JSONDecodeError as error:

                print(f"  line {number}: unreadable, skipped ({error})")
                continue

            entry, problem = validate(payload)

            if problem:

                print(f"  line {number}: {problem}, skipped")
                continue

            # validate() stamps the current time,
            # and the point here is to keep the
            # time it was actually written
            entry["submitted_at"] = payload.get(
                "submitted_at",
                entry["submitted_at"]
            )

            entries.append(entry)

    return entries


def already_stored():

    supabase = db.client()

    response = (
        supabase.table(db.SUBMISSIONS)
        .select("name, submitted_at")
        .execute()
    )

    return {
        (row["name"], row["submitted_at"])
        for row in response.data or []
    }


def main():

    if not db.configured():

        print(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY are not set.\n"
            "Copy .env.example to .env and fill them in."
        )

        return 1

    entries = read_file()

    if not entries:

        print(f"Nothing to migrate from {SUBMISSIONS_FILE}")

        return 0

    stored = already_stored()

    moved = 0

    for entry in entries:

        # Postgres and Python format the same
        # instant differently, so compare on the
        # second rather than the character
        key = (entry["name"], entry["submitted_at"])

        if key in stored or any(
            name == entry["name"]
            and stamp[:19] == entry["submitted_at"][:19]
            for name, stamp in stored
        ):

            print(f"  already stored: {entry['name']}")
            continue

        db.save_submission(entry)

        moved += 1

        print(f"  moved: {entry['name']} ({entry['type']})")

    print(
        f"\n{moved} of {len(entries)} moved into the database. "
        f"{SUBMISSIONS_FILE} has been left where it is."
    )

    return 0


if __name__ == "__main__":

    sys.exit(main())
