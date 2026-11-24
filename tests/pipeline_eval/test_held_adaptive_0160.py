from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.operations.tle_archive import TleSnapshotRef
from reports.ALGO08.v3 import held_adaptive_0160 as trial


def test_causal_read_port_delegates_and_counts_only_selected_snapshot(monkeypatch):
    archive = Path("/dev/shm/causal")
    path = archive / "archive/space-track/example.tle"
    eligible = TleSnapshotRef(1, "space-track", "a" * 64, 3, path)
    at_cutoff = TleSnapshotRef(2, "space-track", "b" * 64, 3, path)
    unbound = TleSnapshotRef(1, "space-track", "c" * 64, 3, path)
    checked, payloads, counts = [], [], Counter()
    monkeypatch.setattr(trial, "resident_path", checked.append)

    def verified_reader(reader, ref):
        payloads.append((reader, ref))
        return b"tle"

    reader = SimpleNamespace(root=archive)
    port = trial.catalogue_scope(archive, (eligible, at_cutoff), 2, verified_reader, counts)
    for ref in (at_cutoff, unbound):
        with pytest.raises(ValueError, match="signed local causal catalogue"):
            port(reader, ref)
    with pytest.raises(ValueError, match="signed local causal catalogue"):
        port(SimpleNamespace(root=Path("/different")), eligible)
    assert port(reader, eligible) == b"tle"
    assert checked == [path]
    assert payloads == [(reader, eligible)]
    assert counts == {path.name: 3}


def test_resident_scope_denies_outside_path():
    with pytest.raises(ValueError, match="exact tmpfs path"):
        trial.resident_path(Path("/tmp"))


def test_bad_catalogue_payload_never_counts_as_verified(monkeypatch):
    archive = Path("/dev/shm/causal")
    ref = TleSnapshotRef(1, "space-track", "a" * 64, 3, archive/"catalogue.tle")
    counts = Counter()
    monkeypatch.setattr(trial, "resident_path", lambda path: path)

    def reject(reader, snapshot):
        raise ValueError("Bad payload digest")

    with pytest.raises(ValueError, match="Bad payload digest"):
        trial.catalogue_scope(archive, (ref,), 2, reject, counts)(SimpleNamespace(root=archive), ref)
    assert not counts
