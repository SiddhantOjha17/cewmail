"""Reads recent mail from the same Gmail account over IMAP (app password works for IMAP too)."""

import imaplib
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

import config

# Bytes fetched per message for the list/search preview -- a partial fetch, so the IMAP
# server slices before sending regardless of how big the full message (or its attachments)
# actually is. Comfortably covers headers + a typical business email's text body without
# ever pulling attachment bytes over the wire.
PREVIEW_FETCH_BYTES = 12000

_UID_RE = re.compile(rb"UID (\d+)")


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


def _parse_fetch_response(fetch_data) -> list[dict]:
    """Parses a (possibly multi-message) FETCH response fetched via a single batched
    command, so this is O(1) network round trips regardless of how many messages matched.
    Each message may come back with a partial/truncated body (see PREVIEW_FETCH_BYTES);
    email.parser tolerates that fine for extracting the headers and an early text part."""
    messages = []
    for part in fetch_data:
        if not isinstance(part, tuple):
            continue
        descriptor, raw = part
        uid_match = _UID_RE.search(descriptor)
        if not uid_match:
            continue
        uid = uid_match.group(1).decode()

        msg = BytesParser(policy=policy.default).parsebytes(raw)

        date_str = msg.get("Date", "")
        try:
            date_iso = parsedate_to_datetime(date_str).isoformat() if date_str else ""
        except Exception:
            date_iso = date_str

        body = _extract_body(msg)
        preview = re.sub(r"\s+", " ", body).strip()[:150]

        messages.append({
            "uid": uid,
            "from": str(msg.get("From", "")),
            "subject": str(msg.get("Subject", "(no subject)")),
            "date": date_iso,
            "preview": preview,
        })

    messages.sort(key=lambda m: int(m["uid"]), reverse=True)  # newest first, regardless of response order
    return messages


def _fetch_summaries_by_seq(imap: imaplib.IMAP4_SSL, seq_range: str) -> list[dict]:
    status, fetch_data = imap.fetch(seq_range, f"(UID BODY.PEEK[]<0.{PREVIEW_FETCH_BYTES}>)")
    if status != "OK":
        raise MailReaderError("IMAP fetch failed.")
    return _parse_fetch_response(fetch_data)


def _fetch_summaries_by_uid(imap: imaplib.IMAP4_SSL, uids: list[bytes]) -> list[dict]:
    if not uids:
        return []
    uid_set = b",".join(uids)
    status, fetch_data = imap.uid("fetch", uid_set, f"(UID BODY.PEEK[]<0.{PREVIEW_FETCH_BYTES}>)")
    if status != "OK":
        raise MailReaderError("IMAP fetch failed.")
    return _parse_fetch_response(fetch_data)


def list_recent_messages(limit: int = 25) -> list[dict]:
    imap = _connect()
    try:
        status, data = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise MailReaderError("Could not open INBOX.")

        # SELECT's response already gives the total message count (EXISTS) -- no need for
        # a separate "SEARCH ALL" just to find out how many messages exist and slice the
        # last N; that used to list every single UID in the mailbox before trimming it down.
        total = int(data[0]) if data and data[0] else 0
        if total == 0:
            return []

        start = max(1, total - limit + 1)
        return _fetch_summaries_by_seq(imap, f"{start}:{total}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def search_messages(query: str, limit: int = 25) -> list[dict]:
    """Searches the whole mailbox (not just the recently-fetched list) via Gmail's
    X-GM-RAW extension -- the same search Gmail's own web UI does, including support for
    operators like from:/subject:. A plain multi-word query (no operator) is wrapped as an
    exact phrase rather than Gmail's default loose AND-of-words match, which tends to feel
    more relevant for "find this email" style searches. Falls back to the recent list if
    the query is empty."""
    query = (query or "").strip()
    if not query:
        return list_recent_messages(limit=limit)

    imap = _connect()
    try:
        status, _ = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise MailReaderError("Could not open INBOX.")

        gmail_query = query if ":" in query else f'"{query}"'
        imap_literal = '"' + gmail_query.replace("\\", "\\\\").replace('"', '\\"') + '"'
        status, data = imap.uid("search", None, "X-GM-RAW", imap_literal)
        if status != "OK":
            raise MailReaderError("IMAP search failed.")

        uids = data[0].split()
        matched_uids = uids[-limit:]  # cap to the most recent `limit` matches (by UID order)
        return _fetch_summaries_by_uid(imap, matched_uids)
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
