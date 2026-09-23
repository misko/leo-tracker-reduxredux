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
        "session_id": "session",
        "reference_utc_ns": 1_000_000_000_000,
        "known_position_used": False,
        "fixed_candidates": {},
        "tle_file": "archived.tle",
        "tle_digest": digest,
        "tle_collected_ns": 400_000_000_000,
        "partition": "chronological",
    }
    path = folder / "session.json"
    path.write_text(json.dumps({"inventory": authority}))
    snapshot = SimpleNamespace(digest=digest, collected_utc_ns=authority["tle_collected_ns"])
    monkeypatch.setattr(
        MODULE,
        "TleArchiveReader",
        lambda _: SimpleNamespace(select_latest_before=lambda cutoff: snapshot),
    )
    monkeypatch.setattr(
        MODULE,
        "parse_element_sets",
        lambda _: SimpleNamespace(names=("STARLINK-1", "STARLINK-2 DEB", "OTHER")),
    )
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
    selected = [("track", object(), [row, row], [0.0, 1.0], 1.0)]
    monkeypatch.setattr(
        MODULE,
        "reference_kernel",
        lambda: SimpleNamespace(
            _tracks=lambda *_: (authority["reference_utc_ns"], object(), selected, 1, 1)
        ),
    )
    with pytest.raises(ValueError, match="union-aware"):
        MODULE.load("session", root, root, root, track_count=1)


def test_all_track_selection_reconstructs_three_second_tracks_without_top_ten_limit():
    graphs = {}
    for index in range(13):
        span = 3.0 if index < 11 else 2.9
        count = 6 if index != 12 else 5
        graphs[str(index)] = SimpleNamespace(
            observations=[
                SimpleNamespace(support_center_utc_ns=int(1e12 + i * span * 1e9 / (count - 1)))
                for i in range(count)
            ]
        )
    source = SimpleNamespace(timing=SimpleNamespace(first_sample_estimate_utc_ns=int(1e12)))
    closed = []
    kernel = SimpleNamespace(
        ScannerTrackingInputStore=lambda _: SimpleNamespace(
            load=lambda _: source, close=lambda: closed.append(True)
        ),
        timing_is_qualified_for_tle=lambda _: True,
        PersistentHopTrajectoryConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        project_scanner_candidates=lambda _: object(),
        reconstruct_persistent_hop_trajectories=lambda _, config: SimpleNamespace(
            hypotheses=[SimpleNamespace(tracklet_ids=tuple(graphs))], tracklets=tuple(graphs)
        ),
        persistent_hop_tracklet_graph=lambda _, track: graphs[track],
        _select_review_tracks=lambda rows, count: rows[:count],
    )
    _, config, selected, eligible, reconstructed = MODULE.load_track_selection(
        kernel, "session", Path("."), None, 3.0, 6
    )
    assert config.minimum_span_s == 3.0
    assert config.minimum_support == 6
    assert len(selected) == eligible == 11
    assert reconstructed == 13
    assert closed == [True]
