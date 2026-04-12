# Whiskey Button

My mom lives in an old-age home and she enjoys a whiskey. The trouble is she
tends to overdo it, and at her age that means a real risk of a fall. The only
other option was having the nurses control her bottle, and I didn't want
that -- nobody should have to ask permission to have a drink in their own
room.

So I built her a button. One press, a perfect double. She gets two a day,
and then it quietly locks itself out until six the next morning. She keeps
her dignity, I sleep a little easier, and nobody has to play gatekeeper.

A Raspberry Pi, a relay board, a gravity-feed solenoid valve, and a bit of
Python. That's all it took.

## How It Works

1. Press the button → relay opens the valve for 2 seconds → whiskey pours.
2. You get **2 pours per day**.
3. After that the button is locked out until **06:00 the next morning**.
4. State is saved to disk, so rebooting the Pi won't reset the counter.

## Hardware

| Component | Detail |
|---|---|
| Raspberry Pi | Any model with GPIO header (tested 3.3 V logic) |
| Relay board | [BDD 2CH 3.3V](https://www.communica.co.za/products/bdd-relay-board-2ch-3-3v) (High/Low level trigger, optocoupler isolated) |
| Button | Momentary push-button (normally open) |
| Valve | 12 V gravity-feed solenoid valve wired through the relay's NO/COM terminals |

## Wiring

```
Raspberry Pi                Relay Board
──────────────              ───────────
3.3 V (pin 1)  ──────────▶ DC+
GND   (pin 6)  ──────────▶ DC-
GPIO 27 (pin 13) ────────▶ IN1
                            Set jumper S1: COM → H (high-level trigger)

Raspberry Pi                Button
──────────────              ──────
GPIO 17 (pin 11) ────────▶ one leg
GND   (pin 9)    ────────▶ other leg
                            (internal pull-up enabled in software)

Relay Board                 Valve / Load
───────────                 ───────────
COM  ─────────────────────▶ one terminal
NO   ─────────────────────▶ other terminal
                            (power supply in series as needed)
```

## Configuration

All tunables live at the top of `whiskey_button.py`:

| Constant | Default | Description |
|---|---|---|
| `BUTTON_PIN` | `17` | BCM GPIO pin for the button |
| `RELAY_PIN` | `27` | BCM GPIO pin for the relay |
| `POUR_DURATION` | `2` | Seconds the valve stays open |
| `MAX_POURS_PER_DAY` | `2` | Pours allowed per day |
| `RESET_HOUR` | `6` | Hour (0-23) when the counter resets |
| `RELAY_ACTIVE_HIGH` | `True` | Set `False` if your jumper is set to low-level trigger |

## Install

Copy the project to your Pi (e.g. via `scp` or `git clone`), then:

```bash
cd whiskey-button
sudo bash install.sh
```

This copies the script to `/opt/whiskey-button/`, installs a systemd service,
and starts it immediately.  It will auto-start on every boot.

## Useful Commands

```bash
sudo systemctl status  whiskey-button     # check status
sudo systemctl stop    whiskey-button     # stop
sudo systemctl start   whiskey-button     # start
sudo systemctl restart whiskey-button     # restart after config changes
sudo journalctl -u     whiskey-button -f  # live logs
```

## State File

Pour history is stored in `/var/lib/whiskey-button/state.json`:

```json
{"date": "2026-04-12", "count": 1}
```

The date represents the "pour day" (which rolls over at `RESET_HOUR`, not at
midnight). Deleting this file resets the counter.
