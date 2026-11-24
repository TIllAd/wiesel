"""Tägliche Auto-Dateien (Mensa, Wetter, ÖPNV, FAU Aktuell) auf der VM erzeugen.

Läuft früher auf Tills PC; jetzt per Cron im Container:
    docker exec -w /app/backend wiesel-backend python -m jobs.crawl_daily

Schreibt direkt in die Wissensbasis. Fällt ein Crawler aus, bleibt die alte
Datei liegen und wird nach KB_AUTO_MAX_AGE_HOURS (Standard 48 h) automatisch
nicht mehr an WiSdom gegeben.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

try:
    from backend import kb_store
except ImportError:
    import kb_store


def _run(name: str, fn) -> bool:
    try:
        fn()
        print(f"  ✓ {name}")
        return True
    except Exception as e:  # ein kaputter Crawler darf die anderen nicht stoppen
        print(f"  ✗ {name}: {e.__class__.__name__}: {e}", file=sys.stderr)
        return False


def main() -> int:
    base = kb_store.kb_dir()
    if not base:
        print("Wissensbasis nicht gefunden", file=sys.stderr)
        return 1
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import Oepnv_crawler
    import fau_news_crawler
    import mensa_crawler
    import wetter_crawler

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Crawler → {base}")

    def mensa():
        out = base / "mensa-woche.md"
        out.write_text(mensa_crawler.generate_markdown(mensa_crawler.crawl_all()), encoding="utf-8")

    def simple(module, filename):
        def go():
            module.OUTPUT = base / filename
            module.main()
        return go

    results = [
        _run("Mensa", mensa),
        _run("Wetter", simple(wetter_crawler, "wetter-heute.md")),
        _run("ÖPNV", simple(Oepnv_crawler, "oepnv-heute.md")),
        _run("FAU Aktuell", simple(fau_news_crawler, "fau-aktuell.md")),
    ]
    return 0 if all(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
