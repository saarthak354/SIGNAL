"""
Start both halves of SIGNAL from one terminal.

    python dev.py

    backend    http://127.0.0.1:5050    Flask, the API
    frontend   http://127.0.0.1:5500    the site

Ctrl+C stops both.

This only starts things. Neither half knows it
exists, and nothing here changes how either one
behaves: the backend is still the API on its own
port, the frontend is still static files on
theirs, and they still talk over CORS exactly as
they do when started by hand.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time


ROOT = os.path.dirname(os.path.abspath(__file__))

BACKEND = os.path.join(ROOT, "backend")

FRONTEND = os.path.join(ROOT, "frontend")


BACKEND_PORT = 5050

FRONTEND_PORT = 5500


HOST = "127.0.0.1"


# -----------------------------------
# WHAT TO START
# -----------------------------------
#
# The same two commands that would otherwise be
# typed into two terminals.

SERVICES = [
    {
        "name": "backend",
        "command": [sys.executable, "main.py"],
        "cwd": BACKEND,
        "port": BACKEND_PORT,
        "colour": "36",
    },
    {
        "name": "frontend",
        "command": [
            sys.executable, "-m", "http.server",
            str(FRONTEND_PORT),
            "--bind", HOST,
        ],
        "cwd": FRONTEND,
        "port": FRONTEND_PORT,
        "colour": "35",
    },
]


# -----------------------------------
# WHEN TO STOP
# -----------------------------------
#
# Set by a signal handler rather than left to
# KeyboardInterrupt on its own.
#
# Python only raises that if its own SIGINT
# handler is installed, and it declines to
# install one when the signal arrives already
# ignored -- which is what a process inherits
# when it is started in the background by a
# non-interactive shell, or under some
# supervisors. Handling it here means the same
# shutdown runs whether the signal came from
# Ctrl+C, from kill, or from whatever started
# this.
#
# SIGTERM is taken as well, so being asked to
# stop politely also stops both servers rather
# than leaving them parented to nothing.

STOPPING = threading.Event()


def on_signal(number, frame):

    STOPPING.set()


USE_COLOUR = sys.stdout.isatty()


def paint(text, colour):

    if not USE_COLOUR:
        return text

    return f"\033[{colour}m{text}\033[0m"


def announce(message):

    print(paint(f"[dev]      {message}", "1"), flush=True)


# -----------------------------------
# IS THE PORT FREE?
# -----------------------------------
#
# Checked before anything starts, because half a
# stack coming up is more confusing than none of
# it: the site would load and then fail on every
# request, or the API would answer while the page
# serving it was the one that never started.

def in_use(port):

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    with probe:

        probe.settimeout(0.5)

        return probe.connect_ex((HOST, port)) == 0


def check_ports():

    taken = [
        service for service in SERVICES
        if in_use(service["port"])
    ]

    if not taken:
        return True

    for service in taken:

        announce(
            f"port {service['port']} is already in use, "
            f"so the {service['name']} cannot start."
        )

    announce(
        "Stop whatever is holding it and try again. "
        "To find it:"
    )

    ports = " ".join(str(s["port"]) for s in taken)

    announce(f"    lsof -ti :{ports.replace(' ', ' -ti :')}")

    return False


# -----------------------------------
# RELAY OUTPUT
# -----------------------------------
#
# Two servers share one terminal, so every line
# says which one it came from.

def relay(service, stream):

    label = paint(
        f"[{service['name']:<8}]",
        service["colour"]
    )

    for line in stream:
        print(f"{label} {line.rstrip()}", flush=True)


# -----------------------------------
# START AND STOP
# -----------------------------------

def start(service):

    environment = os.environ.copy()

    # Otherwise the child buffers its output and
    # the terminal stays silent until it exits
    environment["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        service["command"],
        cwd=service["cwd"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=environment,

        # Its own process group, for two reasons.
        #
        # Ctrl+C would otherwise be delivered by
        # the terminal to every process at once,
        # and each would tear itself down while
        # this script was still trying to do it
        # in order.
        #
        # And Flask in debug mode runs a reloader,
        # which means the process started here is
        # a parent with a child of its own. A group
        # is what makes it possible to stop both.
        start_new_session=True,
    )

    service["process"] = process

    thread = threading.Thread(
        target=relay,
        args=(service, process.stdout),
        daemon=True,
    )

    thread.start()

    return process


def stop(service):

    process = service.get("process")

    if not process or process.poll() is not None:
        return

    announce(f"stopping the {service['name']}")

    try:

        # The group, not the process, so the
        # reloader child goes too
        os.killpg(
            os.getpgid(process.pid),
            signal.SIGTERM
        )

    except (ProcessLookupError, PermissionError, AttributeError):

        # Already gone, or a platform without
        # process groups
        process.terminate()

    try:
        process.wait(timeout=5)

    except subprocess.TimeoutExpired:

        announce(
            f"the {service['name']} did not stop, closing it the hard way"
        )

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)

        except (ProcessLookupError, PermissionError, AttributeError):
            process.kill()


def stop_everything():

    for service in reversed(SERVICES):
        stop(service)


# -----------------------------------
# RUN
# -----------------------------------

def main():

    if not check_ports():
        return 1

    for service in SERVICES:

        start(service)

        announce(
            f"{service['name']} on http://{HOST}:{service['port']}"
        )

    announce(f"open http://{HOST}:{FRONTEND_PORT}")
    announce("Ctrl+C stops both")

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:

        # Neither one is expected to finish. If
        # one does, the other is left serving half
        # an application, so it comes down too.
        while not STOPPING.is_set():

            for service in SERVICES:

                code = service["process"].poll()

                if code is None:
                    continue

                announce(
                    f"the {service['name']} exited on its own "
                    f"(code {code}), stopping the rest"
                )

                return code or 1

            STOPPING.wait(0.3)

    except KeyboardInterrupt:
        pass

    finally:

        # The terminal prints ^C without a newline
        print(flush=True)

        announce("shutting down")

        stop_everything()

    return 0


if __name__ == "__main__":

    sys.exit(main())
