from copy import deepcopy
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest


PATH = Path(__file__).with_name("model_eval.py")
SPEC = importlib.util.spec_from_file_location("roof_model_eval", PATH)
MODEL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODEL
SPEC.loader.exec_module(MODEL)


def rows():
    result = []
    for split, session, east_values in (("cal", "c", (-1.0, 1.0)), ("holdout", "h", (-0.5, 0.5))):
        for track, east in enumerate(east_values):
            for receiver in ("rx0", "rx1"):
                signed = east if receiver == "rx0" else -east
                result.append({"session_id": session, "split": split, "track_id": str(track),
                    "receiver_id": receiver, "channel": 100, "edge": "low",
                    "anchor_margin": 2.0 + track, "matched": signed > 0,
                    "log_margin_ratio_rx1_rx0": east, "east": east, "up": 0.8})
    return result


def test_holdout_changes_do_not_change_fit_or_scaling():
    original = rows()
    changed = deepcopy(original)
    for row in changed:
        if row["split"] == "holdout":
            row.update(anchor_margin=1e9, east=999.0, matched=not row["matched"])
    assert MODEL.fit_detection_models(original) == MODEL.fit_detection_models(changed)


def test_direction_permutations_touch_only_requested_split_and_keep_pairs():
    original = rows()
    cal = MODEL.permute_calibration_directions(original, seed=4)
    assert [r for r in cal if r["split"] == "holdout"] == [r for r in original if r["split"] == "holdout"]
    holdout = MODEL.shuffle_holdout_directions_within_scan(original, seed=4)
    assert [r for r in holdout if r["split"] == "cal"] == [r for r in original if r["split"] == "cal"]
    for transformed in (cal, holdout):
        for split in ("cal", "holdout"):
            for track in ("0", "1"):
                pair = [r["east"] for r in transformed if r["split"] == split and r["track_id"] == track]
                assert len(set(pair)) == 1


def test_each_track_has_unit_total_weight():
    data = rows()
    data.append(dict(data[0]))
    weights = MODEL.track_weights(data)
    totals = {}
    for row, weight in zip(data, weights, strict=True):
        key = row["session_id"], row["track_id"]
        totals[key] = totals.get(key, 0) + weight
    assert all(np.isclose(value, 1.0) for value in totals.values())


def test_detection_direction_has_receiver_dependent_sign_but_ratio_does_not():
    data = rows()
    detection = MODEL.fit_detection_models(data)["M1"]
    continuous = MODEL.fit_continuous_models(data)["M1"]
    rx0, rx1 = data[0], data[1]
    dx0, *_ = MODEL._design([rx0], "detection", True, template=detection)
    dx1, *_ = MODEL._design([rx1], "detection", True, template=detection)
    cx0, *_ = MODEL._design([rx0], "continuous", True, template=continuous)
    cx1, *_ = MODEL._design([rx1], "continuous", True, template=continuous)
    assert dx0[0, -1] == -dx1[0, -1]
    assert cx0[0, -1] == cx1[0, -1]


def test_reverse_mapping_only_flips_east():
    original = rows()
    reversed_rows = MODEL.reverse_mapping(original)
    assert [r["east"] for r in reversed_rows] == [-r["east"] for r in original]
    assert [r["up"] for r in reversed_rows] == [r["up"] for r in original]


def test_shuffle_preserves_direction_trajectory_instead_of_collapsing_first_point():
    data = rows()
    for i,row in enumerate(data):
        row['observation_utc_ns']=i
        row['east'] += .1*(i%2)
    shuffled=MODEL.shuffle_holdout_directions_within_scan(data,seed=8)
    for tid in ('0','1'):
        east=[r['east'] for r in shuffled if r['split']=='holdout' and r['track_id']==tid]
        assert abs(east[1]-east[0])==pytest.approx(.1)


def test_sample_rate_is_a_shared_categorical_confound_and_unseen_is_reported():
    data = rows()
    for index, row in enumerate(data):
        row["sample_rate_hz"] = 2_500_000 if index % 4 < 2 else 5_000_000
    fits = MODEL.fit_detection_models(data)
    assert "sample_rate_hz=5000000" in fits["M0"].feature_names
    assert "sample_rate_hz=5000000" in fits["M1"].feature_names
    holdout = [dict(row, sample_rate_hz=10_000_000) for row in data if row["split"] == "holdout"]
    scored = MODEL.score_models(fits, holdout)
    assert scored["unseen_sample_rate_hz"] == ["10000000"]


def test_channel_edge_is_joint_nuisance_not_additive_main_effects():
    data = rows()
    lanes = [(100, "low"), (100, "high"), (200, "low"), (200, "high")]
    for index, row in enumerate(data):
        row["channel"], row["edge"] = lanes[index % len(lanes)]
    fit = MODEL.fit_detection_models(data)["M0"]
    lane_features = [name for name in fit.feature_names if name.startswith("channel_edge=")]
    assert len(lane_features) == 3
    assert not any(name.startswith("channel=") or name.startswith("edge=")
                   for name in fit.feature_names)


def test_evaluate_is_deterministic_and_includes_predeclared_controls():
    first = MODEL.evaluate(rows(), bootstrap_replicates=20, seed=8)
    second = MODEL.evaluate(rows(), bootstrap_replicates=20, seed=8)
    assert first == second
    assert set(first["detection"]["controls"]) == {
        "calibration_direction_permutation",
        "heldout_within_scan_track_direction_shuffle",
        "mapping_reversal",
    }
    assert first["detection"]["scan_bootstrap"]["estimand"] == \
        "equal_track_loss; scan-cluster bootstrap"


def test_evaluate_reports_training_rate_matched_sensitivity_without_refit():
    data = rows()
    for row in data:
        row["sample_rate_hz"] = 2_500_000 if row["split"] == "cal" else 5_000_000
    result = MODEL.evaluate(data, bootstrap_replicates=5)
    sensitivity = result["detection"]["matched_training_sample_rate_sensitivity"]
    assert sensitivity["score"] is None
    assert sensitivity["included_scans"] == []
    assert sensitivity["excluded_scans"] == ["h"]


def test_scan_bootstrap_matches_explicit_whole_scan_resampling():
    data = rows()
    fits = MODEL.fit_detection_models(data)
    seed, replicates = 31, 12
    actual = MODEL.scan_bootstrap(fits, data, replicates=replicates, seed=seed)
    scans = sorted({r["session_id"] for r in data})
    rng = np.random.default_rng(seed)
    explicit = []
    for _ in range(replicates):
        sampled = []
        for occurrence, scan in enumerate(rng.choice(scans, len(scans), replace=True)):
            for row in data:
                if row["session_id"] == scan:
                    sampled.append(dict(row, session_id=f"{scan}#{occurrence}"))
        explicit.append(MODEL.score_models(fits, sampled)["equal_track"]["M1_minus_M0"])
    assert actual["M1_minus_M0_95_ci"] == pytest.approx(
        np.quantile(explicit, [0.025, 0.975])
    )
    assert actual["M1_better_fraction"] == pytest.approx(np.mean(np.asarray(explicit) < 0))
