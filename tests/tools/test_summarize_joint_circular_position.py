import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[2] / "reports/summarize_joint_circular_position.py"
SPEC = importlib.util.spec_from_file_location("summarize_joint_circular_position", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def result(track_count=39, observation_count=1415):
    tracks = [
        {
            "session_id": "scan",
            "episode_id": f"episode-{index}",
            "receiver_id": 0,
            "pilot_edge": "lower",
            "channel": 1 + index % 2,
            "null_weight": 0.2,
            "candidates": [{"norad": 100 + index, "circular_weight": 0.7}],
        }
        for index in range(track_count)
    ]
    arms = []
    for number, name in enumerate(MODULE.ARMS):
        rows = json.loads(json.dumps(tracks))
        if number == 1:
            rows[0]["null_weight"] = 0.8
        arms.append(
            {
                "arm": name,
                "fits": [{"converged": number != 2, "bound_hit": number == 3}],
                "latitude_deg": 37.0 + number / 100,
                "longitude_deg": -122.0,
                "training_score": 10.0 + number,
                "heldout_score": 20.0 - number,
                "pruning_log_error_bound": 1e-9,
                "groups": [],
                "tracks": rows,
            }
        )
    value = {
        "schema": "blind-joint-circular-position-refinement/v1",
        "complete": False,
        "qualification": "insufficient",
        "qualification_failures": ["synthetic failure"],
        "position_truth_used": False,
        "partition": "five-chronological-blocks-train-0-2-4-heldout-1-3-v1",
        "track_count": track_count,
        "observation_count": observation_count,
        "configuration": {"radius_km": 100},
        "uniform_baseline_parity": {"passed": True},
        "elapsed_s": 1.0,
        "peak_rss_kib": 100,
        "arms": arms,
    }
    value["content_digest"] = MODULE.content_digest(value)
    return value


def write_result(path: Path, value: dict) -> None:
    path.mkdir(parents=True)
    payload = json.dumps(value, sort_keys=True) + "\n"
    result_path = path / "result.json"
    result_path.write_text(payload)
    (path / "result.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")


def six_inputs(tmp_path):
    values = []
    for center in MODULE.CENTERS:
        for cohort in MODULE.COHORTS:
            path = tmp_path / f"{center}-{cohort}"
            value = result() if cohort == "single" else result(165, 5432)
            write_result(path, value)
            values.append(((center, cohort), path / "result.json"))
    return values


def test_bind_before_reference_and_preserve_failed_arms(tmp_path):
    output = tmp_path / "out"
    values = six_inputs(tmp_path)
    loaded = MODULE.bind_inputs(values, output)
    binding = json.loads((output / "inference-bindings.json").read_text())
    assert binding["truth_accessed"] is False
    assert len(binding["inputs"]) == 6
    reference_path = tmp_path / "reference.json"
    reference_path.write_text('{"latitude_deg":37.5,"longitude_deg":-122.2}')
    summary = MODULE.summarize(
        loaded, json.loads(reference_path.read_text()), reference_path
    )
    assert len(summary["runs"]) == 6
    assert all(len(run["arms"]) == 7 for run in summary["runs"])
    row = summary["runs"][0]
    assert row["complete"] is False
    assert row["arms"][2]["status"]["all_fits_converged"] is False
    assert row["arms"][3]["status"]["any_bound_hit"] is True
    assert row["arms"][1]["association"]["leader_changes_from_uniform"] == 1
    assert row["arms"][1]["heldout_delta_from_uniform"] == pytest.approx(-1)
    assert row["group_channel_composition"][0]["channel_track_counts"] == {
        "1": 20,
        "2": 19,
    }


def test_rejects_digest_damage_and_incomplete_inventory(tmp_path):
    values = six_inputs(tmp_path)
    values[0][1].write_text(values[0][1].read_text() + " ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        MODULE.bind_inputs(values, tmp_path / "bad")
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.bind_inputs(six_inputs(tmp_path / "other")[:-1], tmp_path / "missing")


def test_rejects_duplicate_labels_mislabeled_cohort_and_duplicate_tracks(tmp_path):
    values = six_inputs(tmp_path)
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.bind_inputs([*values, values[0]], tmp_path / "duplicate-label")
    wrong = result()
    write_result(tmp_path / "replacement", wrong)
    values[1] = (values[1][0], tmp_path / "replacement/result.json")
    with pytest.raises(ValueError, match="cohort accounting mismatch"):
        MODULE.bind_inputs(values, tmp_path / "wrong-cohort")
    arm = result()["arms"][1]
    arm["tracks"][1] = dict(arm["tracks"][0])
    with pytest.raises(ValueError, match="track inventory differs"):
        MODULE.association_summary(arm, result()["arms"][0])


def test_plot_writes_png(tmp_path):
    loaded = MODULE.bind_inputs(six_inputs(tmp_path), tmp_path / "bound")
    reference_path = tmp_path / "reference.json"
    reference_path.write_text('{"latitude_deg":37.5,"longitude_deg":-122.2}')
    summary = MODULE.summarize(
        loaded, json.loads(reference_path.read_text()), reference_path
    )
    target = tmp_path / "plot.png"
    MODULE.plot(summary, target)
    assert target.read_bytes().startswith(b"\x89PNG")
