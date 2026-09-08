"""Sends email via Gmail SMTP (app password), stdlib only, attachments read straight from upload streams."""

import html as html_module
import mimetypes
import smtplib
from email.message import EmailMessage

import config
import email_signature


class MailerError(Exception):
    """Raised for validation failures or SMTP errors, with a message safe to show the user."""


def clean_subject_for_reply(subject: str) -> str:
    subject = (subject or "").strip()
    if not subject:
        return "Re:"
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def _body_to_html(body: str) -> str:
    return html_module.escape(body).replace("\n", "<br>\n")


def _build_bodies(body: str) -> tuple[str, str]:
    """Returns (plain_text, html) with the signature appended to both."""
    signature_text = email_signature.get_signature_text()
    signature_html = email_signature.get_signature_html()

    plain = f"{body}\n\n{signature_text}" if signature_text else body

    html_parts = [f'<div style="font-family: Arial, sans-serif; font-size: 15px; '
                  f'line-height: 1.5; color: #111111;">{_body_to_html(body)}</div>']
    if signature_html:
        html_parts.append(signature_html)
    html = "\n".join(html_parts)

    return plain, html


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments=None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> None:
    to = (to or "").strip()
    subject = (subject or "").strip()
    body = (body or "").strip()

    if not to or "@" not in to:
        raise MailerError("Recipient email address is missing or invalid.")
    if not subject:
        raise MailerError("Subject is empty.")
    if not body:
        raise MailerError("Body is empty.")
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise MailerError("Gmail credentials are not configured (check .env).")

    attachments = attachments or []
    total_size = 0
    read_attachments = []
    for f in attachments:
        if not f or not f.filename:
            continue
        data = f.read()
        total_size += len(data)
        read_attachments.append((f.filename, data))

    if total_size > config.MAX_ATTACHMENT_BYTES:
        raise MailerError(
            f"Attachments are too large ({total_size / 1024 / 1024:.1f} MB); "
            f"keep combined attachments under {config.MAX_ATTACHMENT_BYTES / 1024 / 1024:.0f} MB."
        )

    plain_body, html_body = _build_bodies(body)

    msg = EmailMessage()
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    for filename, data in read_attachments:
        mime_type, _ = mimetypes.guess_type(filename)
        maintype, _, subtype = (mime_type or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise MailerError("Gmail rejected the login -- check GMAIL_ADDRESS/GMAIL_APP_PASSWORD in .env.") from e
    except smtplib.SMTPException as e:
        raise MailerError(f"SMTP error while sending: {e}") from e
    except OSError as e:
        raise MailerError(f"Network error while sending (check connectivity/firewall): {e}") from e
