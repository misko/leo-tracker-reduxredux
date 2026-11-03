import copy

import pytest

from tools.rx_background_crossvalidation import calibration_rows, crossvalidate


def test_extraction_ignores_all_noncalibration_reception_outcomes():
    document = {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "calibration",
                "alias_period_hz": 100,
                "lane": {"session_id": sid},
                "windows": [
                    {
                        "role": "reception",
                        "source_window_id": sid,
                        "sample_rate_hz": 5,
                        "observed": {"rx0": [{"canonical_rx0_hz": -25}], "rx1": []},
                    },
                    {"role": "held_frequency", "observed": "invalid unread outcome"},
                ],
            }
            for sid in ("a", "b")
        ],
    }
    before = calibration_rows(document, expected_records=2)
    changed = copy.deepcopy(document)
    changed["lanes"].append({"recording_split": "evaluation", "windows": "unread"})
    changed["lanes"][0]["windows"][1]["observed"] = None
    assert calibration_rows(changed, expected_records=2) == before
    assert before[0]["frequencies"] == [[0.75], []]
    changed["lanes"][0]["windows"].append(changed["lanes"][0]["windows"][0])
    with pytest.raises(ValueError, match="duplicate"):
        calibration_rows(changed, expected_records=2)


def test_extraction_requires_expected_records_and_global_window_identity():
    def lane(session_id, window_id):
        return {
            "recording_split": "calibration",
            "alias_period_hz": 100,
            "lane": {"session_id": session_id},
            "windows": [
                {
                    "role": "reception",
                    "source_window_id": window_id,
                    "sample_rate_hz": 5,
                    "observed": {"rx0": [], "rx1": []},
                }
            ],
        }

    document = {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [lane("a", "shared"), lane("b", "other")],
    }
    with pytest.raises(ValueError, match="expected 6"):
        calibration_rows(document)
    duplicate = copy.deepcopy(document)
    duplicate["lanes"][1]["windows"][0]["source_window_id"] = "shared"
    with pytest.raises(ValueError, match="duplicate"):
        calibration_rows(duplicate, expected_records=2)


@pytest.mark.parametrize(("session_id", "window_id"), [("", "window"), ("session", "")])
def test_extraction_rejects_empty_provenance_identity(session_id, window_id):
    document = {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "calibration",
                "alias_period_hz": 100,
                "lane": {"session_id": session_id},
                "windows": [
                    {
                        "role": "reception",
                        "source_window_id": window_id,
                        "sample_rate_hz": 5,
                        "observed": {"rx0": [], "rx1": []},
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="nonempty string"):
        calibration_rows(document, expected_records=1)


def test_fold_models_exclude_held_record_and_scores_decompose(monkeypatch):
    from tools import rx_background_crossvalidation as module

    real_fit = module.fit
    calls = []

    def recording_fit(rows, mode):
        calls.append({row["session_id"] for row in rows})
        return real_fit(rows, mode)

    monkeypatch.setattr(module, "fit", recording_fit)
    rows = [
        {
            "session_id": sid,
            "window_id": sid,
            "period_hz": 100.0,
            "rate_hz": 5,
            "counts": [1, 0],
            "frequencies": [[phase], []],
        }
        for sid, phase in (("a", 0.1), ("b", 0.9))
    ]
    result = crossvalidate(rows)
    assert calls[:5] == [{"b"}] * 5
    assert calls[5:10] == [{"a"}] * 5
    assert calls[-1] == {"a", "b"}
    for fold in result["folds"]:
        for score in fold["scores"].values():
            assert score["mean_log_density"] == pytest.approx(
                score["count_set_mean"] + score["frequency_hz_mean"]
            )
    changed = copy.deepcopy(rows)
    changed[0]["frequencies"] = [[0.8], []]
    result_changed = crossvalidate(changed)
    # Count-only models and their score on the unchanged recording cannot depend on phases.
    for mode in ("poisson", "joint", "rate_joint"):
        assert result_changed["folds"][1]["scores"][mode] == result["folds"][1]["scores"][mode]
