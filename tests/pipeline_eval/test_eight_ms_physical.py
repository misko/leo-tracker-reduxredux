"""An aperture transfer must pass on both calibrations against both controls."""

import importlib
from hashlib import sha256
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("fixed,fitted,complete,passes", [
    (1.625, 1.75, True, True),
    (1.626, 1.75, True, False),
    (1.625, 1.751, True, False),
    (1.0, 1.0, False, False),
    (1.0, None, True, False),
])
def test_both_controls_and_calibrations_gate_physical_transfer(monkeypatch, fixed, fitted, complete, passes):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    score = importlib.import_module("eight_ms_physical_score")
    controls = {"12ms": {"c0": 1.375, "fitted_c": 2.0}, "v3": {"c0": 2.0, "fitted_c": 1.5}}
    assert score.quality({"c0": fixed, "fitted_c": fitted}, controls, complete=complete)["passes"] is passes


def test_public_transfer_recomputes_the_physical_gate(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    score = importlib.import_module("eight_ms_physical_score")
    north = importlib.import_module("eight_ms_north")
    benchmark = {"c0": 1., "fitted_c": 1.125}
    candidate = {"c0": 1.25, "fitted_c": 1.375}
    controls = {"v3": benchmark, "12ms": benchmark}
    output = tmp_path / "physical-score.json"
    row = {"case": "DS30-0016", "original_pair_sha256": score.REFERENCE_SHA,
           "position": score.quality(candidate, controls, complete=True),
           "runs": {name: {"errors_km": value} for name, value in controls.items()}}
    row["runs"]["8ms"] = {"decision": "complete", "errors_km": candidate}
    output.write_text(json.dumps(row))
    assert north.authorized(output) == sha256(output.read_bytes()).hexdigest()
    candidate["fitted_c"] = 1.376
    output.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="did not authorize"):
        north.authorized(output)
