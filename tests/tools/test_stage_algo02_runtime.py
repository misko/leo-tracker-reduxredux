"""ALGO02 staging must preserve the scientific and exact-runtime qualification."""

import copy
import json

import pytest
import stage_algo02_runtime as stage


def evidence():
    parity = dict(exact=True, files=6, tolerance=0, difference_count=0,
                  both_calibration_arms_required=True)
    audits = [dict(parity, frozen_inputs_verified=True, read_audit={"verified": True},
                   runtime_manifest_sha256=pin) for pin in ("original", "candidate")]
    return [dict(exact=True, matched_timing_configuration=True, cprofile_enabled=False,
                 wall_speedup=1.4, parity=parity, reference_audits=audits),
            dict(source_manifest_sha256="original", candidate_manifest_sha256="candidate"),
            dict(passed=True, cases=175, paired_arms=350, reference_after={"verified": True})]


def test_complete_qualification_passes():
    stage.qualification(*evidence())


@pytest.mark.parametrize("field,value", [("exact", False), ("cprofile_enabled", True),
    ("wall_speedup", .99), ("matched_timing_configuration", False)])
def test_invalid_comparison_rejected(field, value):
    rows = evidence()
    rows[0][field] = value
    with pytest.raises(ValueError):
        stage.qualification(*rows)


@pytest.mark.parametrize("field,value", [("files", 5), ("difference_count", 1),
    ("tolerance", 1e-10), ("both_calibration_arms_required", False)])
def test_incomplete_scientific_reference_rejected(field, value):
    rows = copy.deepcopy(evidence())
    rows[0]["reference_audits"][1][field] = value
    with pytest.raises(ValueError):
        stage.qualification(*rows)


def test_replay_must_match_exact_candidate_manifest():
    rows = evidence()
    rows[1]["candidate_manifest_sha256"] = "another-runtime"
    with pytest.raises(ValueError, match="another runtime"):
        stage.qualification(*rows)


def test_package_files_pin_and_incomplete_marker(tmp_path):
    source = tmp_path / "worker.py"
    source.write_text("# original\n")
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(dict(kind=stage.KIND,
        files_sha256={"worker.py": stage.digest(source)})))
    pin = stage.digest(path)
    stage.verify(tmp_path, pin)
    source.write_text("# changed\n")
    with pytest.raises(ValueError, match="member changed"):
        stage.verify(tmp_path, pin)
    with pytest.raises(ValueError, match="unpinned"):
        stage.verify(tmp_path, "wrong")
    (tmp_path / ".incomplete").touch()
    with pytest.raises(ValueError, match="Incomplete"):
        stage.verify(tmp_path, pin)
