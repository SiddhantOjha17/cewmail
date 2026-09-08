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


def _fetch_summaries(imap: imaplib.IMAP4_SSL, uids: list[bytes]) -> list[dict]:
    messages = []
    for uid in uids:
        # Fetch the full message rather than a raw BODY[TEXT] byte-range: most real
        # email is multipart, and a raw slice of the MIME source is boundary markers
        # and sub-part headers, not readable text. _extract_body() below correctly
        # walks the MIME tree to find the actual text/plain (or html-stripped) content.
        status, fetch_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK" or not fetch_data or not isinstance(fetch_data[0], tuple):
            continue

        raw = fetch_data[0][1]
        msg = BytesParser(policy=policy.default).parsebytes(raw)

        date_str = msg.get("Date", "")
        try:
            date_iso = parsedate_to_datetime(date_str).isoformat() if date_str else ""
        except Exception:
            date_iso = date_str

        body = _extract_body(msg)
        preview = re.sub(r"\s+", " ", body).strip()[:150]

        messages.append({
            "uid": uid.decode(),
            "from": str(msg.get("From", "")),
            "subject": str(msg.get("Subject", "(no subject)")),
            "date": date_iso,
            "preview": preview,
        })

    return messages


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
        return _fetch_summaries(imap, recent_uids)
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def search_messages(query: str, limit: int = 25) -> list[dict]:
    """Searches the whole mailbox (not just the recently-fetched list) via IMAP's TEXT
    criterion, which matches against headers (from/subject) and body. Falls back to the
    recent list if the query is empty."""
    query = (query or "").strip()
    if not query:
        return list_recent_messages(limit=limit)

    imap = _connect()
    try:
        status, _ = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise MailReaderError("Could not open INBOX.")

        # Gmail's IMAP server supports X-GM-RAW: the exact same search Gmail's own web
        # search box does (and it accepts Gmail search operators like from:/subject: too),
        # which gives far more relevant results than the generic RFC3501 TEXT criterion --
        # Gmail routes TEXT through its own tokenized index rather than literal substring
        # matching, so results for it can look surprisingly unrelated to the query.
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        status, data = imap.uid("search", None, "X-GM-RAW", f'"{escaped}"')
        if status != "OK":
            raise MailReaderError("IMAP search failed.")

        uids = data[0].split()
        matched_uids = uids[-limit:][::-1]  # newest matches first
        return _fetch_summaries(imap, matched_uids)
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
