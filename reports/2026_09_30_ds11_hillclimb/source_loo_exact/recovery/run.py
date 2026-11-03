"""Run the prospectively gated single SLSQP continuation diagnostic."""
import importlib.util
import json
from pathlib import Path
import time

import numpy as np
from scipy.optimize import OptimizeResult

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def precision_passed(record):
    n = record["numerical"]
    return bool(record["finite_checks_passed"] and n["stable_by_established_limits"]
                and n["newton_solve_available"]
                and n["newton_en_displacement_m"] <= 0.01
                and abs(n["newton_time_displacement_s"]) <= 1e-5)


def main():
    started = time.monotonic()
    precision_path = HERE.parent / "precision" / "run.py"
    precision = module("recovery_precision", precision_path)
    evidence_path = precision_path.with_name("result.json")
    evidence = json.loads(evidence_path.read_text())
    precision.check_sources(evidence)
    assert evidence["job_key"] == precision.KEY and evidence["reference_used"] is False
    assert precision_passed(evidence), "local precision gate did not pass"
    model, old, context, sources = precision.load_case()
    solver = module("recovery_solver", HERE / "solver.py")
    exact = module("recovery_exact", HERE.parents[1] / "source_loo" / "exact_audit.py")
    fold = old["fold"]
    original = OptimizeResult(x=np.asarray(fold["x"]), fun=-fold["retained_score"],
                              jac=-np.asarray(context["initial"]["gradient"]), success=False)
    result, qualification, accepted = solver.recover(
        model, original, fold["optimizer"], context["bounds"], exact.qualify)
    held = exact.common_held_score(context["documents"][0],
        context["subset"]["omitted_indices"], result.x, context["config"])
    assert held["held_observation_count"] == fold["held_observation_count"]
    for path in (HERE / "run.py", HERE / "solver.py", HERE / "PROTOCOL.md",
                 HERE / "test_solver.py", HERE / "test_run.py", evidence_path):
        sources[str(path)] = precision.digest(path)
    out = dict(schema="ds11-source-loo-slsqp-recovery-diagnostic/v1",
        reference_used=False, job_key=precision.KEY, original_failed_result=old,
        seed=original.x.tolist(), x=result.x.tolist(), optimizer=qualification,
        retained_score=float(-result.fun), retained_score_change=float(original.fun-result.fun),
        endpoint_en_change_m=float(1000*np.linalg.norm(result.x[:2]-original.x[:2])),
        time_change_s=float(result.x[2]-original.x[2]),
        common_held_score=held["score"], common_held_change=held["score"]-fold["common_held_score"],
        nfev=int(result.nfev), nit=int(result.nit), diagnostic_passed=accepted,
        elapsed_s=time.monotonic()-started, sources=sources)
    with (HERE / "result.json").open("x") as stream:
        json.dump(out, stream, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k not in ("sources", "original_failed_result")}))


if __name__ == "__main__":
    main()
