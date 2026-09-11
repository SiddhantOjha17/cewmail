"""Generates/refines email drafts: Gemini first (free tier), OpenAI as a silent fallback on failure."""

import json
import logging
import re

from pydantic import BaseModel, Field, create_model

import config

logger = logging.getLogger(__name__)

GENERIC_INSTRUCTION = (
    "Write a professional, concise email reply based on the context and "
    "(if given) the original email below. No template/category was selected, "
    "so use your best judgment on tone and structure."
)

SIGNOFF_INSTRUCTION = (
    "End the email with a short closing line (e.g. 'Best regards,') followed by "
    "the placeholder [Your Name] on its own line. Do not add a job title, company "
    "name, or contact details after it -- a real signature block with those "
    "details is appended automatically after your text."
)

PLACEHOLDER_INSTRUCTION = (
    "If the context above gives you real names, companies, amounts, dates, or "
    "other specifics, use them directly. For anything relevant that isn't given "
    "in the context, it's fine to leave a bracketed placeholder like [detail] for "
    "the sender to fill in before sending."
)

FORMATTING_INSTRUCTION = (
    "Write the body as plain text -- it is not rendered as markdown, so do not use "
    "markdown syntax like **bold**, _italics_, `code`, or # headings. Plain dashes "
    "for a simple list are fine."
)


class DraftEmail(BaseModel):
    subject: str
    body: str


class DraftResponse(BaseModel):
    drafts: list[DraftEmail]


def _make_strict_draft_schema(n: int) -> type[BaseModel]:
    """A DraftResponse variant with a hard-enforced array length, passed to the API's own
    structured-output mechanism so the model is actually constrained to produce exactly n
    drafts at generation time, rather than just being asked nicely in the prompt."""
    return create_model(
        "DraftResponseStrict",
        drafts=(list[DraftEmail], Field(min_length=n, max_length=n)),
    )


class LLMError(Exception):
    """Raised only for real API failures (auth, quota/rate-limit, network/timeout)."""


def _build_prompt(
    template: str | None,
    context: str,
    source_email: str | None,
    n: int,
    recipient: str | None = None,
    reply_direction: str | None = None,
) -> str:
    parts = [
        template.strip() if template else GENERIC_INSTRUCTION,
        "",
        f"Specific context for this email: {context.strip()}",
    ]
    if source_email:
        if reply_direction == "sent":
            origin_note = (
                "The reference email below is a PREVIOUS message the sender (you) already "
                "sent to the recipient -- it is written in YOUR voice, addressed TO the "
                "recipient, not the other way around. It's given only for context on what "
                "was previously discussed; do not mistake the name it's addressed to, or "
                "the name it's signed with, for who you are now writing to."
            )
        else:
            origin_note = (
                "The reference email below was sent TO you BY the recipient -- it is "
                "written in the recipient's voice. It's given only for context; do not "
                "quote or repeat it verbatim, just respond appropriately to it."
            )
        parts += [
            "",
            origin_note,
            "---",
            source_email.strip(),
            "---",
        ]
    if recipient:
        parts += [
            "",
            f"You are writing this new email TO: {recipient}. Address them by name if a "
            "name is given here, regardless of any other names that appear in the "
            "reference email above.",
        ]
    parts += [
        "",
        f"Generate exactly {n} distinct draft options (different in wording/approach, "
        "not just trivial rewording). Each needs a subject and a full body.",
        "",
        SIGNOFF_INSTRUCTION,
        PLACEHOLDER_INSTRUCTION,
        FORMATTING_INSTRUCTION,
    ]
    return "\n".join(parts)


def _build_tweak_prompt(subject: str, body: str, instruction: str) -> str:
    return "\n".join([
        "Here is an email draft:",
        f"Subject: {subject}",
        "Body:",
        body,
        "",
        f"Apply this specific tweak to it: {instruction.strip()}",
        "",
        "Keep everything else about the email the same unless the tweak requires "
        "changing it. Return the revised subject and body.",
        "",
        SIGNOFF_INSTRUCTION,
        PLACEHOLDER_INSTRUCTION,
        FORMATTING_INSTRUCTION,
    ])


