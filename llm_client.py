"""Generates email draft options: Gemini first (free tier), OpenAI as a silent fallback on failure."""

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


def _parse_fallback(raw_text: str) -> DraftResponse:
    try:
        data = json.loads(raw_text)
        if isinstance(data, list):
            data = {"drafts": data}
        return DraftResponse.model_validate(data)
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw_text, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\}|\[.*\])", raw_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                data = {"drafts": data}
            return DraftResponse.model_validate(data)
        except Exception:
            pass

    logger.warning("Could not parse structured drafts from LLM output; returning raw text as a single draft.")
    return DraftResponse(drafts=[DraftEmail(subject="(could not parse model output)", body=raw_text or "<empty response>")])


def _generate_with_gemini(prompt: str, n: int) -> DraftResponse:
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
                "response_schema": DraftResponse,
            },
        )
    except genai_errors.APIError as e:
        raise LLMError(f"Gemini API error: {e}") from e
    except Exception as e:
        raise LLMError(f"Gemini request failed: {e}") from e

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, DraftResponse) and parsed.drafts:
        return parsed
    return _parse_fallback(response.text or "")


def _generate_with_openai(prompt: str, n: int) -> DraftResponse:
    if not config.OPENAI_API_KEY:
        raise LLMError("OpenAI not configured (no OPENAI_API_KEY)")

    from openai import OpenAI, OpenAIError

    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "draft_response",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "drafts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "subject": {"type": "string"},
                                        "body": {"type": "string"},
                                    },
                                    "required": ["subject", "body"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["drafts"],
                        "additionalProperties": False,
                    },
                },
            },
        )
    except OpenAIError as e:
        raise LLMError(f"OpenAI API error: {e}") from e
    except Exception as e:
        raise LLMError(f"OpenAI request failed: {e}") from e

    text = completion.choices[0].message.content or ""
    return _parse_fallback(text)


def generate_drafts(
    template: str | None,
    context: str,
    source_email: str | None = None,
    n: int = 3,
) -> tuple[list[dict], str]:
    """Returns (drafts, backend_used). Raises LLMError only if both backends fail/aren't configured."""
    prompt = _build_prompt(template, context, source_email, n)

    gemini_error: Exception | None = None
    try:
        result = _generate_with_gemini(prompt, n)
        return [d.model_dump() for d in result.drafts], "gemini"
    except LLMError as e:
        gemini_error = e
        logger.warning("Gemini draft generation failed, falling back to OpenAI: %s", e)

    try:
        result = _generate_with_openai(prompt, n)
        return [d.model_dump() for d in result.drafts], "openai"
    except LLMError as e:
        logger.error("OpenAI fallback also failed: %s", e)
        raise gemini_error or e
