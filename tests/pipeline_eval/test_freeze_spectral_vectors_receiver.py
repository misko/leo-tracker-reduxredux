from importlib import import_module
import json
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


@pytest.fixture
def bundle_inputs(tmp_path, monkeypatch):
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(reports))
    trial = import_module("reports.ALGO08.single-core-2x.freeze_spectral_vectors_receiver")
    source, parent = tmp_path / "sources", tmp_path / "parent"
    parent.mkdir()
    inputs = {
        Path("receiver.so"): b"prior receiver",
        Path("solver.so"): b"unchanged solver",
        Path("sealed-inventory.json"): b"unchanged inventory",
        Path("reports/ALGO08/single-core-2x/run-candidate"): b"unchanged launcher",
    }
    for relative, data in inputs.items():
        path = parent / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    spec = dict(
        detector=str(parent / "receiver.so"), detector_sha256=trial.digest(parent / "receiver.so"),
        graph_path=dict(library=str(parent / "solver.so"), sha256=trial.digest(parent / "solver.so")),
        regional_veto_terminal_only=True, schedule="all", solver="screened-stock-finish",
        sources={str(file): trial.digest(parent / file) for file in inputs},
    )
    (parent / "spec.json").write_text(json.dumps(spec))
    candidate = tmp_path / "candidate.so"
    candidate.write_bytes(b"reviewed receiver")
    source_pins = {}
    for relative in trial.SOURCES:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(relative))
        source_pins[relative] = trial.digest(path)
    monkeypatch.setattr(trial, "SOURCE", source)
    monkeypatch.setattr(trial, "SOURCES", source_pins)
    monkeypatch.setattr(trial, "PARENT_SHA", canonical_digest(spec))
    monkeypatch.setattr(trial, "REFERENCE_SHA", spec["detector_sha256"])
    monkeypatch.setattr(trial, "CANDIDATE_SHA", trial.digest(candidate))
    monkeypatch.setattr(trial, "verify_evidence", lambda bench, receiver: {"native": str(receiver)})
    return trial, parent, candidate, tmp_path / "child", tmp_path / "receipt.json"


def test_freeze_keeps_terminal_solver_and_source_pins(bundle_inputs):
    trial, parent, candidate, child, receipt = bundle_inputs
    trial.freeze(parent.parent, parent, candidate, child, receipt)
    previous, after = (trial.read(path / "spec.json") for path in (parent, child))
    assert after["detector_sha256"] == trial.digest(candidate)
    assert after["graph_path"] == previous["graph_path"] | {"library": str(child / "solver.so")}
    for key in ("solver", "regional_veto_terminal_only", "schedule"):
        assert after[key] == previous[key]
    assert after["sources"]["sealed-inventory.json"] == previous["sources"]["sealed-inventory.json"]
    assert trial.read(receipt)["specification"] == canonical_digest(after)
    assert (child / "solver.so").read_bytes() == (parent / "solver.so").read_bytes()


@pytest.mark.parametrize("tamper", ["inherited", "new", "receiver"])
def test_freeze_checks_existing_and_added_source_bytes(bundle_inputs, tamper):
    trial, parent, candidate, child, receipt = bundle_inputs
    if tamper == "inherited":
        (parent / "sealed-inventory.json").write_bytes(b"tampered")
    elif tamper == "new":
        (trial.SOURCE / next(iter(trial.SOURCES))).write_bytes(b"tampered")
    else:
        candidate.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        trial.freeze(parent.parent, parent, candidate, child, receipt)
    assert not child.exists()
