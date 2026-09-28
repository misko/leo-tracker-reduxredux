import copy

import numpy as np

import tools.rx_orbit_increment_eval as module


def test_evaluation_document_removes_calibration_lanes():
    document = {
        "lanes": [
            {"recording_split": "calibration", "lane": {"session_id": "cal"}},
            {"recording_split": "evaluation", "lane": {"session_id": "eval"}},
        ]
    }
    restricted = module._evaluation_document(document)
    assert [lane["lane"]["session_id"] for lane in restricted["lanes"]] == ["eval"]


def test_geometry_permute_only_rolls_candidate_geometry():
    x = np.arange(2 * 3 * 2 * 8, dtype=float).reshape(2, 3, 2, 8)
    lane = {
        "x": x.copy(),
        "signal": np.ones((2, 3, 2)),
        "log_prior": np.arange(6).reshape(2, 3),
        "reference": np.zeros(2),
    }
    changed = module._permute_geometry([lane])[0]
    np.testing.assert_array_equal(changed["x"][..., :3], x[..., :3])
    np.testing.assert_array_equal(changed["x"][..., 3:8], np.roll(x[..., 3:8], 1, axis=1))
    np.testing.assert_array_equal(changed["signal"], lane["signal"])
    np.testing.assert_array_equal(changed["log_prior"], lane["log_prior"])
    np.testing.assert_array_equal(lane["x"], x)


def test_fit_uses_uniform_reception_family_and_preserves_receipts(monkeypatch):
    rows = [{"session_id": f"s{i}", "window_id": f"w{i}-{j}"} for i in range(6) for j in range(2)]
    prepared = {
        "rows": rows,
        "background": {"schema": "rx-empirical-background/v1", "mode": "joint"},
        "center": np.zeros(8),
        "scale": np.ones(8),
        "uniform": [{"source": {"lane": {"session_id": f"s{i // 2}"}}} for i in range(12)],
    }
    calls = []
    monkeypatch.setattr(module, "prepare_families", lambda document: prepared)
    monkeypatch.setattr(
        module,
        "attach_orbit_increment",
        lambda lanes: (lanes, [{"receipt": True}]),
    )

    def fake_fit(lanes, seed):
        calls.append((lanes, seed))
        return {"fits": {arm: {} for arm in module.ARMS}}

    monkeypatch.setattr(module, "fit_arms", fake_fit)
    result = module.fit({})
    assert calls[0][0] is prepared["uniform"]
    assert calls[0][1] == {"D": {"parameters": [-2.0, 0.0, 0.0]}}
    assert result["training_source_window_count"] == 12
    assert result["orbit_increment_diagnostics"] == [{"receipt": True}]


def test_orbit_control_names_are_explicit_and_distinct():
    assert module.ORBIT_SPECS["T_geometry_reverse"] == ("reverse", None, 0.0, "T")
    assert module.ORBIT_SPECS["T_reverse_motion"] == (None, "reverse", 0.0, "T")
    assert module.ORBIT_SPECS["T_zero_motion"] == (None, "zero", 0.0, "T")
    assert module.ORBIT_SPECS["T_shift"] == (None, None, 0.25, "T")
    assert "T_geometry_permute" in module.ORBIT_SPECS


def test_evaluation_filter_is_independent_of_outcomes():
    document = {
        "lanes": [
            {"recording_split": "evaluation", "lane": {"session_id": "e"}, "windows": []},
            {"recording_split": "calibration", "lane": {"session_id": "c"}, "windows": []},
        ]
    }
    changed = copy.deepcopy(document)
    changed["lanes"][0]["windows"] = [{"observed": {"rx0": [1]}}]
    assert [x["lane"] for x in module._evaluation_document(document)["lanes"]] == [
        x["lane"] for x in module._evaluation_document(changed)["lanes"]
    ]


def test_score_keeps_reference_comparison_scoped_per_record(monkeypatch):
    background = {"mode": "joint"}
    center, scale = np.zeros(8), np.ones(8)
    monkeypatch.setattr(
        module,
        "_validate_orbit_model",
        lambda *args: (["cal"], background, center, scale),
    )
    monkeypatch.setattr(
        module,
        "_validate_model",
        lambda *args: (["cal"], background, center, scale),
    )

    def fake_prepared(document, *args, **kwargs):
        sid = document["lanes"][0]["lane"]["session_id"]
        value = float(sid[-1])
        return [
            {
                "reference": np.array([value]),
                "signal": np.ones((1, 1, 2)),
                "source": {"lane": {"session_id": sid}},
            }
        ]

    monkeypatch.setattr(module, "_prepared", fake_prepared)
    monkeypatch.setattr(module, "_permute_geometry", lambda lanes: lanes)
    monkeypatch.setattr(module, "attach_orbit_increment", lambda lanes, **kwargs: (lanes, []))
    monkeypatch.setattr(module, "attach_causal_frequency", lambda lanes: (lanes, []))

    def fake_score(lanes, selected):
        value = float(lanes[0]["reference"][0])
        role = {
            "relative_log_score_per_window": value,
            "reference_log_score": value,
        }
        return {"roles": {"reception": role, "held_frequency": role}}

    monkeypatch.setattr(module, "score_lanes", fake_score)
    fits = {arm: {"selected": {}} for arm in module.ARMS}
    orbit = {"fits": fits}
    static = {"families": {"causal": {"fits": copy.deepcopy(fits)}}}
    document = {
        "lanes": [
            {"recording_split": "evaluation", "lane": {"session_id": f"eval-{i}"}}
            for i in range(1, 5)
            for _receiver in range(2)
        ]
    }
    result = module.score({}, orbit, document, static)
    assert result["evaluation_sessions"] == ["eval-1", "eval-2", "eval-3", "eval-4"]
    assert result["coverage"]["recordings"] == 4
