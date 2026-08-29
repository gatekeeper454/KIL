"""Canonical serialization for deterministic KIL decision artifacts."""

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Any


def _normalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical values require a finite Decimal")
        return format(value, "f")
    if isinstance(value, dict):
        if not all(type(key) is str for key in value):
            raise TypeError("canonical dictionary keys must be strings")
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if value is None or type(value) in (str, bool, int):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return a stable UTF-8-ready JSON representation of ``value``."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_digest(value: Any) -> str:
    """Return the SHA-256 hex digest of the canonical JSON representation."""
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
