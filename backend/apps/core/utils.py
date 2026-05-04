"""Shared utilities for the project."""
import hashlib
import logging
from datetime import datetime, date
from typing import Any, Optional

logger = logging.getLogger(__name__)


def compute_content_hash(content: str) -> str:
    """Return SHA-256 hash of string content for change detection."""
    if content is None:
        return ''
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def compute_sporting_age(birth_year: int, reference_year: Optional[int] = None) -> int:
    """
    Calculate 'sporting age' per CBT / FPT rules:
    age = reference_year - birth_year (ignores month/day).
    """
    if reference_year is None:
        reference_year = datetime.now().year
    return reference_year - birth_year


def safe_get(d: dict, *keys, default: Any = None) -> Any:
    """Safely access nested dict keys."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def diff_dicts(old: dict, new: dict) -> dict:
    """Return a dict of fields that changed (old != new) with tuple (old, new)."""
    changes = {}
    all_keys = set(old.keys()) | set(new.keys())
    for k in all_keys:
        a = old.get(k)
        b = new.get(k)
        if a != b:
            changes[k] = {'old': a, 'new': b}
    return changes


def to_iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
