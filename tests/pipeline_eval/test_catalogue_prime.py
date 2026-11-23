import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import catalogue_prime as trial


def ref(hour, digest):
    return SimpleNamespace(collected_utc_ns=hour * trial.HOUR_NS, sha256=digest,
                           path=Path(f"{hour}-{digest}.tle"), byte_size=8)


def test_prime_source_order_uses_recent_first_and_deduplicates_only_bodies():
    refs = tuple(ref(hour, digest) for hour, digest in (
        (27, "prehistory"), (28, "old"), (32, "repeat"), (52, "recent"), (64, "repeat"),
        (100, "boundary"), (101, "future"),
    ))
    planned = trial.select_sources(refs, 100 * trial.HOUR_NS)
    assert [snapshot.path.name for snapshot in planned] == [
        "52-recent.tle", "64-repeat.tle", "100-boundary.tle", "28-old.tle",
    ]
    authoritative = trial.select_sources(refs, 99 * trial.HOUR_NS)
    actual_keys = [snapshot.sha256 for snapshot in authoritative]
    assert actual_keys == ["recent", "repeat", "prehistory", "old"]


def test_manifest_prime_supplies_only_authenticated_body_keys(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = dict(schema_version=2, session_id="test", configuration=dict(
        sample_rate_hz=10_000_000, window_ms=20,
    ), radio={}, sample_rate_hz=10_000_000, receiver_ids=[0, 1], created_utc_ns=100 * trial.HOUR_NS,
        finalized_utc_ns=101 * trial.HOUR_NS, status="complete", stop_reason="test",
        window_count=0, chunks=[])
    content = json.dumps(manifest).encode()
    manifest_path.write_bytes(content)
    digest = sha256(content).hexdigest()
    requests, parser = [], []

    def read(snap):
        requests.append(snap.sha256)
        return snap.sha256

    reader = SimpleNamespace(read=read, list_snapshots=lambda provider: (
        ref(52, "recent"), ref(100, "boundary"), ref(101, "future"),
    ))
    with pytest.raises(ValueError, match="input digest"):
        trial.prime_sources(reader, parser.append, manifest_path, "0" * 64)
    assert requests == parser == []
    result = trial.prime_sources(reader, parser.append, manifest_path, "sha256:" + digest)
    assert result["expected_cutoff_utc_ns"] == 100 * trial.HOUR_NS
    assert requests == parser == ["recent", "boundary"]
