#!/usr/bin/env python3
"""
Whiskey Button — Raspberry Pi gravity-feed whiskey dispenser controller.

Monitors a push-button on a GPIO pin. Each press activates a relay for a
configurable duration to open a gravity-feed valve and pour a measure of
whiskey.  Usage is limited to a configurable number of pours per day, with
the counter resetting at a configurable hour each morning.

State is persisted to disk so that power failures / reboots cannot reset
the daily count.
"""

import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import RPi.GPIO as GPIO

# ---------------------------------------------------------------------------
# Configuration — change these to match your wiring and preferences
# ---------------------------------------------------------------------------

BUTTON_PIN = 17          # BCM pin number for the push-button
RELAY_PIN = 27           # BCM pin number for the relay IN signal
POUR_DURATION = 2        # seconds the relay (valve) stays open per pour
MAX_POURS_PER_DAY = 20    # pours allowed before lockout
RESET_HOUR = 6           # hour (0-23) when the daily counter resets
RELAY_ACTIVE_HIGH = True # True  = HIGH signal activates relay (jumper → H)
                         # False = LOW signal activates relay  (jumper → L)
DEBOUNCE_MS = 300        # button debounce time in milliseconds

STATE_FILE = "/var/lib/whiskey-button/state.json"

FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "")
REMOTE_POLL_INTERVAL = 10  # seconds between remote-reset checks

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _current_pour_date() -> str:
    """Return the 'pour date' string for right now.

    The pour date rolls over at RESET_HOUR, not at midnight.  So 02:00 on
    April 13 still belongs to the April 12 pour window.
    """
    now = datetime.now()
    if now.hour < RESET_HOUR:
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def load_state() -> dict:
    """Load persisted state from disk, returning a safe default on any error."""
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        if "date" in state and "count" in state:
            state.setdefault("last_reset_at", 0)
            return state
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return {"date": _current_pour_date(), "count": 0, "last_reset_at": 0}


def save_state(state: dict) -> None:
    """Atomically write state to disk (write-then-rename)."""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


def get_pour_count() -> int:
    """Return how many pours have been used in the current pour window."""
    state = load_state()
    if state["date"] != _current_pour_date():
        state = {"date": _current_pour_date(), "count": 0}
        save_state(state)
    return state["count"]


def record_pour() -> int:
    """Increment the pour counter and persist.  Returns the new count."""
    state = load_state()
    today = _current_pour_date()
    if state["date"] != today:
        state = {"date": today, "count": 0}
    state["count"] += 1
    save_state(state)
    return state["count"]

# ---------------------------------------------------------------------------
# Remote reset
# ---------------------------------------------------------------------------

def check_remote_reset() -> None:
    """Poll Firebase for a reset signal and zero the counter if one is found."""
    if not FIREBASE_DB_URL:
        return
    url = FIREBASE_DB_URL.rstrip("/") + "/reset.json"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TypeError):
        return

    if not data or "resetAt" not in data:
        return

    remote_ts = data["resetAt"]
    state = load_state()
    if remote_ts > state.get("last_reset_at", 0):
        state["count"] = 0
        state["date"] = _current_pour_date()
        state["last_reset_at"] = remote_ts
        save_state(state)
        remaining = MAX_POURS_PER_DAY
        print(f"[{datetime.now():%H:%M:%S}] Remote reset received — {remaining} pour(s) available.")
        _confirm_reset(remote_ts)


def _confirm_reset(reset_ts: int) -> None:
    """Write an acknowledgment back to Firebase so the dashboard can confirm."""
    url = FIREBASE_DB_URL.rstrip("/") + "/reset.json"
    payload = json.dumps({"resetAt": reset_ts, "confirmedAt": int(time.time() * 1000)}).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="PUT")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except (urllib.error.URLError, OSError):
        print(f"[{datetime.now():%H:%M:%S}] Could not send reset confirmation to Firebase.")


# ---------------------------------------------------------------------------
# Relay helpers
# ---------------------------------------------------------------------------

def relay_on() -> None:
    GPIO.output(RELAY_PIN, GPIO.HIGH if RELAY_ACTIVE_HIGH else GPIO.LOW)


def relay_off() -> None:
    GPIO.output(RELAY_PIN, GPIO.LOW if RELAY_ACTIVE_HIGH else GPIO.HIGH)

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup(_signum=None, _frame=None) -> None:
    """Ensure the relay is off and GPIO is released before exiting."""
    try:
        relay_off()
        GPIO.cleanup()
    except Exception:
        pass
    sys.exit(0)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def pour_whiskey() -> None:
    """Execute one pour cycle: relay on → wait → relay off."""
    print(f"[{datetime.now():%H:%M:%S}] Pouring for {POUR_DURATION}s …")
    relay_on()
    time.sleep(POUR_DURATION)
    relay_off()
    print(f"[{datetime.now():%H:%M:%S}] Done.")


COOLDOWN_SECONDS = 30
_pour_lock = threading.Lock()
_last_pour_time = 0.0

def on_button_press(_channel) -> None:
    """Callback fired on button press (falling edge)."""
    global _last_pour_time

    # Verify the pin is genuinely low (pressed) — not a noise glitch from
    # WiFi/power fluctuations that the edge detector picked up.
    time.sleep(0.02)
    if GPIO.input(BUTTON_PIN) != GPIO.LOW:
        return

    if not _pour_lock.acquire(blocking=False):
        return
    try:
        now = time.monotonic()
        if now - _last_pour_time < COOLDOWN_SECONDS:
            return

        count = get_pour_count()
        remaining = MAX_POURS_PER_DAY - count

        if remaining <= 0:
            print(f"[{datetime.now():%H:%M:%S}] Limit reached — suspended until {RESET_HOUR:02d}:00 tomorrow.")
            return

        _last_pour_time = now
        pour_whiskey()
        new_count = record_pour()
        left = MAX_POURS_PER_DAY - new_count
        print(f"[{datetime.now():%H:%M:%S}] Pours used today: {new_count}/{MAX_POURS_PER_DAY} ({left} remaining)")
    finally:
        _pour_lock.release()


def main() -> None:
    # Ensure the state directory exists
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)

    # Register cleanup on normal exit and common signals
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # GPIO setup
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    relay_off()

    # Edge-detect on the button (falling edge because of internal pull-up)
    GPIO.add_event_detect(
        BUTTON_PIN,
        GPIO.FALLING,
        callback=on_button_press,
        bouncetime=DEBOUNCE_MS,
    )

    count = get_pour_count()
    remaining = MAX_POURS_PER_DAY - count
    print(f"Whiskey Button ready — {remaining} pour(s) remaining today.")
    print(f"  Button GPIO : {BUTTON_PIN}")
    print(f"  Relay GPIO  : {RELAY_PIN}")
    print(f"  Pour time   : {POUR_DURATION}s")
    print(f"  Daily limit : {MAX_POURS_PER_DAY}")
    print(f"  Resets at   : {RESET_HOUR:02d}:00")
    if FIREBASE_DB_URL:
        print(f"  Remote reset: {FIREBASE_DB_URL}")
    else:
        print(f"  Remote reset: disabled (FIREBASE_DB_URL not set)")

    try:
        while True:
            time.sleep(REMOTE_POLL_INTERVAL)
            get_pour_count()           # day-rollover bookkeeping
            check_remote_reset()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
