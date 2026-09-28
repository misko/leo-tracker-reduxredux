import json

import pytest

import run_mixture_polished_loso as runner


def real_inputs():
    tracks, receipt = runner.adapter.load_joined()
    sessions = receipt["sessions"]
    return tracks, receipt, sessions


def test_partition_is_disjoint_and_complete():
    tracks, _receipt, sessions = real_inputs()
    train, held = runner.partition(tracks, sessions[0])
    assert len(train) + len(held) == 344
    assert all(row.session_id != sessions[0] for row in train)
    assert all(row.session_id == sessions[0] for row in held)


def test_verify_real_fold_when_available_or_roundtrip_contract():
    tracks, receipt, sessions = real_inputs()
    path = runner.raw_fold_path(sessions[0])
    if not path.exists():
        pytest.skip("main has not yet published immutable original fold")
    raw = json.loads(path.read_text())
    sid, train, held, schema, bindings = runner.verify_raw_fold(
        raw, 1, sessions, tracks, receipt)
    assert sid == sessions[0]
    assert len(train) + len(held) == 344
    assert raw["feature_schema"] == runner.full_runner.json_value(
        runner.asdict(schema))
    assert raw["bindings"] == bindings


def test_verify_fold_rejects_partition_drift_when_available():
    tracks, receipt, sessions = real_inputs()
    path = runner.raw_fold_path(sessions[0])
    if not path.exists():
        pytest.skip("main has not yet published immutable original fold")
    raw = json.loads(path.read_text())
    raw["score_track_count"] += 1
    with pytest.raises(ValueError, match="binding or partition"):
        runner.verify_raw_fold(raw, 1, sessions, tracks, receipt)


def test_build_both_has_identical_feature_contract():
    tracks, _receipt, sessions = real_inputs()
    train, held = runner.partition(tracks, sessions[0])
    schema = runner.adapter.fit_schema(train)
    for arm in runner.ARMS:
        training, scoring, layout, names = runner.build_both(train, held, schema, arm)
        assert len(training) == len(train)
        assert len(scoring) == len(held)
        assert layout.detection_size == len(names["detection"])
        assert layout.ratio_size == len(names["ratio"])


def test_real_polished_full_is_fully_source_bound():
    tracks, receipt, sessions = real_inputs()
    bindings = runner.original.source_bindings(receipt)
    bindings["structural_input_sha256"] = runner.adapter.structural_signature(tracks)
    value, digest = runner.verified_polished_full(sessions, bindings)
    assert value["source_hashes"] == runner.expected_full_source_hashes()
    assert digest.startswith("sha256:")


def test_polished_full_rejects_changed_source_binding(monkeypatch, tmp_path):
    tracks, receipt, sessions = real_inputs()
    bindings = runner.original.source_bindings(receipt)
    bindings["structural_input_sha256"] = runner.adapter.structural_signature(tracks)
    source = runner.HERE / "mixture-calibration-polished-full.json"
    value = json.loads(source.read_text())
    value["source_hashes"]["polish_core"] = "changed"
    (tmp_path / source.name).write_text(json.dumps(value))
    (tmp_path / "mixture-calibration-full.json").write_bytes(
        (runner.HERE / "mixture-calibration-full.json").read_bytes())
    monkeypatch.setattr(runner, "HERE", tmp_path)
    monkeypatch.setattr(runner, "expected_full_source_hashes",
                        lambda: value["source_hashes"] | {"polish_core": "expected"})
    with pytest.raises(ValueError, match="incomplete or rebound"):
        runner.verified_polished_full(sessions, bindings)
