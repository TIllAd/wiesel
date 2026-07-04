"""
SQLite-Backup + Integritätscheck für wiesel.db.

Nutzt die sqlite3-Backup-API (konsistenter Snapshot auch bei laufendem Server,
im Gegensatz zu einem simplen Datei-Copy — genau so ist die korrupte Kopie vom
04.07. entstanden). Behält die letzten RETENTION_DAYS Tages-Backups.

Aufruf (Cron, täglich z. B. 04:30):
    python db_backup.py [--db PATH] [--out DIR]

Exit-Code != 0, wenn der Integritätscheck fehlschlägt → für Monitoring/Alerts.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

RETENTION_DAYS = 14


def integrity_ok(db_path: Path) -> bool:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()
        return bool(result) and result[0] == "ok"
    finally:
        con.close()


def backup(db_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"wiesel_{datetime.now().strftime('%Y-%m-%d')}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)  # konsistenter Snapshot, WAL-sicher
    finally:
        dst.close()
        src.close()
    return target


def prune(out_dir: Path) -> None:
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for f in out_dir.glob("wiesel_????-??-??.db"):
        try:
            stamp = datetime.strptime(f.stem.split("_")[1], "%Y-%m-%d")
            if stamp < cutoff:
                f.unlink()
                print(f"pruned {f.name}")
        except (ValueError, IndexError):
            continue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).parent / "wiesel.db"))
    parser.add_argument("--out", default=str(Path(__file__).parent / "backups"))
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out)

    if not db_path.exists():
        print(f"FEHLER: DB nicht gefunden: {db_path}", file=sys.stderr)
        return 2

    if not integrity_ok(db_path):
        print(f"FEHLER: integrity_check der Live-DB fehlgeschlagen: {db_path}", file=sys.stderr)
        print("Kein Backup erstellt — zuerst DB wiederherstellen (letztes gutes Backup einspielen).", file=sys.stderr)
        return 1

    target = backup(db_path, out_dir)
    if not integrity_ok(target):
        print(f"FEHLER: Backup ist korrupt: {target}", file=sys.stderr)
        return 1

    prune(out_dir)
    print(f"OK: {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
