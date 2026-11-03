#!/usr/bin/env python3
"""Consistent database backup (safe while the app runs).  Restore: stop the app and copy a backup over data/teacher.db.

  python scripts/backup.py [--keep 14] [--dest /path]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import config, db  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--keep", type=int, default=config.BACKUP_KEEP); ap.add_argument("--dest", type=Path)
a = ap.parse_args()
out = db.backup(a.dest, a.keep)
print(f"backup written: {out} ({out.stat().st_size / 1_048_576:.1f} MB)")
