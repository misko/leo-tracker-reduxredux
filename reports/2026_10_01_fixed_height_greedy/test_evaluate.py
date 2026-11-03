import importlib.util,hashlib,json,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("fixed_eval",HERE/"evaluate.py");assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=module;SPEC.loader.exec_module(module)


def test_failed_point_is_diagnostic_not_accepted_error():
    receipt={"schema":"fixed-msl-greedy-replay/v1","unit_id":"U","arm":"beam","_variant":"v",
      "status":"error","components":[{"weight":1,"mean":[0,0]}],"checkpoints":[{}],"planned_factors":2,
      "_launch":{"wall_seconds":3,"status":"complete","returncode":1},"_sealed":True,
      "_path":"p","_sha256":"sha256:x","_verified_sources":[]}
    row=module.evaluate([receipt])["rows"][0]
    assert row["error_m"] is None and row["failed_point_error_m_diagnostic"] is not None
    assert row["numerically_converged"] is None and row["processing_complete"] is False


def test_joint_uses_best_mean_and_iteration_count():
    receipt={"schema":"fixed-height-joint-greedy/v1","unit_id":"U","_variant":"joint-v1",
      "status":"converged_local_mode","planned_factors":2,
      "best":{"mean":[1,2,3],"iterations":7,"converged":True,"associations":["1","background"]},
      "fits":[{"converged":False},{"converged":True}],
      "_launch":{"status":"complete","returncode":0},"_sealed":True,"wall_seconds":4,
      "_path":"p","_sha256":"sha256:x","_verified_sources":[]}
    row=module.evaluate([receipt])["rows"][0]
    assert row["point_rule"]=="joint_best_mean" and row["iterations"]==7 and row["error_m"] is not None
    assert row["processing_complete"] and row["num_factors_fit"]==2
    assert row["seed_fits_attempted"]==2 and row["seed_fits_converged"]==1


def test_sequential_complete_is_not_optimizer_convergence_claim():
    receipt={"schema":"fixed-msl-greedy-replay/v1","unit_id":"U","arm":"beam","_variant":"v",
      "status":"complete","components":[{"weight":1,"mean":[0,0]}],"checkpoints":[{},{}],
      "planned_factors":2,"_launch":{"status":"complete","returncode":0},"_sealed":True,
      "wall_seconds":1,"_path":"p","_sha256":"sha256:x","_verified_sources":[]}
    row=module.evaluate([receipt])["rows"][0]
    assert row["processing_complete"] is True and row["numerically_converged"] is None
    assert row["num_factors_fit"]==2


def test_changed_live_source_can_verify_through_snapshot(tmp_path):
    live=tmp_path/"live.py";live.write_text("changed")
    snap=tmp_path/"snap.py";snap.write_text("frozen")
    expected=module.sha256(snap)
    result=module.verify_source_bindings({str(live):expected},{(str(live),expected):snap})
    assert result[0]["verified_via"]=="archived_snapshot"
    snap.write_text("bad")
    with pytest.raises(ValueError,match="no valid"):module.verify_source_bindings({str(live):expected},{(str(live),expected):snap})
