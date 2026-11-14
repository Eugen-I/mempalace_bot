#!/usr/bin/env python3
"""Import a Garmin wellness export without touching Garmin Connect.

Examples:
    python scripts/garmin_import_cli.py ~/Downloads/wellness.zip
    python scripts/garmin_import_cli.py --user-id 123 ~/Downloads/wellness.fit
    python scripts/garmin_import_cli.py          # scan GARMIN_IMPORT_DIR
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.garmin.config import get_config  # noqa: E402
from services.garmin.db import init_db  # noqa: E402
from services.garmin.importers import import_any_path  # noqa: E402
from services.garmin.raw_store import RawStore  # noqa: E402


def _candidates(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".zip", ".fit", ".csv", ".json", ".tcx"}
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Garmin wellness exports")
    parser.add_argument("path", nargs="?", help="ZIP/FIT file or extracted folder")
    parser.add_argument(
        "--user-id",
        type=int,
        default=int(os.getenv("GARMIN_USER_ID", "1")),
        help="Telegram user id for the local database (default: 1)",
    )
    parser.add_argument("--data-dir", help="Garmin data directory")
    parser.add_argument("--db", help="SQLite path (default: GARMIN_DB_PATH)")
    parser.add_argument("--tmp-dir", help="temporary extraction directory")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    cfg = get_config(args.data_dir)
    cfg.ensure_dirs()
    db_path = Path(args.db).expanduser() if args.db else cfg.db_path
    conn = init_db(db_path)
    store = RawStore(cfg.raw_dir)

    if args.path:
        paths = [Path(args.path).expanduser()]
    else:
        paths = _candidates(cfg.import_dir)
        if not paths:
            print(f"Нет .zip/.fit файлов в {cfg.import_dir}")
            conn.close()
            return 0

    results = []
    try:
        for path in paths:
            result = import_any_path(
                path,
                conn=conn,
                raw_store=store,
                user_id=args.user_id,
                tmp_dir=args.tmp_dir or cfg.tmp_dir,
            )
            results.append({"path": str(path), **result.as_dict()})
    finally:
        conn.close()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            days = ", ".join(item["days"]) if item["days"] else "—"
            print(
                f"{item['path']}: {item['status']} | дни: {days} | "
                f"FIT: {item['files_ok']}/{item['files_total']} | "
                f"ошибок: {len(item['issues'])}"
            )
            for issue in item["issues"]:
                print(f"  ! {issue['file']}: {issue['error']}")

    return 1 if any(item["status"] == "failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
