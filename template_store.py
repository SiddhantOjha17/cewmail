"""Email category templates, stored as one .txt file per category under email_templates/."""

import re

from config import EMAIL_TEMPLATES_DIR

# Windows reserved device names -- can't be used as filenames even with an extension.
_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def sanitize_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        raise ValueError("Category name is empty after sanitization")
    if name in _RESERVED_NAMES:
        name = f"cat_{name}"
    return name


_ACRONYMS = {"po", "gst", "poc"}


def pretty_name(name: str) -> str:
    words = name.replace("_", " ").strip().split()
    return " ".join(w.upper() if w.lower() in _ACRONYMS else w.capitalize() for w in words)


def list_categories() -> list[str]:
    EMAIL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in EMAIL_TEMPLATES_DIR.glob("*.txt"))


def get_template(name: str) -> str:
    path = EMAIL_TEMPLATES_DIR / f"{sanitize_name(name)}.txt"
    if not path.is_file():
        raise FileNotFoundError(name)
    return path.read_text(encoding="utf-8")


def save_template(name: str, body: str, overwrite: bool = False) -> str:
    EMAIL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    safe = sanitize_name(name)
    path = EMAIL_TEMPLATES_DIR / f"{safe}.txt"
    if path.exists() and not overwrite:
        raise FileExistsError(safe)
    path.write_text(body, encoding="utf-8")
    return safe
