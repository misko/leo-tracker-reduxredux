"""Confinement-aware resolution of stable ``bulk://`` artifact URIs."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from leo.storage.errors import PathConfinementError


class BulkUriResolver:
    """Map logical bulk URIs to descendants of one configured local root."""

    def __init__(
        self,
        root: Path,
        *,
        allowed_namespaces: tuple[str, ...] = ("recordings", "analysis", "test-corpus"),
        create: bool = True,
    ) -> None:
        if create:
            root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        if not allowed_namespaces or len(set(allowed_namespaces)) != len(allowed_namespaces):
            raise ValueError("bulk URI namespaces must be non-empty and unique")
        if any(
            not item or item in {".", ".."} or "/" in item or "\\" in item
            for item in allowed_namespaces
        ):
            raise ValueError("bulk URI namespace is not one safe path component")
        self.allowed_namespaces = allowed_namespaces

    def resolve(self, uri: str, *, must_exist: bool = True) -> Path:
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "bulk"
            or parsed.netloc not in self.allowed_namespaces
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise PathConfinementError(f"invalid or disallowed bulk URI: {uri!r}")
        raw_parts = parsed.path.removeprefix("/").split("/")
        if not raw_parts or any(not part for part in raw_parts):
            raise PathConfinementError("bulk URI requires non-empty canonical path components")
        parts: list[str] = []
        for raw_part in raw_parts:
            part = unquote(raw_part)
            if part in {"", ".", ".."} or "/" in part or "\\" in part or "\0" in part:
                raise PathConfinementError("bulk URI contains an unsafe path component")
            parts.append(part)
        candidate = self.root / parsed.netloc / Path(*parts)
        return confined_path(self.root, candidate, must_exist=must_exist)

    def uri_for(self, path: Path) -> str:
        candidate = confined_path(self.root, path, must_exist=True)
        relative = candidate.relative_to(self.root)
        if len(relative.parts) < 2 or relative.parts[0] not in self.allowed_namespaces:
            raise PathConfinementError("path is not inside a public bulk namespace")
        namespace, *parts = relative.parts
        encoded = "/".join(quote(part, safe="._-:") for part in parts)
        return f"bulk://{namespace}/{encoded}"


def confined_path(root: Path, candidate: Path, *, must_exist: bool) -> Path:
    """Resolve a path and reject escapes or symlinked descendants."""

    canonical_root = root.resolve(strict=True)
    lexical = candidate if candidate.is_absolute() else canonical_root / candidate
    try:
        lexical_relative = lexical.relative_to(canonical_root)
    except ValueError as error:
        raise PathConfinementError(f"path escapes bulk root: {candidate}") from error

    current = canonical_root
    for part in lexical_relative.parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise PathConfinementError(f"symlinked bulk path is not allowed: {current}")

    try:
        resolved = lexical.resolve(strict=must_exist)
    except FileNotFoundError:
        raise
    try:
        resolved.relative_to(canonical_root)
    except ValueError as error:
        raise PathConfinementError(f"resolved path escapes bulk root: {candidate}") from error
    return resolved
