#!/usr/bin/env python3
"""Clear all Wiesel chat/session flags without deleting chats.

Use this when you want a clean slate for testing the flagging workflow.
It creates a timestamped backup of backend/wiesel.db before deleting rows from chat_flags.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "backend" / "wiesel.db"
REPORTS_DIR = ROOT / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear all rows from Wiesel chat_flags.")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to SQLite DB. Default: backend/wiesel.db")
    parser.add_argument("--yes", action="store_true", help="Actually delete flags. Without this, only prints what would happen.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        return 1

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_flags'")
        if cur.fetchone() is None:
            print(f"ERROR: table chat_flags does not exist in {db_path}")
            return 1

        total = cur.execute("SELECT COUNT(*) FROM chat_flags").fetchone()[0]
        session_flags = cur.execute("SELECT COUNT(*) FROM chat_flags WHERE message_id IS NULL").fetchone()[0]
        message_flags = cur.execute("SELECT COUNT(*) FROM chat_flags WHERE message_id IS NOT NULL").fetchone()[0]

        print("Wiesel chat_flags reset")
        print(f"DB:            {db_path}")
        print(f"Total flags:   {total}")
        print(f"Session flags: {session_flags}")
        print(f"Message flags: {message_flags}")

        if not args.yes:
            print("\nDRY RUN only. Nothing deleted.")
            print("Run with --yes to delete all flag rows:")
            print("  python clear_chat_flags.py --yes")
            return 0

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = REPORTS_DIR / f"wiesel-before-clear-chat-flags-{stamp}.db"
    shutil.copy2(db_path, backup_path)

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM chat_flags")
        deleted = cur.rowcount
        conn.commit()
        remaining = cur.execute("SELECT COUNT(*) FROM chat_flags").fetchone()[0]

    print("\nDONE")
    print(f"Backup:        {backup_path}")
    print(f"Deleted rows:  {deleted}")
    print(f"Remaining:     {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
