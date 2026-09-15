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
# The file underneath is only for a backend with
# no database behind it -- running on a laptop
# without Supabase. There it is the store.
#
# It used to double as a fallback when a database
# insert failed, which was the wrong call once the
# API moved to a host. Render's disk is wiped on
# every deploy, restart and sleep, so a submission
# written there was as good as lost -- while the
# person who sent it was told it had arrived.
#
# Now a failed insert fails out loud. The form
# says so and keeps what they typed, so trying
# again costs them one click, and nothing is
# promised that was not kept.

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

class SubmissionNotSaved(RuntimeError):
    pass


def save(entry):

    # No database at all: the file is the store
    if not db.configured():
        return append(entry)

    try:
        return db.save_submission(entry)

    except Exception as error:

        # The type and the reason, not the message
        # or the name. Nothing is lost by leaving
        # them out -- the form keeps them for the
        # retry -- and logs are the wrong place for
        # what people write to us.
        print(
            f"SUBMISSION NOT SAVED ({entry.get('type')}): "
            f"{type(error).__name__}: {error}",
            flush=True
        )

        raise SubmissionNotSaved(str(error)) from error


def append(entry):

    os.makedirs(DATA_DIR, exist_ok=True)

    line = json.dumps(entry, ensure_ascii=False)

    # Two visitors can submit at the same moment
    with _lock:

        with open(SUBMISSIONS_FILE, "a", encoding="utf-8") as handle:

            handle.write(line + "\n")

    return entry
