"""Reads recent mail from the same Gmail account over IMAP (app password works for IMAP too)."""

import imaplib
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

import config


class MailReaderError(Exception):
    pass


def _connect() -> imaplib.IMAP4_SSL:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise MailReaderError("Gmail credentials are not configured (check .env).")
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        imap.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
    except imaplib.IMAP4.error as e:
        raise MailReaderError(f"IMAP login failed -- check credentials and that IMAP is enabled: {e}") from e
    except OSError as e:
        raise MailReaderError(f"Network error connecting to IMAP: {e}") from e
    return imap


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", "", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    import html as html_module

    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_body(msg) -> str:
    plain = None
    html = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_content()
            elif ctype == "text/html" and html is None:
                html = part.get_content()
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            plain = msg.get_content()
        elif ctype == "text/html":
            html = msg.get_content()

    if plain:
        return plain.strip()
    if html:
        return _strip_html(html)
    return ""


def list_recent_messages(limit: int = 25) -> list[dict]:
    imap = _connect()
    try:
        status, _ = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise MailReaderError("Could not open INBOX.")

        status, data = imap.uid("search", None, "ALL")
        if status != "OK":
            raise MailReaderError("IMAP search failed.")

        uids = data[0].split()
        recent_uids = uids[-limit:][::-1]

        messages = []
        for uid in recent_uids:
            status, fetch_data = imap.uid("fetch", uid, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.400>)")
            if status != "OK" or not fetch_data:
                continue

            header_bytes = b""
            text_bytes = b""
            for part in fetch_data:
                if isinstance(part, tuple):
                    section = part[0]
                    if b"HEADER" in section:
                        header_bytes = part[1]
                    elif b"TEXT" in section:
                        text_bytes = part[1]

            headers = BytesParser(policy=policy.default).parsebytes(header_bytes)
            date_str = headers.get("Date", "")
            try:
                date_iso = parsedate_to_datetime(date_str).isoformat() if date_str else ""
            except Exception:
                date_iso = date_str

            preview_source = text_bytes.decode("utf-8", errors="replace")
            preview = re.sub(r"\s+", " ", preview_source).strip()[:150]

            messages.append({
                "uid": uid.decode(),
                "from": str(headers.get("From", "")),
                "subject": str(headers.get("Subject", "(no subject)")),
                "date": date_iso,
                "preview": preview,
            })

        return messages
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def get_message(uid: str) -> dict:
    imap = _connect()
    try:
        status, _ = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise MailReaderError("Could not open INBOX.")

        status, data = imap.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            raise MailReaderError(f"Message {uid} not found.")

        raw = data[0][1]
        msg = BytesParser(policy=policy.default).parsebytes(raw)

        date_str = msg.get("Date", "")
        try:
            date_iso = parsedate_to_datetime(date_str).isoformat() if date_str else ""
        except Exception:
            date_iso = date_str

        return {
            "uid": uid,
            "from": str(msg.get("From", "")),
            "subject": str(msg.get("Subject", "(no subject)")),
            "date": date_iso,
            "message_id": str(msg.get("Message-ID", "")),
            "references": str(msg.get("References", "")),
            "body": _extract_body(msg),
        }
    finally:
        try:
            imap.logout()
        except Exception:
            pass
