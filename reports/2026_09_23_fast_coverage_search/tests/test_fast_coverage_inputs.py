import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).parents[2] / "tools/research/fast_coverage_inputs.py"
SPEC = importlib.util.spec_from_file_location("fast_coverage_inputs_test", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    folder = tmp_path / "evidence"
    folder.mkdir()
    text = "archived catalogue fixture"
    (folder / "archived.tle").write_text(text)
    digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    authority = {
        "session_id": "session", "reference_utc_ns": 1_000_000_000_000,
        "known_position_used": False, "fixed_candidates": {},
        "tle_file": "archived.tle", "tle_digest": digest,
        "tle_collected_ns": 400_000_000_000, "partition": "chronological",
    }
    path = folder / "session.json"
    path.write_text(json.dumps({"inventory": authority}))
    snapshot = SimpleNamespace(digest=digest, collected_utc_ns=authority["tle_collected_ns"])
    monkeypatch.setattr(MODULE, "TleArchiveReader", lambda _: SimpleNamespace(
        select_latest_before=lambda cutoff: snapshot
    ))
    monkeypatch.setattr(MODULE, "parse_element_sets", lambda _: SimpleNamespace(
        names=("STARLINK-1", "STARLINK-2 DEB", "OTHER")
    ))
    return tmp_path, path, authority, snapshot


def test_causal_catalogue_is_unrestricted_and_old_split_is_only_metadata(evidence):
    root, _, authority, _ = evidence
    _, indices, provenance = MODULE.catalogue_authority(
        "session", root, root, authority["reference_utc_ns"]
    )
    assert indices.tolist() == [0]
    assert provenance["archived_evidence_partition_not_used"] == "chronological"
    assert provenance["catalogue_cutoff_utc_ns"] == 495_000_000_000


@pytest.mark.parametrize("change", ["truth", "identity", "snapshot", "digest"])
def test_catalogue_rejects_leaked_or_mismatched_authority(evidence, change):
    root, path, authority, snapshot = evidence
    if change == "truth":
        authority["known_position_used"] = True
    elif change == "identity":
        authority["fixed_candidates"] = {"track": 123}
    elif change == "snapshot":
        snapshot.collected_utc_ns += 1
    else:
        authority["tle_digest"] = "sha256:wrong"
    path.write_text(json.dumps({"inventory": authority}))
    with pytest.raises(ValueError):
        MODULE.catalogue_authority("session", root, root, authority["reference_utc_ns"])


def test_duplicate_observations_cannot_silently_receive_double_weight(evidence, monkeypatch):
    root, _, authority, _ = evidence
    row = SimpleNamespace(observation_id="same", measured_cfo_hz=1.0)
    selected = [("track", object(), [row, row], [0., 1.], 1.)]
    monkeypatch.setattr(MODULE, "reference_kernel", lambda: SimpleNamespace(
        _tracks=lambda *_: (authority["reference_utc_ns"], object(), selected, 1, 1)
    ))
    with pytest.raises(ValueError, match="union-aware"):
        MODULE.load("session", root, root, root, track_count=1)
