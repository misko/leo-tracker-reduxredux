import importlib.util,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("continuation_eval",HERE/"evaluate_continuation.py");assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=module;SPEC.loader.exec_module(module)


def primary_row(status="unresolved"):
    return {"unit_id":"U","dataset":"DS9","attempted":True,"status":status,"numerically_converged":False,
      "error_m":None,"failed_point_error_m_diagnostic":100.,"east_km":0.,"north_km":0.,"num_factors_fit":2,"runtime_s":80.}


def test_converged_resume_overlays_but_preserves_primary():
    document={"publication_ready":False,"attempted_count":1,"rows":[primary_row()]}
    receipt={"status":"converged_local_mode","best":{"mean":[1.,2.],"converged":True,"iterations":4,"associations":["1","2"]},
             "resumed_fits":[{"converged":True},{"converged":False}]}
    resumes={"U":{"launch":{"status":"complete","returncode":0,"wall_seconds":30.},"launch_path":"l","sealed":True,"receipt":receipt}}
    row=module.overlay(document,resumes)["rows"][0]
    assert row["primary"]["status"]=="unresolved" and row["effective_native_numerically_converged"]
    assert row["effective_accepted"] and row["effective_error_m"] is not None and row["total_runtime_s"]==110.
    assert row["continuation"]["resumed_fits_attempted"]==2


def test_missing_resume_leaves_primary_failure():
    result=module.overlay({"publication_ready":False,"attempted_count":1,"rows":[primary_row()]},{})
    row=result["rows"][0]
    assert not row["continuation_attempted"] and row["effective_error_m"] is None
    assert row["effective_failed_point_error_m_diagnostic"]==100.


def test_native_convergence_is_not_accepted_on_bad_launch_or_over_budget():
    receipt={"status":"converged_local_mode","best":{"mean":[1.,2.],"converged":True,"iterations":4,"associations":["1"]},"resumed_fits":[]}
    for launch in ({"status":"error","returncode":1,"wall_seconds":30.},
                   {"status":"complete","returncode":0,"wall_seconds":101.}):
        resumes={"U":{"launch":launch,"launch_path":"l","sealed":True,"receipt":receipt}}
        row=module.overlay({"publication_ready":False,"attempted_count":1,"rows":[primary_row()]},resumes)["rows"][0]
        assert row["effective_native_numerically_converged"] is True
        assert not row["effective_accepted"] and row["effective_error_m"] is None
        assert row["effective_failed_point_error_m_diagnostic"] is not None
