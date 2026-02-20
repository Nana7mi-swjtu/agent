from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app


class EmailSender:
    def send_code(self, to_email: str, code: str, purpose: str) -> None:
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    def send_code(self, to_email: str, code: str, purpose: str) -> None:
        subject = "验证码"
        body = f"您的验证码是：{code}\n10分钟内有效，请勿泄露。"
        print(f"[Email:{purpose}] To={to_email} Subject={subject}\n{body}")


class InMemoryEmailSender(EmailSender):
    def __init__(self, outbox: list[dict]) -> None:
        self._outbox = outbox

    def send_code(self, to_email: str, code: str, purpose: str) -> None:
        self._outbox.append(
            {
                "to": to_email,
                "code": code,
                "purpose": purpose,
            }
        )


class SmtpEmailSender(EmailSender):
    def __init__(self, host: str, port: int, username: str, password: str, from_addr: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_addr

    def send_code(self, to_email: str, code: str, purpose: str) -> None:
        subject = "验证码"
        body = f"您的验证码是：{code}\n10分钟内有效，请勿泄露。"
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to_email
        msg.set_content(body)

        with smtplib.SMTP(self._host, self._port) as server:
            server.starttls()
            if self._username:
                server.login(self._username, self._password)
            server.send_message(msg)


def get_email_sender() -> EmailSender:
    backend = current_app.config.get("EMAIL_BACKEND", "console")
    if backend == "memory":
        outbox = current_app.extensions.get("email_outbox", [])
        return InMemoryEmailSender(outbox)
    if backend == "smtp":
        host = current_app.config.get("SMTP_HOST", "")
        port = int(current_app.config.get("SMTP_PORT", 587))
        username = current_app.config.get("SMTP_USERNAME", "")
        password = current_app.config.get("SMTP_PASSWORD", "")
        from_addr = current_app.config.get("SMTP_FROM") or username

        if not host or not username or not password:
            raise RuntimeError("SMTP configuration missing. Set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD.")

        return SmtpEmailSender(host, port, username, password, from_addr)
    return ConsoleEmailSender()
