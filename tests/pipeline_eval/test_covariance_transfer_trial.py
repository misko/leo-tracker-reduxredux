import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from tools.pipeline_eval.__main__ import encoded


@pytest.fixture(scope="module")
def trial():
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    source = reports / "covariance_transfer_trial.py"
    spec = spec_from_file_location(source.stem, source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_lock_binds_document_offer_and_archive(trial):
    document = {"probes": [1, 2]}
    tile = {"center": [1, 8], "width_km": 25}
    history = [{"collected_utc_ns": 1, "sha256": "d"}]
    row = dict(
        offer=tile,
        document_sha256=trial.digest(encoded(document)),
        history_sha256=trial.digest(encoded(history)),
        input_sha256=trial.digest(encoded(dict(document=document, tile=tile, history=history))),
    )
    assert trial.matched_inputs(row, document, tile, history)
    assert not trial.matched_inputs(row, {"probes": [2, 1]}, tile, history)
    assert not trial.matched_inputs(row, document, dict(tile, width_km=24), history)
    assert not trial.matched_inputs(row, document, tile, [dict(history[0], collected_utc_ns=2)])
    assert not trial.matched_inputs(dict(row, input_sha256=""), document, tile, history)


def test_archive_staging_rejects_equal_cutoff_and_mutated_bytes(trial, tmp_path):
    content = b"published TLE object"
    key = trial.digest(content)
    source = tmp_path / "snapshot"
    source.write_bytes(content)
    history = [{"sha256": key, "collected_utc_ns": 3}]
    with pytest.raises(ValueError, match="strictly causal"):
        trial.stage_history(tmp_path / "site", history, {key: source}, 3)
    source.write_bytes(content + b" (changed)")
    with pytest.raises(ValueError, match="object changed"):
        trial.stage_history(tmp_path / "site", history, {key: source}, 4)
    source.write_bytes(content)
    trial.stage_history(tmp_path / "site", history, {key: source}, 4)
    (staged,) = (tmp_path / "site/tle/archive/space-track").iterdir()
    assert staged.name == f"3-{key}.tle"
    assert staged.read_bytes() == content


def test_score_reads_complete_predictions_before_reference(trial, monkeypatch, tmp_path):
    offer = {"center": [48., 12.], "width_km": 25.}
    plan = [dict(case="case", mode="matched-tile", offer=offer)]
    trial.write(tmp_path / "plan.json", plan)
    case = tmp_path / "case"
    case.mkdir()
    output = tmp_path / "result.json"
    reference_reads = []

    def released_reference():
        reference_reads.append(True)
        return {"case": {"position": [48., 12.]}}, {}

    monkeypatch.setattr(trial, "scoring_references", released_reference)
    with pytest.raises(FileNotFoundError):
        trial.score(tmp_path, output)
    assert reference_reads == []
    result = dict(
        status="withheld", reason="test", arms={arm: {"latlon": None} for arm in trial.ARMS},
    )
    for build in ("installed", "covariance"):
        trial.write(case / f"matched-tile-{build}.json", result)
    trial.score(tmp_path, output)
    row, = json.loads(output.read_bytes())["rows"]
    assert reference_reads == [True]
    assert row["offer_center_error_km"] == 0
    assert row["reference_clearance_km"] == 12.5
    assert row["builds"]["covariance"]["reason"] == "test"
    assert [a["horizontal_error_km"] for a in row["builds"]["covariance"]["arms"].values()] == [
        None, None,
    ]
