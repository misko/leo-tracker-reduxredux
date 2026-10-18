"""Confinement-aware resolution of stable ``bulk://`` artifact URIs."""

from __future__ import annotations

import os
import re
import stat
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from leo.storage.errors import PathConfinementError
from leo.storage.pinned import PinnedLocalRoot

_RECORDING_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def parse_recording_bundle_uri(uri: str) -> str:
    """Return the session ID from one canonical dated recording-bundle URI."""

    parsed = urlsplit(uri)
    if (
        parsed.scheme != "bulk"
        or parsed.netloc != "recordings"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
    ):
        raise PathConfinementError("recording bundle URI must use bulk://recordings")
    raw_parts = parsed.path.removeprefix("/").split("/")
    if len(raw_parts) != 4 or any(not part for part in raw_parts):
        raise PathConfinementError("recording bundle URI must have YYYY/MM/DD/session geometry")
    raw_year, raw_month, raw_day, raw_session_id = raw_parts
    if (
        len(raw_year) != 4
        or len(raw_month) != 2
        or len(raw_day) != 2
        or not (raw_year + raw_month + raw_day).isdigit()
    ):
        raise PathConfinementError("recording bundle URI date is not canonical")
    try:
        date(int(raw_year), int(raw_month), int(raw_day))
    except ValueError as error:
        raise PathConfinementError("recording bundle URI date is invalid") from error
    session_id = unquote(raw_session_id)
    if not _RECORDING_SESSION_ID.fullmatch(session_id):
        raise PathConfinementError("recording bundle URI session ID is unsafe")
    if quote(session_id, safe="._-:") != raw_session_id:
        raise PathConfinementError("recording bundle URI session ID is not canonically encoded")
    return session_id


class BulkUriResolver:
    """Map logical bulk URIs to descendants of one configured local root."""

    def __init__(
        self,
        root: Path,
        *,
        allowed_namespaces: tuple[str, ...] = ("recordings", "analysis", "test-corpus"),
        create: bool = True,
        pinned: bool = False,
        pinned_namespace: tuple[str, PinnedLocalRoot] | None = None,
    ) -> None:
        if pinned_namespace is not None and (create or pinned):
            raise ValueError("pinned namespace resolver has incompatible options")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        self._namespace_capability = None if pinned_namespace is None else pinned_namespace[1]
        self._namespace = None if pinned_namespace is None else pinned_namespace[0]
        self.root = root if pinned or pinned_namespace is not None else root.resolve(strict=True)
        self._pinned = pinned or pinned_namespace is not None
        if not allowed_namespaces or len(set(allowed_namespaces)) != len(allowed_namespaces):
            raise ValueError("bulk URI namespaces must be non-empty and unique")
        if any(
            not item or item in {".", ".."} or "/" in item or "\\" in item
            for item in allowed_namespaces
        ):
            raise ValueError("bulk URI namespace is not one safe path component")
        self.allowed_namespaces = allowed_namespaces
        if self._namespace is not None and self._namespace not in allowed_namespaces:
            raise ValueError("pinned namespace is outside the allowed namespaces")

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
        if self._namespace_capability is not None:
            if parsed.netloc != self._namespace:
                raise PathConfinementError(f"invalid pinned bulk namespace: {uri!r}")
            self._namespace_capability.assert_open()
            namespace_root = self._namespace_capability.io_root
            candidate = namespace_root / Path(*parts)
            return confined_path(
                namespace_root,
                candidate,
                must_exist=must_exist,
                retain_lexical=True,
            )
        candidate = self.root / parsed.netloc / Path(*parts)
        return confined_path(
            self.root,
            candidate,
            must_exist=must_exist,
            retain_lexical=self._pinned,
        )

    def uri_for(self, path: Path) -> str:
        if self._namespace_capability is not None:
            self._namespace_capability.assert_open()
            namespace_root = self._namespace_capability.io_root
            candidate = confined_path(
                namespace_root,
                path,
                must_exist=True,
                retain_lexical=True,
            )
            relative = candidate.relative_to(namespace_root)
            if not relative.parts:
                raise PathConfinementError("bulk URI must identify a namespace descendant")
            encoded = "/".join(quote(part, safe="._-:") for part in relative.parts)
            return f"bulk://{self._namespace}/{encoded}"
        candidate = confined_path(
            self.root,
            path,
            must_exist=True,
            retain_lexical=self._pinned,
        )
        relative = candidate.relative_to(self.root)
        if len(relative.parts) < 2 or relative.parts[0] not in self.allowed_namespaces:
            raise PathConfinementError("path is not inside a public bulk namespace")
        namespace, *parts = relative.parts
        encoded = "/".join(quote(part, safe="._-:") for part in parts)
        return f"bulk://{namespace}/{encoded}"


def confined_path(
    root: Path,
    candidate: Path,
    *,
    must_exist: bool,
    retain_lexical: bool = False,
) -> Path:
    """Resolve a path and reject escapes or symlinked descendants."""

    if root.parts[:4] == ("/", "proc", "self", "fd"):
        retain_lexical = True
    canonical_root = root.resolve(strict=True)
    lexical_root = root if retain_lexical else canonical_root
    lexical = candidate if candidate.is_absolute() else lexical_root / candidate
    try:
        lexical_relative = lexical.relative_to(lexical_root)
    except ValueError as error:
        raise PathConfinementError(f"path escapes bulk root: {candidate}") from error

    current = lexical_root
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
    return lexical if retain_lexical else resolved
