# fritzbox-vpn-monitor

Überwacht eine VPN-Verbindung (Site-to-Site) einer AVM FRITZ!Box und schickt eine
Push-Benachrichtigung (via [ntfy](https://ntfy.sh)), wenn die Verbindung ausfällt
bzw. wieder hergestellt wird.

## Hintergrund

FRITZ!OS hat keinen nativen Push-Service-Trigger für VPN-Verbindungsabbrüche –
ein Abbruch landet zwar im Ereignisprotokoll, löst aber keine E-Mail/Push aus.
Für Szenarien, in denen ein Site-to-Site-VPN dauerhaft stehen soll (z. B. eine
Anbindung an eine Leitstelle für einen Alarmdrucker), fällt ein Abbruch damit
oft erst auf, wenn es zu spät ist. Dieses Script schließt die Lücke von außen,
per periodischem Poll.

## Funktionsweise

- Login über den FRITZ!OS-PBKDF2-Challenge-Response-Mechanismus (`login_sid.lua?version=2`,
  FRITZ!OS ≥ 7.24).
- Abfrage des VPN-Verbindungsstatus über die (undokumentierte) `query.lua`-JSON-Schnittstelle,
  die auch die Weboberfläche selbst nutzt.
- Schwellwert-/Debounce-Logik über eine lokale State-Datei: Erst nach mehreren
  aufeinanderfolgenden Fehlschlägen wird ein Alarm ausgelöst, damit kurze
  Reconnects (Verbindungsaufbau dauert erfahrungsgemäß einige Sekunden bis
  niedrige Zehnersekunden) keine Fehlalarme erzeugen.
- Bei Erreichen der Schwelle sowie bei Wiederherstellung: Push-Benachrichtigung
  via ntfy.sh (oder eine selbstgehostete ntfy-Instanz).

## Voraussetzungen

- FRITZ!OS ≥ 7.24
- Ein Fritzbox-Benutzerkonto mit aktiviertem "Zugriff auch aus dem Internet erlaubt"
  (System → FRITZ!Box-Benutzer)
- Erreichbarkeit der Fritzbox-Weboberfläche von dort, wo das Script läuft – z. B.
  über MyFRITZ! plus aktivierter HTTPS-Freigabe unter
  `Internet → Freigaben → FRITZ!Box-Dienste`
- Python 3 und das Paket `requests`

## Installation

```bash
apt install python3-requests   # Debian/Ubuntu
# oder: pip install requests
```

## Konfiguration

Alle Zugangsdaten und Einstellungen werden ausschließlich über Umgebungsvariablen
übergeben – niemals im Code oder eingecheckt.

| Variable | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `FRITZBOX_HOST` | ja | – | z. B. `https://xxxxxxxxxxxxx.myfritz.net:PORT` (ohne trailing slash) |
| `FRITZBOX_USER` | ja | – | Fritzbox-Benutzername |
| `FRITZBOX_PASSWORD` | nein | interaktive Abfrage | Fritzbox-Passwort; wenn nicht gesetzt, wird per `getpass` gefragt |
| `FRITZBOX_VPN_NAME` | nein | `Leitstelle REK Drucker` | Name der zu überwachenden VPN-Verbindung, exakt wie in der Fritzbox konfiguriert |
| `FRITZBOX_VPN_FAIL_THRESHOLD` | nein | `3` | Anzahl aufeinanderfolgender Fehlschläge, bevor ein Alarm ausgelöst wird |
| `FRITZBOX_VPN_STATE_FILE` | nein | Verzeichnis des Scripts | Pfad der State-Datei zum Zählen aufeinanderfolgender Fehlschläge |
| `NTFY_URL` | nein | `https://ntfy.sh` | ntfy-Server (auch selbstgehostet nutzbar) |
| `NTFY_TOPIC` | nein | – | ntfy-Topic; ohne gesetztes Topic wird nur geloggt, kein Push verschickt |

## Nutzung

```bash
export FRITZBOX_HOST="https://xxxxxxxxxxxxx.myfritz.net:PORT"
export FRITZBOX_USER="benutzer"
export FRITZBOX_PASSWORD="passwort"
export NTFY_TOPIC="ein-langer-zufaelliger-string"

python3 fritzbox_vpn_status.py
```

## Automatisierung per Cron

Zugangsdaten in eine Datei mit restriktiven Rechten auslagern und per Wrapper-Script laden:

```bash
# /opt/fritzbox-monitor/.env, chmod 600
FRITZBOX_HOST=https://xxxxxxxxxxxxx.myfritz.net:PORT
FRITZBOX_USER=benutzer
FRITZBOX_PASSWORD=passwort
FRITZBOX_VPN_NAME="Leitstelle REK Drucker"
NTFY_TOPIC=ein-langer-zufaelliger-string
```

```bash
#!/bin/bash
# /opt/fritzbox-monitor/run.sh
set -a
source /opt/fritzbox-monitor/.env
set +a
exec python3 /opt/fritzbox-monitor/fritzbox_vpn_status.py
```

```cron
*/5 * * * * /opt/fritzbox-monitor/run.sh >> /var/log/fritzbox-monitor.log 2>&1
```

## Sicherheitshinweise

- Zugangsdaten ausschließlich über Umgebungsvariablen bzw. eine `.env`-Datei mit
  `chmod 600` bereitstellen – niemals im Code oder Repo.
- ntfy.sh-Topics sind standardmäßig **nicht privat**: Wer den Topic-Namen kennt,
  kann mitlesen und selbst Nachrichten senden. Einen langen, zufälligen Namen
  wählen (`openssl rand -hex 16`) oder eine selbstgehostete ntfy-Instanz nutzen.
- Wo möglich ein eigenes, separates Fritzbox-Benutzerkonto für dieses Script
  anlegen statt des Hauptkontos.
- Falls das Script von einer IPv6-only erreichbaren FRITZ!Box abgefragt wird
  (z. B. reines IPv6-Anschluss ohne öffentliches IPv4), braucht die ausführende
  Maschine selbst funktionierende IPv6-Konnektivität – reine IPv4-Umgebungen
  (u. a. viele GitHub-Actions-Hosted-Runner) erreichen einen solchen Host nicht.

## Bekannte Einschränkungen

- `login_sid.lua` und `query.lua` sind von AVM nicht offiziell dokumentierte
  Schnittstellen und können sich mit künftigen FRITZ!OS-Versionen ändern.
- Die State-Datei ist lokal und muss auf einer dauerhaft laufenden Maschine
  liegen (Cron/systemd-Timer). Auf ephemeren Umgebungen (z. B. GitHub-Actions-
  Runnern) geht der Fehlschlag-Zähler zwischen Läufen verloren.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
