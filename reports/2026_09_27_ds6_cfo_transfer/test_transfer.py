"""Evidence checks for the frozen real-data transfer experiment."""
import hashlib
import json
from pathlib import Path

import pytest
import numpy as np

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text())


@pytest.mark.parametrize("name,expected", PROTOCOL["inputs"].items())
def test_inputs_and_randomized_whole_visit_partitions_are_unchanged(name, expected):
    path = HERE.parent / "2026_09_27_ds6_common_rate_validation" / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    data = json.loads(path.read_text())
    partitions = {}
    for track in data["tracks"]:
        for visit, training in zip(track["visits"], track["training_mask"], strict=True):
            assert visit not in partitions or partitions[visit] == training
            partitions[visit] = training
    assert set(partitions.values()) == {False, True}


@pytest.mark.parametrize("name", PROTOCOL["inputs"])
def test_real_search_coverage_and_training_only_selection(name):
    result = json.loads((HERE / name.replace("-plan", "")).read_text())
    assert result["protocol_sha256"] == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    assert result["complete"] or result["stages"][-1]["boundary"]
    for stage in result["stages"]:
        assert len(stage["rows"]) == 49
        assert len({(row["latitude"], row["longitude"]) for row in stage["rows"]}) == 49
        assert stage["best"] == max(stage["rows"], key=lambda row: row["train"])
        # Arbitrary held scores cannot change this predeclared decision.
        perturbed = [dict(row, held=1e9 * index) for index, row in enumerate(stage["rows"])]
        chosen = max(perturbed, key=lambda row: row["train"])
        assert (chosen["latitude"], chosen["longitude"]) == (
            stage["best"]["latitude"], stage["best"]["longitude"])


def test_receiver_drift_recovers_injected_slopes_without_held_data_leakage():
    from clock_audit import fit_drift
    times = np.linspace(-20, 20, 40)
    mask = np.arange(40) % 2 == 0
    times -= times[mask].mean()
    rows = [dict(receiver_id=rx, residual=offset+slope*times, time=times, mask=mask)
            for rx, slope in [(0, 2.), (1, -1.5)] for offset in [-800., 500., 1200.]]
    slopes, offsets = fit_drift(rows)
    assert slopes == pytest.approx({0: 2., 1: -1.5}, abs=1e-7)
    changed = [dict(row, residual=row['residual']+np.where(mask, 0., 10000.)) for row in rows]
    changed_slopes, changed_offsets = fit_drift(changed)
    assert changed_slopes == slopes
    np.testing.assert_array_equal(changed_offsets, offsets)
