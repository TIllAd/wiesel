"""Quellen-Wächter: meldet, wenn sich die offizielle Quellseite einer
Wissensbasis-Datei geändert hat. Er ändert NIE eine Wissensbasis-Datei –
das Team entscheidet im Editor, ob etwas übernommen wird.

Aufruf (Cron auf der VM, einmal pro Nacht):
    docker exec -w /app/backend wiesel-backend python -m jobs.source_watch

Zustand: <Wissensbasis>/.quellen-status.json (wird nicht an WiSdom gegeben).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from backend import kb_store
except ImportError:  # Aufruf mit -w /app/backend
    import kb_store

STATE_NAME = ".quellen-status.json"
USER_AGENT = "WiSdom-Quellenwaechter/1.0 (FAU WiSo; Kontakt siehe Impressum)"


def state_path(base: Path) -> Path:
    return base / STATE_NAME


def load_state(base: Path) -> dict:
    try:
        return json.loads(state_path(base).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(base: Path, state: dict) -> None:
    tmp = state_path(base).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(state_path(base))


def page_fingerprint(html: str) -> str:
    """Nur den sichtbaren Haupttext vergleichen, nicht Skripte/Menüs/Zeitstempel."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.find(id="content") or soup.find("article") or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ")).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(5, 20))
    response.raise_for_status()
    return response.text


def mark_reviewed(base: Path, relative: str, who: str = "") -> None:
    state = load_state(base)
    entry = state.get(relative)
    if not entry:
        return
    if entry.get("aktuell_hash"):
        entry["basis_hash"] = entry["aktuell_hash"]
    entry["geaendert_seit"] = None
    entry["geprueft_am"] = datetime.now().isoformat(timespec="minutes")
    entry["geprueft_von"] = who
    save_state(base, state)


def _mark_unreachable(entry: dict, reason: str) -> None:
    entry["nicht_pruefbar"] = reason
    entry.pop("fehler", None)
    entry.pop("fehler_seit", None)


def run(base: Path, fetcher=fetch, pause: float = 1.0) -> dict:
    state = load_state(base)
    now = datetime.now().isoformat(timespec="minutes")
    seen = set()
    unreachable_hosts: set[str] = set()  # ein Timeout pro Server reicht, nicht 40
    for path in kb_store.md_files(base):
        relative = kb_store.rel(base, path)
        if kb_store.is_auto(relative):
            continue
        _, body = kb_store.parse(path.read_text(encoding="utf-8", errors="replace"))
        url = kb_store.source_url(body)
        if not url:
            continue
        seen.add(relative)
        entry = state.get(relative) or {}
        if entry.get("url") != url:  # neue oder geänderte Quelle → neu einlesen
            entry = {"url": url}
        entry["letzter_check"] = now
        host = urlparse(url).hostname or ""
        if host in unreachable_hosts:
            _mark_unreachable(entry, "Server vom WiSdom-Server aus nicht erreichbar")
            state[relative] = entry
            continue
        try:
            fingerprint = page_fingerprint(fetcher(url))
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None:
                # Die Seite antwortet, aber mit Fehler (404, 410 …): echter Hinweis fürs Team.
                entry["fehler"] = f"HTTP {status}"
                entry.setdefault("fehler_seit", now)
                entry.pop("nicht_pruefbar", None)
            else:
                # Netzwerk (z. B. FAU-Seiten sind von der VM aus gesperrt): kein Alarm.
                unreachable_hosts.add(host)
                _mark_unreachable(entry, e.__class__.__name__)
        else:
            entry.pop("fehler", None)
            entry.pop("fehler_seit", None)
            entry.pop("nicht_pruefbar", None)
            entry["aktuell_hash"] = fingerprint
            if not entry.get("basis_hash"):
                entry["basis_hash"] = fingerprint
            if fingerprint != entry["basis_hash"]:
                entry["geaendert_seit"] = entry.get("geaendert_seit") or now
            else:
                entry["geaendert_seit"] = None
        state[relative] = entry
        if pause:
            time.sleep(pause)
    for relative in list(state):
        if relative not in seen:
            del state[relative]
    save_state(base, state)
    return state


def main() -> int:
    base = kb_store.kb_dir()
    if not base:
        print("Wissensbasis nicht gefunden", file=sys.stderr)
        return 1
    state = run(base)
    changed = [p for p, e in state.items() if e.get("geaendert_seit")]
    failed = [p for p, e in state.items() if e.get("fehler")]
    skipped = [p for p, e in state.items() if e.get("nicht_pruefbar")]
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] {len(state)} Quellen: {len(changed)} geändert, {len(failed)} mit Fehlerseite, {len(skipped)} vom Server aus nicht prüfbar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
