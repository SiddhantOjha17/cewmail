"""Generates/refines email drafts: Gemini first (free tier), OpenAI as a silent fallback on failure."""

import json
import logging
import re

from pydantic import BaseModel

import config

logger = logging.getLogger(__name__)

GENERIC_INSTRUCTION = (
    "Write a professional, concise email reply based on the context and "
    "(if given) the original email below. No template/category was selected, "
    "so use your best judgment on tone and structure."
)


class DraftEmail(BaseModel):
    subject: str
    body: str


class DraftResponse(BaseModel):
    drafts: list[DraftEmail]


class LLMError(Exception):
    """Raised only for real API failures (auth, quota/rate-limit, network/timeout)."""


def _build_prompt(template: str | None, context: str, source_email: str | None, n: int) -> str:
    parts = [
        template.strip() if template else GENERIC_INSTRUCTION,
        "",
        f"Specific context for this email: {context.strip()}",
    ]
    if source_email:
        parts += [
            "",
            "This is a reply. Below is the email you are replying to, for context only "
            "-- do not quote or repeat it verbatim, just respond appropriately to it:",
            "---",
            source_email.strip(),
            "---",
        ]
    parts += [
        "",
        f"Generate exactly {n} distinct draft options (different in wording/approach, "
        "not just trivial rewording). Each needs a subject and a full body.",
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
    ])


def _parse_fallback(raw_text: str, schema: type[BaseModel]) -> BaseModel:
    def _coerce(data):
        if schema is DraftResponse and isinstance(data, list):
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
    if schema is DraftResponse:
        return DraftResponse(drafts=[DraftEmail(subject="(could not parse model output)", body=raw_text or "<empty response>")])
    return DraftEmail(subject="(could not parse model output)", body=raw_text or "<empty response>")


def _call_gemini(prompt: str, schema: type[BaseModel]) -> BaseModel:
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
                "response_schema": schema,
            },
        )
    except genai_errors.APIError as e:
        raise LLMError(f"Gemini API error: {e}") from e
    except Exception as e:
        raise LLMError(f"Gemini request failed: {e}") from e

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    return _parse_fallback(response.text or "", schema)


def _call_openai(prompt: str, schema: type[BaseModel]) -> BaseModel:
    if not config.OPENAI_API_KEY:
        raise LLMError("OpenAI not configured (no OPENAI_API_KEY)")

    from openai import OpenAI, OpenAIError

    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        completion = client.chat.completions.parse(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format=schema,
        )
    except OpenAIError as e:
        raise LLMError(f"OpenAI API error: {e}") from e
    except Exception as e:
        raise LLMError(f"OpenAI request failed: {e}") from e

    message = completion.choices[0].message
    if message.parsed is not None:
        return message.parsed
    return _parse_fallback(message.content or "", schema)


def _generate_structured(prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, str]:
    """Tries Gemini first, then OpenAI. Raises LLMError only if both fail/aren't configured."""
    gemini_error: Exception | None = None
    try:
        return _call_gemini(prompt, schema), "gemini"
    except LLMError as e:
        gemini_error = e
        logger.warning("Gemini call failed, falling back to OpenAI: %s", e)

    try:
        return _call_openai(prompt, schema), "openai"
    except LLMError as e:
        logger.error("OpenAI fallback also failed: %s", e)
        raise gemini_error or e


def generate_drafts(
    template: str | None,
    context: str,
    source_email: str | None = None,
    n: int = 3,
) -> tuple[list[dict], str]:
    """Returns (drafts, backend_used)."""
    prompt = _build_prompt(template, context, source_email, n)
    result, backend = _generate_structured(prompt, DraftResponse)
    return [d.model_dump() for d in result.drafts], backend


def tweak_draft(subject: str, body: str, instruction: str) -> tuple[dict, str]:
    """Revises a single draft per a free-text instruction. Returns (draft, backend_used)."""
    prompt = _build_tweak_prompt(subject, body, instruction)
    result, backend = _generate_structured(prompt, DraftEmail)
    return result.model_dump(), backend
