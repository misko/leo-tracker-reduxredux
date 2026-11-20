import json
from hashlib import sha256

import numpy as np
import pytest

from tools.pipeline_eval.qualification import arm_execution_trial
from tools.pipeline_eval.variants import arm_execution as arm


def paired(fitted):
    return dict(
        status="ok",
        boundary="controlled paired fixture",
        metrics=dict(c0_frequency_score=5.0, fitted_c_frequency_score=4.0),
        arms=dict(
            c0=dict(latlon=[0.0, 0.0], rf_rms_hz=7.0), fitted_c=dict(latlon=fitted, rf_rms_hz=6.0)
        ),
    )


def test_selected_fit_cannot_override_other_arms_publication_disagreement():
    case = paired([0.0, 12.5 / 111.32])
    tile = dict(center=[0.0, 0.0], width_km=25.0)
    first = arm.selected(case, "c0", tile, "paired-interior")
    other = arm.selected(case, "fitted_c", tile, "paired-interior")
    assert first["status"] == other["status"] == "withheld"
    assert first["paired_decision_sha256"] == other["paired_decision_sha256"]
    assert first["frequency_score"] == 5.0 and other["frequency_score"] == 4.0
    assert first["fit"] == dict(latlon=None, rf_rms_hz=7.0, forced_latlon=[0.0, 0.0])
    assert "arms" not in first
    assert arm.selected(case, "c0", tile, "paired")["fit"]["latlon"] == [0.0, 0.0]


def test_selected_mode_rejects_missing_or_implicit_pair():
    tile = dict(center=[0.0, 0.0], width_km=25.0)
    case = paired([0.0, 0.1])
    with pytest.raises(ValueError, match="explicit paired publication"):
        arm.selected(case, "c0", tile, None)
    with pytest.raises(ValueError, match="both calibration arms"):
        arm.selected(dict(case, arms={"c0": case["arms"]["c0"]}), "c0", tile, "paired")


def test_phase_views_share_only_same_scan_and_ordered_labels_with_private_results():
    calls = []

    def widths(scan, labels):
        calls.append((scan, tuple(labels)))
        return np.array(labels, float), [dict(label=n) for n in labels]

    cache = arm.PhaseViews(widths)
    one, two = object(), object()
    a, b = cache(one, [1, 2])
    a[0] = b[0]["label"] = 99
    rows, info = cache(one, [1, 2])
    assert rows.tolist() == [1, 2] and info == [{"label": 1}, {"label": 2}]
    cache(one, [2, 1])
    cache(two, [1, 2])
    assert calls == [(one, (1, 2)), (one, (2, 1)), (two, (1, 2))]
    assert cache.calls == 4 and cache.reused == 1


def test_strip_keeps_paired_core_and_only_removes_terminal_reporting():
    code = (
        "def fit():\n    stable = paired_recovery()\n"
        + arm.BEGIN
        + (
            "    for arm in ARMS:\n"
            "        extended = extend_associations()\n"
            '        pair[arm]["association"] = extended\n'
            '        pair[arm]["association_tracks"] = extended\n'
        )
        + arm.END
        + "        pair=pair,\n    )\n"
    )
    reduced = arm.strip_reporting(code)
    assert (
        reduced
        == "def fit():\n    stable = paired_recovery()\n" + arm.END + "        pair=pair,\n    )\n"
    )
    with pytest.raises(ValueError, match="reporting seam"):
        arm.strip_reporting(code.replace("extend_associations()", "changed_scientific_policy()"))


def test_selected_cli_uses_verified_request_and_explicit_policy(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "tle"
    archive.mkdir()
    (archive / "causal.tle").write_bytes(b"causal fixture")
    compact = dict(archive=str(archive))
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            dict(
                compact=compact,
                causal_snapshots={
                    "causal.tle": sha256(b"causal fixture").hexdigest(),
                },
            )
        )
    )
    monkeypatch.setattr(arm, "verify_install", lambda root: assert_same(root, tmp_path))

    def solve(root, values, calibration, publication, timeout_s):
        assert root == tmp_path and values == compact and timeout_s == 30
        assert calibration == "fitted_c" and publication == "paired-interior"
        output = arm.selected(
            paired([0.0, 0.0]), calibration, dict(center=[0, 0], width_km=25), publication
        )
        return {"selected": output}

    monkeypatch.setattr(arm, "solve_selected", solve)
    arm.main(
        [
            "select",
            "--receiver",
            str(tmp_path),
            "--request",
            str(request),
            "--request-sha256",
            sha256(request.read_bytes()).hexdigest(),
            "--calibration",
            "fitted_c",
            "--publication",
            "paired-interior",
            "--timeout",
            "30",
        ]
    )
    assert json.loads(capsys.readouterr().out)["calibration"] == "fitted_c"


def assert_same(actual, expected):
    assert actual == expected


def test_trial_keeps_effective_tile_and_screen_independent():
    spec = dict(
        native="native",
        native_sha256="verified",
        archive="archive",
        track_config="fixed",
        config_sha256="config",
        session="input",
        tile=dict(center=[0, 4], width_km=25.0),
        screen_center=[4, 0],
    )
    assert arm_execution_trial.compact(spec)["tile"] == [0, 4]
    assert arm_execution_trial.compact(spec)["screen_center"] == [4, 0]
    del spec["tile"]["width_km"]
    assert arm_execution_trial.compact(spec)["width_km"] == 25.0
