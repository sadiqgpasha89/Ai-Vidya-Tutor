import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Isolated data dir for every test run; must be set before the backend is imported.
os.environ["TEACHER_DATA_DIR"] = tempfile.mkdtemp(prefix="vidya-test-")
for var in ("TEACHER_MOCK", "TEACHER_MODEL", "TEACHER_PROVIDER", "TEACHER_QUIZ_MODEL", "TEACHER_STRONG_MODEL", "TEACHER_AUTH"):
    os.environ.pop(var, None)
os.environ.update({"TEACHER_WARMUP": "0", "TEACHER_REMINDERS": "0", "TEACHER_BACKUP_HOURS": "0", "TEACHER_RATE_AUTH": "1000", "TEACHER_RATE_AI": "1000", "TEACHER_RATE_GENERAL": "100000"})

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def mailbox(monkeypatch):
    """Nothing is ever emailed in tests: codes land here as (email, code, purpose) instead."""
    from backend import notify
    box = []
    monkeypatch.setattr(notify, "send_code", lambda to, code, purpose: box.append((to, code, purpose)) or "email")
    return box


@pytest.fixture()
def student():
    from backend import accounts
    n = len(accounts.db.all("SELECT id FROM users")) + 1
    user = accounts.create_user(f"stu{n}", "Passw0rd!x", "Asha", "student", 2006, profile={"grade": 9})
    from backend import store
    return {**store.get_student(user["id"]), "username": user["username"]}