def _parse_fallback(raw_text: str, schema: type[BaseModel]) -> BaseModel:
    """Parses with a schema that has no array-length constraints, so a technically-valid
    but short response (e.g. 2 drafts instead of 3) still comes back usable instead of
    being discarded for a synthetic error draft."""

    def _coerce(data):
        if isinstance(data, list) and "drafts" in schema.model_fields:
            data = {"drafts": data}
        return schema.model_validate(data)

    try:
        return _coerce(json.loads(raw_text))
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw_text, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\}|\[.*\])", raw_text, re.DOTALL)
    if match:
        try:
            return _coerce(json.loads(match.group(1)))
        except Exception:
            pass

    logger.warning("Could not parse structured output from LLM; falling back to raw text.")
    fallback_draft = DraftEmail(subject="(could not parse model output)", body=raw_text or "<empty response>")
    if "drafts" in schema.model_fields:
        return schema(drafts=[fallback_draft])
    return fallback_draft


def _call_gemini(prompt: str, strict_schema: type[BaseModel], lenient_schema: type[BaseModel]) -> BaseModel:
    if not config.GEMINI_API_KEY:
        raise LLMError("Gemini not configured (no GEMINI_API_KEY)")

    from google import genai
    from google.genai import errors as genai_errors

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": strict_schema,
            },
        )
    except genai_errors.APIError as e:
        raise LLMError(f"Gemini API error: {e}") from e
    except Exception as e:
        raise LLMError(f"Gemini request failed: {e}") from e

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, strict_schema):
        return parsed
    return _parse_fallback(response.text or "", lenient_schema)


def _call_openai(prompt: str, strict_schema: type[BaseModel], lenient_schema: type[BaseModel]) -> BaseModel:
    if not config.OPENAI_API_KEY:
        raise LLMError("OpenAI not configured (no OPENAI_API_KEY)")

    from openai import OpenAI, OpenAIError

    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        completion = client.chat.completions.parse(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format=strict_schema,
        )
    except OpenAIError as e:
        raise LLMError(f"OpenAI API error: {e}") from e
    except Exception as e:
        raise LLMError(f"OpenAI request failed: {e}") from e

    message = completion.choices[0].message
    if message.parsed is not None:
        return message.parsed
    return _parse_fallback(message.content or "", lenient_schema)


def _generate_structured(
    prompt: str,
    strict_schema: type[BaseModel],
    lenient_schema: type[BaseModel] | None = None,
) -> tuple[BaseModel, str]:
    """Tries Gemini first, then OpenAI. strict_schema is what's sent to the API's own
    structured-output mechanism (steers generation, e.g. enforces exact array length);
    lenient_schema (defaults to strict_schema) is used when manually parsing fallback
    text, so an imperfect-but-usable response isn't discarded over a strict mismatch.
    Raises LLMError only if both backends fail/aren't configured."""
    lenient_schema = lenient_schema or strict_schema

    gemini_error: Exception | None = None
    try:
        return _call_gemini(prompt, strict_schema, lenient_schema), "gemini"
    except LLMError as e:
        gemini_error = e
        logger.warning("Gemini call failed, falling back to OpenAI: %s", e)

    try:
        return _call_openai(prompt, strict_schema, lenient_schema), "openai"
    except LLMError as e:
        logger.error("OpenAI fallback also failed: %s", e)
        raise gemini_error or e


def generate_drafts(
    template: str | None,
    context: str,
    source_email: str | None = None,
    n: int = 3,
    recipient: str | None = None,
    reply_direction: str | None = None,
) -> tuple[list[dict], str]:
    """Returns (drafts, backend_used)."""
    prompt = _build_prompt(template, context, source_email, n, recipient, reply_direction)
    strict_schema = _make_strict_draft_schema(n)
    result, backend = _generate_structured(prompt, strict_schema, DraftResponse)
    return [d.model_dump() for d in result.drafts], backend


def tweak_draft(subject: str, body: str, instruction: str) -> tuple[dict, str]:
    """Revises a single draft per a free-text instruction. Returns (draft, backend_used)."""
    prompt = _build_tweak_prompt(subject, body, instruction)
    result, backend = _generate_structured(prompt, DraftEmail)
    return result.model_dump(), backend
