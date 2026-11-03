"""Native staging cannot pass partial, slower or scientifically changed trials."""

import copy
import json

import pytest
import stage_native_glrt_runtime as native


def evidence():
    return [dict(exact=True, mismatch_count=0, windows=6772, receiver_results=13534,
                 all_candidates=108272, matched_timing_configuration=True, wall_speedup=1.4,
                 frozen_verification={"verified": True}),
            dict(exact=True, tolerance=0, files=6, difference_count=0,
                 both_calibration_arms_required=True, frozen_inputs_verified=True,
                 read_audit={"verified": True}),
            dict(passed=True, unique_windows=80, receiver_outputs=160),
            dict(passed=True, cases=175)]


def test_complete_evidence_required():
    native.qualification(*evidence())


@pytest.mark.parametrize("index,field,value", [
    (0, "matched_timing_configuration", False), (0, "wall_speedup", .99),
    (0, "windows", 16), (0, "all_candidates", 108271), (0, "mismatch_count", 1),
    (1, "both_calibration_arms_required", False), (1, "difference_count", 1),
    (1, "frozen_inputs_verified", False), (2, "passed", False), (3, "cases", 174)])
def test_failed_qualification_cannot_stage(index, field, value):
    rows = copy.deepcopy(evidence())
    rows[index][field] = value
    with pytest.raises(ValueError):
        native.qualification(*rows)


def test_runtime_pin_and_source_bytes_required(tmp_path):
    member = tmp_path / "worker.py"
    member.write_text("# original\n")
    manifest = tmp_path / "runtime-manifest.json"
    manifest.write_text(json.dumps(dict(kind=native.KIND,
        files_sha256={"worker.py": native.digest(member)})))
    pin = native.digest(manifest)
    assert native.verify(tmp_path, pin)["kind"] == native.KIND
    member.write_text("# changed\n")
    with pytest.raises(ValueError, match="member differs"):
        native.verify(tmp_path, pin)
    with pytest.raises(ValueError, match="unpinned"):
        native.verify(tmp_path, "0" * 64)


def test_incomplete_release_is_never_usable(tmp_path):
    (tmp_path / ".incomplete").touch()
    with pytest.raises(ValueError, match="Incomplete"):
        native.verify(tmp_path, "0" * 64)
