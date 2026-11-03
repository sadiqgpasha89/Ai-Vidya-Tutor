#!/usr/bin/env python3
"""Create (or promote to) an administrator:  python scripts/create_admin.py <username> [password]"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import accounts, db  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
username = sys.argv[1].lower()
user = accounts.get_by_username(username)
if user:
    db.run("UPDATE users SET role='admin' WHERE id=?", (user["id"],))
    print(f"{username} is now an administrator")
else:
    password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Password (8+ characters): ")
    created = accounts.create_user(username, password, "Administrator", "teacher", 1980)
    db.run("UPDATE users SET role='admin' WHERE id=?", (created["id"],))
    print(f"administrator '{username}' created. Sign in, then add and verify your email address in Settings so you can reset your password later.")
