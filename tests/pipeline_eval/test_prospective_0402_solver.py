from hashlib import sha256

import pytest

from reports.ALGO08.v3 import prospective_0402_solver as trial


def test_archive_charge_is_deduplicated_and_prefers_local_matches():
    matched = {"source": "/dev/shm/signed-copy", "sha256": "known", "bytes": 2}
    missing = {"source": None, "sha256": "missing", "bytes": 3}
    files = {"original": matched, "missing-original": missing, "second-original": dict(missing)}
    assert trial.bulk_sources(files) == {("missing", 3): "missing-original"}


def test_original_payload_limit_bounds_both_count_and_total_bytes():
    one = {"original": {"source": None, "sha256": "large", "bytes": 34_002_576}}
    many = {f"original-{i}": {"source": None, "sha256": str(i), "bytes": 1} for i in range(20)}
    for invalid in (one, many):
        with pytest.raises(ValueError, match="19-payload / 34,002,575-byte"):
            trial.bulk_sources(invalid)


def test_payload_validation_rejects_different_size_or_unverified_content(tmp_path):
    path = tmp_path / "snapshot.tle"
    path.write_bytes(b"leaf")
    digest = sha256(b"leaf").hexdigest()
    assert trial.bounded_payload(path, digest, 4) == b"leaf"
    with pytest.raises(ValueError, match="size before reading"):
        trial.bounded_payload(path, digest, 3)
    path.write_bytes(b"twig")
    with pytest.raises(ValueError, match="sealed digest"):
        trial.bounded_payload(path, digest, 4)


def test_dropped_lanes_bind_receiver_channel_and_role_to_exact_owner_ids():
    def probe(counter, visit):
        return dict(receiver_id=1, channel=6, actual_rf_hz=11_959_687_500,
                    valid_start_counter=counter, visit_index=visit)

    def identity(counter):
        return "sha256:" + sha256(f"saved:1:{counter}".encode()).hexdigest()

    native = {"source": {"session_id": "saved", "probes": [probe(100, 1), probe(200, 2), probe(300, 4)]}}
    rows = [[identity(100), 58377, "conditional"], [identity(200), 58377, "conditional"],
            [identity(300), 58377, "conditional"]]
    lost = trial.dropped_owner_lanes(native, rows, [identity(100), identity(300)])
    assert lost == [dict(norad=58377, role="conditional", receiver=2, channel=6, rf_hz=11_959_687_500,
                         count=2, first_visit=1, last_visit=4)]
