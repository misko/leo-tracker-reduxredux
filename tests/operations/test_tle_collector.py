from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo.operations.tle_collector import CollectionError, collect_provider


def _catalog(count: int = 1_000) -> bytes:
    lines = []
    for index in range(count):
        catalog_id = 10_000 + index
        lines.extend(
            (
                f"STARLINK-{catalog_id}",
                f"1 {catalog_id:05d}U 24001A   24200.50000000  .00000000  00000-0  00000-0 0  9999",
                f"2 {catalog_id:05d}  53.0000 100.0000 0001000  10.0000 350.0000 15.00000000    01",
            )
        )
    return ("\n".join(lines) + "\n").encode()


def test_space_track_has_persistent_attempt_and_success_hourly_guards(tmp_path: Path) -> None:
    calls = 0

    def fetch() -> bytes:
        nonlocal calls
        calls += 1
        return _catalog()

    first = collect_provider(tmp_path, "space-track", now_ns=1_000_000_000_000, fetcher=fetch)
    limited = collect_provider(
        tmp_path,
        "space-track",
        now_ns=1_000_000_000_000 + 3_599_000_000_000,
        fetcher=fetch,
    )

    assert first.status == "published" and first.satellite_count == 1_000
    assert limited.status == "rate_limited"
    assert calls == 1
    state = json.loads((tmp_path / "state/space-track.json").read_text())
    assert state["last_attempt_utc_ns"] == state["last_success_utc_ns"]
    assert len(tuple((tmp_path / "archive/space-track").glob("*.tle"))) == 1


def test_failed_attempt_is_also_rate_limited(tmp_path: Path) -> None:
    def fail() -> bytes:
        raise RuntimeError("provider unavailable")

    try:
        collect_provider(tmp_path, "space-track", now_ns=2_000_000_000_000, fetcher=fail)
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed fetch must propagate")

    result = collect_provider(
        tmp_path,
        "space-track",
        now_ns=2_000_000_000_000 + 1_000_000_000,
        fetcher=_catalog,
    )
    assert result.status == "rate_limited"


def test_hugging_face_uses_six_hour_success_guard(tmp_path: Path) -> None:
    first = collect_provider(tmp_path, "huggingface", now_ns=3_000_000_000_000, fetcher=_catalog)
    limited = collect_provider(
        tmp_path,
        "huggingface",
        now_ns=3_000_000_000_000 + 3_600_000_000_000,
        fetcher=_catalog,
    )
    assert first.status == "published"
    assert limited.status == "rate_limited"


def test_rate_state_rejects_a_non_integer_timestamp(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "huggingface.json").write_text('{"last_attempt_utc_ns":"not-a-time"}\n')

    with pytest.raises(CollectionError, match="rate state is invalid"):
        collect_provider(tmp_path, "huggingface", now_ns=3_000_000_000_000, fetcher=_catalog)
