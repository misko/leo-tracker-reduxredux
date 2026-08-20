"""Bounded local Starlink TLE collection with durable provider rate gates."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import http.cookiejar
import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_SPACE_TRACK_LOGIN = "https://www.space-track.org/ajaxauth/login"
_SPACE_TRACK_QUERY = (
    "https://www.space-track.org/basicspacedata/query/class/gp/"
    "OBJECT_NAME/~~STARLINK/decay_date/null-val/epoch/%3Enow-10/"
    "orderby/NORAD_CAT_ID/format/3le"
)
_SPACE_TRACK_LOGOUT = "https://www.space-track.org/ajaxauth/logout"
_HUGGING_FACE_QUERY = (
    "https://huggingface.co/datasets/juliensimon/starlink-tle-latest/"
    "resolve/main/data/starlink.tle"
)
_MAX_BYTES = 16 * 1024 * 1024
_TIMEOUT_S = 30
_HOUR_NS = 3_600_000_000_000
_HF_INTERVAL_NS = 21_600_000_000_000


class CollectionError(RuntimeError):
    """Sanitized collection failure."""


@dataclass(frozen=True, slots=True)
class CollectionResult:
    provider: str
    status: str
    satellite_count: int | None = None
    digest: str | None = None


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _read_state(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionError("provider rate state is invalid") from error
    if not isinstance(value, dict):
        raise CollectionError("provider rate state is invalid")
    return value


def _read_bounded(response: BinaryIO) -> bytes:
    body = response.read(_MAX_BYTES + 1)
    if len(body) > _MAX_BYTES:
        raise CollectionError("provider response exceeds byte bound")
    return body


def _credential(name: str) -> str:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if directory is None:
        raise CollectionError("Space-Track credential capability is unavailable")
    path = Path(directory) / name
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise CollectionError("Space-Track credential capability is unavailable") from error
    if not value:
        raise CollectionError("Space-Track credential capability is empty")
    return value


def _space_track_fetch() -> bytes:
    identity = _credential("space-track-identity")
    password = _credential("space-track-password")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    login = urllib.request.Request(
        _SPACE_TRACK_LOGIN,
        data=urllib.parse.urlencode({"identity": identity, "password": password}).encode(),
        method="POST",
    )
    try:
        with opener.open(login, timeout=_TIMEOUT_S) as response:
            _read_bounded(response)
        with opener.open(_SPACE_TRACK_QUERY, timeout=_TIMEOUT_S) as response:
            return _read_bounded(response)
    finally:
        with contextlib.suppress(Exception):
            opener.open(_SPACE_TRACK_LOGOUT, timeout=_TIMEOUT_S).close()


def _hugging_face_fetch() -> bytes:
    with urllib.request.urlopen(_HUGGING_FACE_QUERY, timeout=_TIMEOUT_S) as response:
        return _read_bounded(response)


def _tle_count(body: bytes) -> int:
    try:
        lines = [line.strip() for line in body.decode("ascii").splitlines() if line.strip()]
    except UnicodeDecodeError as error:
        raise CollectionError("provider response is not ASCII TLE data") from error
    element_ones = [line for line in lines if line.startswith("1 ")]
    element_twos = [line for line in lines if line.startswith("2 ")]
    if len(element_ones) != len(element_twos) or not 1_000 <= len(element_ones) <= 20_000:
        raise CollectionError("provider response has invalid Starlink TLE inventory")
    return len(element_ones)


def collect_provider(
    root: Path,
    provider: str,
    *,
    now_ns: int | None = None,
    fetcher: Callable[[], bytes] | None = None,
) -> CollectionResult:
    """Collect once if both persistent attempt and success gates permit it."""

    if provider not in {"space-track", "huggingface"}:
        raise ValueError("unsupported TLE provider")
    root.mkdir(parents=True, exist_ok=True)
    state_root = root / "state"
    archive_root = root / "archive" / provider
    state_root.mkdir(exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / f"{provider}.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state_path = state_root / f"{provider}.json"
        state = _read_state(state_path)
        current = time.time_ns() if now_ns is None else now_ns
        interval = _HOUR_NS if provider == "space-track" else _HF_INTERVAL_NS
        for field in ("last_attempt_utc_ns", "last_success_utc_ns"):
            previous = state.get(field)
            if previous is not None and current - int(previous) < interval:
                return CollectionResult(provider, "rate_limited")
        state.update({"provider": provider, "last_attempt_utc_ns": current})
        _atomic_json(state_path, state)
        selected_fetcher = fetcher or (
            _space_track_fetch if provider == "space-track" else _hugging_face_fetch
        )
        body = selected_fetcher()
        count = _tle_count(body)
        digest = hashlib.sha256(body).hexdigest()
        destination = archive_root / f"{current}-{digest}.tle"
        with destination.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        state.update(
            {
                "last_success_utc_ns": current,
                "last_digest": f"sha256:{digest}",
                "satellite_count": count,
            }
        )
        _atomic_json(state_path, state)
        return CollectionResult(provider, "published", count, f"sha256:{digest}")
    finally:
        os.close(descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    results: list[CollectionResult] = []
    errors: list[dict[str, str]] = []
    for provider in ("space-track", "huggingface"):
        try:
            results.append(collect_provider(args.root, provider))
        except Exception as error:
            errors.append({"provider": provider, "detail": type(error).__name__})
    print(
        json.dumps(
            {
                "event": "tle_collection",
                "providers": [
                    {
                        "provider": item.provider,
                        "status": item.status,
                        "satellite_count": item.satellite_count,
                        "digest": item.digest,
                    }
                    for item in results
                ],
                "errors": errors,
            },
            sort_keys=True,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
