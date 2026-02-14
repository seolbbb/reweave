"""File naming utilities for vault output."""

from __future__ import annotations

import re


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a URL-friendly slug for filenames."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:max_length].strip("-")


def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    return re.sub(r'[<>:"/\\|?*]', "", name)
