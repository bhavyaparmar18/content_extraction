"""Import the former per-store databases (auth.db, sop_records.db, template_records.db,
gwp_guides.db, migrations.db) into the single ``data/app.db``.

The server does this by itself on startup when ``app.db`` does not exist yet; this
script lets you preview it first (``--dry-run`` builds the new database in a
temporary folder, verifies it, reports and throws it away) or run it explicitly.

The old files are backed up to ``data/legacy_db_backup_<timestamp>/`` and left in
place, unused. To roll back: stop the server and delete ``data/app.db``.

Examples (from content_extraction/):
    uv run python scripts/migrate_to_app_db.py --dry-run
    uv run python scripts/migrate_to_app_db.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.db.legacy_import import LegacyImportError, import_legacy, legacy_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Build and verify in a temporary folder; change nothing")
    args = parser.parse_args()

    settings = get_settings()
    found = legacy_files(settings.db_path)
    print(f"Target: {settings.db_path}")
    print(f"Legacy databases: {', '.join(str(p.name) for p in found.values()) or 'none'}")
    try:
        report = import_legacy(settings, dry_run=args.dry_run)
    except LegacyImportError as exc:
        print(f"Not imported: {exc}", file=sys.stderr)
        return 1
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
