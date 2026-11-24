from hashlib import sha256

import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3.nomination_handoff_0419_local import collector_roster, copy_archive, pooled


def add_snapshot(folder, time, data):
    pin = sha256(data).hexdigest()
    path = folder / f"{time}-{pin}.tle"
    path.write_bytes(data)
    return path, pin


def test_exact_local_roster_and_authenticated_copy(tmp_path):
    bodies = tmp_path / "collector"
    bodies.mkdir()
    earlier, pin = add_snapshot(bodies, 11, b"early body")
    add_snapshot(bodies, 12, b"at cutoff")
    want = canonical_digest({earlier.name: pin})
    device = bodies.stat().st_dev
    rows, extent = collector_roster(bodies, device, 10, 12, want)
    assert extent == len(b"early body")
    target = tmp_path / "ram"
    copy_archive(bodies, target, rows, device)
    assert list(target.iterdir()) == [target / earlier.name]
    assert (target / earlier.name).read_bytes() == b"early body"
    with pytest.raises(ValueError, match="exceeds the staging budget"):
        collector_roster(bodies, device, 10, 12, want, limit=1)
    with pytest.raises(ValueError, match="roster differs"):
        collector_roster(bodies, device, 10, 12, canonical_digest({}))


def test_selected_symlink_and_wrong_device_are_rejected(tmp_path):
    bodies = tmp_path / "collector"
    bodies.mkdir()
    source, pin = add_snapshot(tmp_path, 11, b"not a regular archive member")
    (bodies / source.name).symlink_to(source)
    want = canonical_digest({source.name: pin})
    device = bodies.stat().st_dev
    with pytest.raises(ValueError, match="Unexpected collector file identity"):
        collector_roster(bodies, device, 10, 12, want)
    with pytest.raises(ValueError, match="changed devices"):
        collector_roster(bodies, device + 1, 10, 12, want)


def test_same_inode_wrong_body_cannot_be_staged(tmp_path):
    bodies = tmp_path / "collector"
    bodies.mkdir()
    earlier, pin = add_snapshot(bodies, 11, b"canonical")
    device = bodies.stat().st_dev
    rows, _ = collector_roster(bodies, device, 10, 12, canonical_digest({earlier.name: pin}))
    earlier.write_bytes(b"corrupted")
    target = tmp_path / "ram"
    with pytest.raises(ValueError, match="signed hash"):
        copy_archive(bodies, target, rows, device)
    assert list(target.iterdir()) == []


def test_cumulative_and_blind_admission_denominators_stay_separate():
    result = pooled(10, 20, 30, 10, 5)
    assert result["summed_speedup"] == pytest.approx(40 / 30)
    assert result["median_paired_speedup"] == pytest.approx(1 / ((20 / 10 + 10 / 30) / 2))
    assert result["blind_speedup_shared_admission"] == pytest.approx(35 / 15)
    assert result["blind_speedup_candidate_only_admission"] == pytest.approx(30 / 15)
