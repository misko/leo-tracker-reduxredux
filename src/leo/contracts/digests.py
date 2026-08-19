"""Canonical JSON and content-digest primitives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from pydantic import StringConstraints

Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$"),
]


def sha256_digest(payload: bytes) -> str:
    """Return a tagged SHA-256 digest suitable for persisted contracts."""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def canonical_json_bytes(value: Any) -> bytes:
    """Encode an already JSON-compatible value deterministically."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(value: Mapping[str, Any] | Sequence[Any]) -> str:
    return sha256_digest(canonical_json_bytes(value))
