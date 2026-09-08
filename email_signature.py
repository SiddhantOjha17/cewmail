"""Company email signature -- appended automatically at send time, kept separate from
what the LLM writes so it's always exact (never paraphrased or dropped by a tweak).

Edit signature/signature.html and signature/signature.txt directly to change it.
"""

from pathlib import Path

SIGNATURE_DIR = Path(__file__).parent / "signature"


def get_signature_html() -> str:
    path = SIGNATURE_DIR / "signature.html"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def get_signature_text() -> str:
    path = SIGNATURE_DIR / "signature.txt"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""
