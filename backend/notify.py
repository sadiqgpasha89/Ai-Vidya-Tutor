"""Notifications: in-app always; email (SMTP), web push (VAPID) and WhatsApp (Meta Cloud API) when configured and opted in."""
from __future__ import annotations

import json
import smtplib
import threading
import time
import urllib.request
from datetime import date, datetime
from email.message import EmailMessage

from . import config, db, learning, reports, store
from .logs import get

log = get("notify")


# ---- channels ----------------------------------------------------------------------------------
def email_ready() -> bool:
    return bool(config.SMTP_HOST)


def push_ready() -> bool:
    return bool(config.VAPID_PUBLIC and config.VAPID_PRIVATE)


def whatsapp_ready() -> bool:
    return bool(config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_ID)


def _send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
    msg.set_content(body)
    if config.SMTP_SECURITY == "ssl":
        client = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    else:
        client = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    with client as s:
        if config.SMTP_SECURITY == "starttls":
            s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)


def send_code(to: str, code: str, purpose: str) -> str:
    """Email a one-time code. -> "email" when it was sent. Without SMTP settings nothing can be sent, so the code is written to the server log
    for the administrator (a school can then read it out, or set SMTP_HOST); -> "log". Raises if the mail server refuses."""
    what = {"signup": "start creating your AIVidya account", "login": "sign in to AIVidya", "reset": "reset your AIVidya password", "email": "confirm this email address for your AIVidya account"}.get(purpose, "continue")
    if not email_ready():
        log.warning(f"EMAIL NOT CONFIGURED (set SMTP_HOST): one-time code for {to} to {what}: {code}")
        return "log"
    _send_email(to, f"Your AIVidya code: {code}",
                f"Your AIVidya verification code is {code}\n\nEnter it to {what}. It works once and expires in {config.OTP_MINUTES} minutes.\n\n"
                "If you did not ask for this, ignore this email: nothing has been changed, and nobody can use your account without the code.")
    return "email"


def _send_push(user_id: str, title: str, body: str, link: str) -> int:
    from pywebpush import WebPushException, webpush
    sent = 0
    for sub in db.all("SELECT endpoint, subscription FROM push_subs WHERE user_id=?", (user_id,)):
        try:
            webpush(json.loads(sub["subscription"]), json.dumps({"title": title, "body": body, "link": link}), vapid_private_key=config.VAPID_PRIVATE,
                    vapid_claims={"sub": config.VAPID_SUBJECT})
            sent += 1
        except WebPushException as exc:
            if getattr(exc.response, "status_code", 0) in (404, 410):  # subscription expired
                db.run("DELETE FROM push_subs WHERE endpoint=?", (sub["endpoint"],))
    return sent


def _send_whatsapp(phone: str, text: str) -> None:
    payload = json.dumps({"messaging_product": "whatsapp", "to": phone.lstrip("+"), "type": "text", "text": {"body": text[:900]}}).encode()
    req = urllib.request.Request(f"https://graph.facebook.com/v19.0/{config.WHATSAPP_PHONE_ID}/messages", data=payload,
                                 headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}", "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=20).read()


def _deliver(nid: int, user_id: str, title: str, body: str, link: str) -> None:
    contact = db.one("SELECT * FROM contacts WHERE user_id=?", (user_id,)) or {}
    try:
        if email_ready() and contact.get("email") and contact.get("notify_email"):
            _send_email(contact["email"], title, f"{body}\n\n{link or ''}".strip())
            db.run("UPDATE notifications SET emailed=1 WHERE id=?", (nid,))
        if push_ready() and _send_push(user_id, title, body, link):
            db.run("UPDATE notifications SET pushed=1 WHERE id=?", (nid,))
        if whatsapp_ready() and contact.get("phone") and contact.get("notify_whatsapp"):
            _send_whatsapp(contact["phone"], f"{title}\n{body}")
            db.run("UPDATE notifications SET whatsapp=1 WHERE id=?", (nid,))
    except Exception:  # noqa: BLE001 - a failed channel must never lose the in-app notification
        log.exception("notification delivery failed")


