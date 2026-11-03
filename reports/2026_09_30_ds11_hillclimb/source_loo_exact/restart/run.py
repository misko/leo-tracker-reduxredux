"""One explicitly separate restart of the saved near-stationary failed fold."""
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
SCREEN = HERE.parent / "screen"
KEY = "04_robust_t8_scale100_65855"


def eligible(fold):
    opt = fold["optimizer"]
    return bool(not opt["success"] and not opt["qualified"] and not opt["boundary"]
                and np.isfinite(fold["x"]).all()
                and np.isfinite(fold["retained_score"])
                and opt["gradient_max_abs"] is not None
                and 0 <= opt["gradient_max_abs"] <= 0.01
                and opt["gradient_audit_max_abs"] is not None
                and 0 <= opt["gradient_audit_max_abs"] <= 0.02)


def main():
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location("restart_screen", SCREEN / "run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    plan = runner.load_plan()
    path = SCREEN / "runs" / f"{KEY}.json"
    old = json.loads(path.read_text())
    receipt_path = path.with_suffix(".receipt.json")
    receipt = json.loads(receipt_path.read_text())
    assert receipt["exit_code"] == 0 and receipt["job_key"] == KEY
    assert receipt["run_sha256"] == runner.digest(SCREEN / "run.py")
    assert receipt["plan_sha256"] == runner.digest(SCREEN / "plan.json")
    for p, expected in old["sources"].items():
        assert runner.digest(p) == expected, p
    fold = old["fold"]
    assert eligible(fold)
    job = next(j for j in plan["jobs"] if runner.job_key(j) == KEY)
    assert old["full_endpoint_x"] == job["full_endpoint_x"]
    pilot = runner.module("restart_pilot", HERE.parent / "run.py")
    pilot.fast.baseline.profile = pilot.fast.profile
    diagnose = runner.module("restart_diagnose", pilot.HILL / "source_loo" / "diagnose.py")
    exact = runner.module("restart_exact", pilot.HILL / "source_loo" / "exact_audit.py")
    context = runner.module("restart_context", SCREEN / "input_context.py")
    source = runner.module("restart_source", pilot.HILL / "source_balance" / "model.py")
    robust = runner.module("restart_robust", pilot.HILL / "robust" / "model.py")
    _, base, entry, documents, _, norad_map = context.load_scan(4)
    assert old["session_id"] == entry["session_id"]
    _, _, _, iid_x, _, _ = diagnose.load_endpoint(
        "iid_t4_scale100", diagnose.FAMILIES["iid_t4_scale100"], 4, entry["session_id"])
    assignments = source.freeze_assignments(documents, base["config"], iid_x, norad_map)
    weights = source.derive_weights(assignments, "source_receiver_equal")
    runner.check_frozen_assignments(plan, 4, assignments, weights)
    subset = pilot.retained_fold(assignments, weights, job["norad"])
    assert fold["track_ids"] == job["source_track_ids"] == [
        assignments[i]["track_id"] for i in subset["omitted_indices"]]
    retained = diagnose.subset_document(documents[0], subset["retained_indices"])
    model = diagnose.build_evaluator("robust", "df8", retained, base["config"],
                                    {"source": source, "robust": robust})
    initial = model.evaluate(np.asarray(fold["x"]), gradient=True)
    assert abs(initial["score"] - fold["retained_score"]) <= 1e-7
    assert abs(np.max(np.abs(initial["gradient"])) - fold["optimizer"]["gradient_max_abs"]) <= 1e-7
    result, qualification = pilot.fit_local(model, fold["x"], diagnose.BOUNDS, exact.qualify)
    held = exact.common_held_score(documents[0], subset["omitted_indices"], result.x, base["config"])
    change = float(-result.fun - fold["retained_score"])
    out = dict(schema="ds11-source-loo-restart-diagnostic/v1", reference_used=False,
               job_key=KEY, original_failed_result=str(path), seed=fold["x"],
               x=result.x.tolist(), retained_score=float(-result.fun),
               retained_score_change=change, optimizer=qualification,
               nfev=int(result.nfev), nit=int(result.nit),
               endpoint_en_change_m=float(1000 * np.linalg.norm(result.x[:2] - np.asarray(fold["x"][:2]))),
               time_change_s=float(result.x[2] - fold["x"][2]),
               common_held_score=held["score"], common_held_change=held["score"]-fold["common_held_score"],
               diagnostic_passed=bool(qualification["qualified"] and change >= -1e-7),
               elapsed_s=time.monotonic()-started,
               sources={str(p): runner.digest(p) for p in (
                   HERE / "run.py", HERE / "PROTOCOL.md", HERE / "test_run.py",
                   SCREEN / "plan.json", path, receipt_path)})
    with (HERE / "result.json").open("x") as stream:
        json.dump(out, stream, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k != "sources"}))


if __name__ == "__main__":
    main()
