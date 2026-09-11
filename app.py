import logging

from flask import Flask, jsonify, render_template, request

import config
import email_signature
import llm_client
import mail_reader
import mailer
import template_store

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # hard cap slightly above our own attachment check


@app.route("/")
def index():
    categories = template_store.list_categories()
    return render_template(
        "index.html",
        categories=[{"name": c, "label": template_store.pretty_name(c)} for c in categories],
        signature_html=email_signature.get_signature_html(),
    )


@app.route("/api/categories", methods=["GET"])
def api_list_categories():
    categories = template_store.list_categories()
    return jsonify({
        "categories": [{"name": c, "label": template_store.pretty_name(c)} for c in categories],
    })


@app.route("/api/categories", methods=["POST"])
def api_add_category():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    template = data.get("template", "")

    if not template.strip():
        return jsonify({"error": "Template body cannot be empty."}), 400

    try:
        saved_name = template_store.save_template(name, template)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileExistsError:
        return jsonify({"error": f"Category '{name}' already exists."}), 409

    return jsonify({"name": saved_name, "label": template_store.pretty_name(saved_name)}), 201


@app.route("/api/inbox", methods=["GET"])
def api_inbox():
    limit = request.args.get("limit", default=25, type=int)
    query = request.args.get("q", default="", type=str)
    try:
        if query.strip():
            messages = mail_reader.search_messages(query, limit=limit)
        else:
            messages = mail_reader.list_recent_messages(limit=limit)
    except mail_reader.MailReaderError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"messages": messages})


@app.route("/api/inbox/<uid>", methods=["GET"])
def api_inbox_message(uid):
    try:
        message = mail_reader.get_message(uid)
    except mail_reader.MailReaderError as e:
        return jsonify({"error": str(e)}), 502
    message["reply_subject"] = mailer.clean_subject_for_reply(message["subject"])
    return jsonify(message)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or {}
    category = (data.get("category") or "").strip()
    context = (data.get("context") or "").strip()
    source_email = data.get("source_email") or None
    recipient = data.get("recipient") or None
    reply_direction = data.get("reply_direction") or None

    if not context:
        return jsonify({"error": "Please describe the context for this email."}), 400

    template = None
    if category:
        try:
            template = template_store.get_template(category)
        except FileNotFoundError:
            return jsonify({"error": f"Unknown category '{category}'."}), 400

    try:
        drafts, backend = llm_client.generate_drafts(
            template, context,
            source_email=source_email, n=3,
            recipient=recipient, reply_direction=reply_direction,
        )
    except llm_client.LLMError as e:
        return jsonify({"error": f"Could not generate drafts: {e}"}), 502

    return jsonify({"drafts": drafts, "backend": backend})


@app.route("/api/tweak", methods=["POST"])
def api_tweak():
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    instruction = (data.get("instruction") or "").strip()

    if not subject or not body:
        return jsonify({"error": "Nothing to tweak yet -- pick or write a draft first."}), 400
    if not instruction:
        return jsonify({"error": "Please specify what to tweak."}), 400

    try:
        draft, backend = llm_client.tweak_draft(subject, body, instruction)
    except llm_client.LLMError as e:
        return jsonify({"error": f"Could not apply tweak: {e}"}), 502

    return jsonify({"draft": draft, "backend": backend})


@app.route("/api/send", methods=["POST"])
def api_send():
    recipient = request.form.get("recipient", "")
    subject = request.form.get("subject", "")
    body = request.form.get("body", "")
    in_reply_to = request.form.get("in_reply_to") or None
    references = request.form.get("references") or None
    attachments = request.files.getlist("attachments")

    try:
        mailer.send_email(
            recipient, subject, body,
            attachments=attachments,
            in_reply_to=in_reply_to,
            references=references,
        )
    except mailer.MailerError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"status": "sent"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=config.FLASK_PORT, threaded=True)
