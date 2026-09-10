import json
import os
import threading

from datetime import datetime, timezone

import db


# -----------------------------------
# WHERE SUBMISSIONS GO
# -----------------------------------
#
# Into the database, as rows.
#
# The file underneath is what they used to be:
# one JSON object per line, append only. It is
# kept as the place a submission lands when the
# database cannot take it, because somebody took
# the trouble to write to us and a failed insert
# is not a good enough reason to lose it. Run
# migrate_submissions.py to move anything that
# collected there into the table.

DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data"
)

SUBMISSIONS_FILE = os.path.join(
    DATA_DIR,
    "submissions.jsonl"
)


FORM_TYPES = {
    "feedback",
    "source",
}

MAX_NAME = 100

MAX_MESSAGE = 2000


_lock = threading.Lock()


# -----------------------------------
# VALIDATE
# -----------------------------------

def validate(payload):

    if not isinstance(payload, dict):
        return None, "Expected an object."

    form_type = str(payload.get("type", "")).strip()

    if form_type not in FORM_TYPES:
        return None, "Unknown form."

    name = str(payload.get("name", "")).strip()

    message = str(payload.get("message", "")).strip()

    if not name:
        return None, "Please add your name."

    if not message:
        return None, "Please add a message."

    return {
        "type": form_type,
        "name": name[:MAX_NAME],
        "message": message[:MAX_MESSAGE],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }, None


# -----------------------------------
# STORE
# -----------------------------------

def save(entry):

    if db.configured():

        try:
            return db.save_submission(entry)

        except Exception as error:

            print(
                f"Submission could not be stored, "
                f"falling back to the file: "
                f"{type(error).__name__}: {error}"
            )

    append(entry)

    return entry


def append(entry):

    os.makedirs(DATA_DIR, exist_ok=True)

    line = json.dumps(entry, ensure_ascii=False)

    # Two visitors can submit at the same moment
    with _lock:

        with open(SUBMISSIONS_FILE, "a", encoding="utf-8") as handle:

            handle.write(line + "\n")

    return entry
