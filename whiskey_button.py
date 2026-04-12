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
import time
from datetime import datetime, timedelta
from pathlib import Path

import RPi.GPIO as GPIO

# ---------------------------------------------------------------------------
# Configuration — change these to match your wiring and preferences
# ---------------------------------------------------------------------------

BUTTON_PIN = 17          # BCM pin number for the push-button
RELAY_PIN = 27           # BCM pin number for the relay IN signal
POUR_DURATION = 2        # seconds the relay (valve) stays open per pour
MAX_POURS_PER_DAY = 2    # pours allowed before lockout
RESET_HOUR = 6           # hour (0-23) when the daily counter resets
RELAY_ACTIVE_HIGH = True # True  = HIGH signal activates relay (jumper → H)
                         # False = LOW signal activates relay  (jumper → L)
DEBOUNCE_MS = 300        # button debounce time in milliseconds

STATE_FILE = "/var/lib/whiskey-button/state.json"

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
            return state
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return {"date": _current_pour_date(), "count": 0}


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


def on_button_press(_channel) -> None:
    """Callback fired on button press (falling edge)."""
    count = get_pour_count()
    remaining = MAX_POURS_PER_DAY - count

    if remaining <= 0:
        print(f"[{datetime.now():%H:%M:%S}] Limit reached — suspended until {RESET_HOUR:02d}:00 tomorrow.")
        return

    pour_whiskey()
    new_count = record_pour()
    left = MAX_POURS_PER_DAY - new_count
    print(f"[{datetime.now():%H:%M:%S}] Pours used today: {new_count}/{MAX_POURS_PER_DAY} ({left} remaining)")


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

    # Keep the process alive; wake once a minute to check for day rollover
    try:
        while True:
            time.sleep(60)
            # Silent daily reset when the clock passes RESET_HOUR
            if get_pour_count() == 0:
                pass  # already reset
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
