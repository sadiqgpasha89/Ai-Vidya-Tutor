"""The code email itself: sent over real SMTP to a local sink, and written to the server log when no mail server is configured."""
import socketserver
import threading

import pytest

from backend import config, notify, otp

REAL_SEND_CODE = notify.send_code  # the autouse mailbox fixture replaces it for other tests


class _Sink(socketserver.StreamRequestHandler):
    """Just enough of an SMTP server to accept one message."""
    def handle(self):
        w = lambda line: self.wfile.write((line + "\r\n").encode())  # noqa: E731
        w("220 test ESMTP")
        data, collecting = [], False
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode(errors="replace").rstrip("\r\n")
            if collecting:
                if line == ".":
                    collecting = False
                    self.server.messages.append("\n".join(data))
                    w("250 queued")
                else:
                    data.append(line[1:] if line.startswith("..") else line)
                continue
            cmd = line.upper()
            if cmd.startswith("EHLO") or cmd.startswith("HELO"):
                w("250 test")
            elif cmd.startswith(("MAIL", "RCPT")):
                w("250 ok")
            elif cmd == "DATA":
                collecting = True
                w("354 go")
            elif cmd == "QUIT":
                w("221 bye")
                return
            else:
                w("250 ok")


@pytest.fixture()
def smtp_sink(monkeypatch):
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Sink)
    server.messages, server.daemon_threads = [], True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "SMTP_PORT", server.server_address[1])
    monkeypatch.setattr(config, "SMTP_SECURITY", "none")
    monkeypatch.setattr(config, "SMTP_USER", "")
    monkeypatch.setattr(config, "SMTP_FROM", "vidya@school.test")
    monkeypatch.setattr(notify, "send_code", REAL_SEND_CODE)
    yield server
    server.shutdown()


def test_the_code_arrives_by_email(smtp_sink):
    assert notify.send_code("asha@example.com", "482913", "signup") == "email"
    import email
    (raw,) = smtp_sink.messages
    msg = email.message_from_string(raw)
    body = msg.get_payload(decode=True).decode()
    assert msg["To"] == "asha@example.com" and msg["From"] == "vidya@school.test" and msg["Subject"] == "Your AIVidya code: 482913"
    assert "482913" in body and "expires in 10 minutes" in body and "If you did not ask for this" in body


def test_a_refusing_mail_server_leaves_no_code_behind(monkeypatch):
    from backend import db
    monkeypatch.setattr(notify, "send_code", lambda *a: (_ for _ in ()).throw(ConnectionRefusedError("no mail server")))
    with pytest.raises(otp.OtpError) as err:
        otp.issue("signup", "refused@example.com", None, {"x": 1})
    assert err.value.status == 503 and "could not send" in str(err.value)
    assert db.one("SELECT 1 FROM email_otps WHERE email='refused@example.com'") is None


def test_without_a_mail_server_the_code_goes_to_the_server_log(monkeypatch, caplog):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    monkeypatch.setattr(notify, "send_code", REAL_SEND_CODE)
    import logging
    with caplog.at_level(logging.WARNING):
        assert notify.send_code("log@example.com", "135790", "reset") == "log"
    assert "135790" in caplog.text and "SMTP_HOST" in caplog.text


def test_email_addresses_are_checked_and_masked():
    assert otp.normalize_email("  Name.Tag+x@Sub.Example.CO.in ") == "name.tag+x@sub.example.co.in"
    for bad in ("", "x", "x@y", "x@@y.com", "a b@c.com", "a..b@c.com", "@c.com", "x@.com", "a" * 300 + "@c.com"):
        with pytest.raises(otp.OtpError):
            otp.normalize_email(bad)
    assert otp.mask("asha@example.com") == "a***@example.com" and "@" in otp.mask("a@b.co") and otp.mask("asha@example.com").count("sha") == 0
