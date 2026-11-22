from importlib import import_module
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest

trial = import_module("reports.ALGO08.single-core-2x.longitude_chart_successor")
RUN = Path("reports/ALGO08/single-core-2x/run-candidate")


@pytest.fixture
def reviewed_fixture(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    source = tmp_path / "source"
    pin = tmp_path / "parent-receipt.json"
    library = Path("graph-path.so")
    base = {
        RUN: b"runner",
        trial.LAUNCHER: b"old entry",
        trial.RECEIVER: b"receiver",
        library: b"lib",
        Path("unlisted"): b"unmodified",
    }
    for path, content in base.items():
        file = parent / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    pins = {str(path): trial.digest(parent / path) for path in base if path != Path("unlisted")}
    original = dict(
        detector=str(parent / trial.RECEIVER),
        detector_sha256=pins[str(trial.RECEIVER)],
        solver="screened-tiled-finish",
        regional_veto=True,
        regional_veto_terminal_only=True,
        graph_path={"library": str(parent / library), "sha256": pins[str(library)]},
        sparse_rank_projection="reviewed released scan",
        sources=pins,
    )
    trial.write(parent / "spec.json", original)
    trial.write(pin, {"spec": original})
    for path in trial.SOURCES:
        location = source / path
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_bytes((trial.SOURCE / path).read_bytes())
    monkeypatch.setattr(trial, "SOURCE", source)
    monkeypatch.setattr(trial, "PARENT", canonical_digest(original))
    monkeypatch.setattr(trial, "PARENT_RECEIPT", pin)
    monkeypatch.setattr(trial, "PARENT_RECEIPT_SHA", trial.digest(pin))
    return parent, source, pin, tmp_path / "successor", tmp_path / "receipt.json"


def test_freeze_rebases_library_paths_and_changes_only_chart_entry(reviewed_fixture):
    parent, _, _, output, receipt = reviewed_fixture
    before = trial.files(parent)
    trial.freeze(parent, output, receipt)
    assert trial.files(parent) == before
    trial.check_files(before, trial.files(output))
    report = trial.read(receipt)
    spec = trial.read(output / "spec.json")
    assert report["specification"] == canonical_digest(spec)
    assert spec == report["spec"] and spec["wrapped_longitude"] is True
    assert spec["graph_path"]["library"] == str(output / "graph-path.so")
    assert spec["detector_sha256"] == before[trial.RECEIVER]
    assert set(report["changed_files"]) == {str(path) for path in trial.CHANGED}


@pytest.mark.parametrize("file", ["old-entry", "new-chart", "new-entry", "parent-receipt"])
def test_freeze_rejects_source_or_receipt_tampering_before_creating_successor(
    reviewed_fixture, file
):
    parent, source, pin, output, receipt = reviewed_fixture
    changed = {
        "old-entry": parent / trial.LAUNCHER,
        "new-chart": source / trial.LONGITUDE_CHART_SOURCE,
        "new-entry": source / trial.LAUNCHER,
        "parent-receipt": pin,
    }[file]
    changed.write_bytes(b"mismatched")
    with pytest.raises(ValueError, match="source|reviewed spectral"):
        trial.freeze(parent, output, receipt)
    assert not output.exists() and not receipt.exists()