# ---- API ---------------------------------------------------------------------------------------
def create(user_id: str, kind: str, title: str, body: str = "", link: str = "", deliver: bool = True) -> int:
    nid = db.run("INSERT INTO notifications (user_id, kind, title, body, link, created_at) VALUES (?,?,?,?,?,?)", (user_id, kind, title[:140], body[:600], link, time.time()))
    if deliver and (email_ready() or push_ready() or whatsapp_ready()):
        threading.Thread(target=_deliver, args=(nid, user_id, title, body, link), daemon=True).start()
    return nid


def listing(user_id: str, unread_only: bool = False, limit: int = 30) -> list[dict]:
    return db.all("SELECT * FROM notifications WHERE user_id=?" + (" AND read_at IS NULL" if unread_only else "") + " ORDER BY id DESC LIMIT ?", (user_id, limit))


def unread_count(user_id: str) -> int:
    return db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (user_id,), 0)


def mark_read(user_id: str, nid: int | None = None) -> None:
    if nid:
        db.run("UPDATE notifications SET read_at=? WHERE id=? AND user_id=?", (time.time(), nid, user_id))
    else:
        db.run("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (time.time(), user_id))


def save_contact(user_id: str, email: str | None, phone: str | None, notify_email: bool, notify_whatsapp: bool) -> None:
    db.run("INSERT INTO contacts (user_id, email, phone, notify_email, notify_whatsapp) VALUES (?,?,?,?,?) ON CONFLICT DO UPDATE SET email=?, phone=?, notify_email=?, notify_whatsapp=?",
           (user_id, email, phone, int(notify_email), int(notify_whatsapp), email, phone, int(notify_email), int(notify_whatsapp)))


def save_push(user_id: str, subscription: dict) -> None:
    endpoint = str(subscription.get("endpoint", ""))
    if endpoint.startswith("https://"):
        db.run("INSERT OR REPLACE INTO push_subs VALUES (?,?,?)", (user_id, endpoint, json.dumps(subscription)))


def wellbeing_alert(student: dict) -> None:
    """Tell linked parents (never the content) that their child may be struggling emotionally. Disclosed in the privacy notice."""
    for p in db.all("SELECT parent_id FROM parent_links WHERE student_id=?", (student["id"],)):
        create(p["parent_id"], "wellbeing", f"{student['name']} may need a kind word",
               "AIVidya noticed something in a conversation that suggests your child may be feeling stressed or low. Please check in with them gently. Tele-MANAS: 14416.", "/#/parent")


# ---- scheduled reminders -----------------------------------------------------------------------
def reminder_tick(today: date | None = None) -> int:
    """Send at most one study reminder per student per day, and a weekly report to parents on Sundays. Returns how many were created."""
    today = today or date.today()
    start = datetime.combine(today, datetime.min.time()).timestamp()
    sent = 0
    for st in db.all("SELECT u.id, u.display_name FROM users u WHERE u.role='student' AND u.disabled=0 AND u.consent IN ('na','granted')"):
        sid = st["id"]
        if db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='reminder' AND created_at>=?", (sid, start), 0):
            continue
        due, cards = len(store.due_revisions(sid, 20)), learning.card_counts(sid)["due"]
        streak = store.streak(sid)
        today_active = today.isoformat() in store.active_days(sid, 2)
        if due or cards:
            create(sid, "reminder", "Time to revise 🔁", f"{due} topic(s) and {cards} flashcard(s) are due. A few minutes now keeps them in memory.", "/#/revise")
            sent += 1
        elif streak >= 2 and not today_active:
            create(sid, "reminder", f"Keep your {streak}-day streak 🔥", "Do one short topic today to keep it going.", "/#/plan")
            sent += 1
    if today.weekday() == 6:  # Sunday
        for link in db.all("SELECT parent_id, student_id FROM parent_links"):
            if db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id=? AND kind='weekly' AND created_at>=?", (link["parent_id"], start), 0):
                continue
            r = reports.weekly_summary(link["student_id"])
            create(link["parent_id"], "weekly", f"Weekly report: {r['name']}", r["text"], "/#/parent")
            sent += 1
    return sent


def _loop() -> None:
    while True:
        time.sleep(3600)
        if 7 <= datetime.now().hour <= 20:  # never nag at night
            try:
                reminder_tick()
            except Exception:  # noqa: BLE001
                log.exception("reminder tick failed")


def start() -> None:
    if config.REMINDERS:
        threading.Thread(target=_loop, daemon=True, name="reminders").start()
