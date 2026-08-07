#!/usr/bin/env python3
"""Check one VPN connection's status on a FRITZ!Box via its remote HTTPS web UI (e.g. myfritz.net).

Meant to be run repeatedly (cron). Tracks consecutive failures in a small state
file so a single flaky/reconnecting check doesn't trigger an alert, and pushes
an ntfy notification when the failure threshold is crossed (and again on recovery).

Required env vars:
  FRITZBOX_HOST      https://xxxxxxxxxxxxx.myfritz.net:PORT   (no trailing slash)
  FRITZBOX_USER
  FRITZBOX_PASSWORD

Optional env vars:
  FRITZBOX_VPN_NAME          default "Leitstelle REK Drucker"
  FRITZBOX_VPN_FAIL_THRESHOLD default "3"
  FRITZBOX_VPN_STATE_FILE     default alongside this script
  NTFY_URL                   default "https://ntfy.sh"
  NTFY_TOPIC                  no default; if unset, no push is sent
"""
import getpass
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET

import requests

HOST = os.environ.get("FRITZBOX_HOST", "").rstrip("/")
USER = os.environ.get("FRITZBOX_USER", "")
PASSWORD = os.environ.get("FRITZBOX_PASSWORD") or getpass.getpass("FRITZ!Box Passwort: ")
TARGET_NAME = os.environ.get("FRITZBOX_VPN_NAME", "Leitstelle REK Drucker")
FAIL_THRESHOLD = int(os.environ.get("FRITZBOX_VPN_FAIL_THRESHOLD", "3"))
STATE_FILE = os.environ.get(
    "FRITZBOX_VPN_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vpn_monitor_state.json"),
)
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

if not HOST or not USER:
    sys.exit("FRITZBOX_HOST und FRITZBOX_USER müssen gesetzt sein.")


def notify(title, message, priority=3):
    if not NTFY_TOPIC:
        print(f"(kein NTFY_TOPIC gesetzt, würde senden: [{title}] {message})")
        return
    try:
        requests.post(
            NTFY_URL,
            json={"topic": NTFY_TOPIC, "title": title, "message": message, "priority": priority},
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"ntfy-Benachrichtigung fehlgeschlagen: {e}")


def pbkdf2_response(challenge, password):
    _, iter1, salt1, iter2, salt2 = challenge.split("$")
    hash1 = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt1), int(iter1))
    hash2 = hashlib.pbkdf2_hmac("sha256", hash1, bytes.fromhex(salt2), int(iter2))
    return f"{salt2}${hash2.hex()}"


def login(session):
    r = session.get(f"{HOST}/login_sid.lua", params={"version": "2"}, timeout=15)
    r.raise_for_status()
    challenge = ET.fromstring(r.text).findtext("Challenge")

    if not challenge.startswith("2$"):
        sys.exit("Unerwartetes Challenge-Format – Fritzbox nutzt evtl. eine sehr alte FRITZ!OS-Version.")

    response = pbkdf2_response(challenge, PASSWORD)
    r = session.get(
        f"{HOST}/login_sid.lua",
        params={"version": "2", "username": USER, "response": response},
        timeout=15,
    )
    r.raise_for_status()
    sid = ET.fromstring(r.text).findtext("SID")

    if sid == "0000000000000000":
        sys.exit("Login fehlgeschlagen (falscher Benutzer/Passwort oder Konto ohne Zugriffsrechte).")
    return sid


def vpn_connections(session, sid):
    query = "vpn:settings/connection/list(name,activated,state,connected_since,remote_ip)"
    r = session.get(f"{HOST}/query.lua", params={"sid": sid, "q": query}, timeout=15)
    r.raise_for_status()
    return {entry["name"]: entry for entry in r.json().get("q", [])}


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"consecutive_failures": 0, "alerting": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    session = requests.Session()
    sid = login(session)

    connections = vpn_connections(session, sid)
    target = connections.get(TARGET_NAME)
    if target is None:
        sys.exit(f"VPN-Verbindung {TARGET_NAME!r} nicht gefunden. Verfügbar: {list(connections)}")

    state = load_state()
    is_up = target["state"] == "ready"

    if is_up:
        if state["alerting"]:
            print(f"OK: {TARGET_NAME!r} wieder verbunden (seit {target['connected_since']}s).")
            notify(
                "VPN wieder verbunden",
                f"{TARGET_NAME} ist seit {target['connected_since']}s wieder verbunden.",
                priority=3,
            )
        else:
            print(f"OK: {TARGET_NAME!r} verbunden (seit {target['connected_since']}s).")
        state = {"consecutive_failures": 0, "alerting": False}
    else:
        state["consecutive_failures"] += 1
        print(
            f"WARN: {TARGET_NAME!r} nicht verbunden (state={target['state']!r}), "
            f"{state['consecutive_failures']}/{FAIL_THRESHOLD} Fehlschläge in Folge."
        )
        if state["consecutive_failures"] >= FAIL_THRESHOLD and not state["alerting"]:
            state["alerting"] = True
            print("ALARM: Schwelle erreicht, sende ntfy-Push.")
            notify(
                f"VPN getrennt: {TARGET_NAME}",
                f"{TARGET_NAME} ist seit {state['consecutive_failures']} Checks in Folge nicht "
                f"verbunden (state={target['state']!r}). Manuell in der Fritzbox pruefen.",
                priority=5,
            )

    save_state(state)


if __name__ == "__main__":
    main()
