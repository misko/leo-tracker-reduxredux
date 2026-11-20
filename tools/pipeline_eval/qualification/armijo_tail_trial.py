"""Trace solver-sensitive cases and confirm a centered stop on a disjoint roster."""

import argparse
import gzip
import json
import os
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import orbit_projector, v5_armijo_fit, v5_armijo_tail, v5_core, v5_lean, v5_secant_fit
from .armijo_confirmation import binding, original_result
from .broad_search_budget import _case
from .full_v5_check import _load_case, _sha
from .recording_to_v5 import save
from .secant_fit_trial import failed_result

REPORT = ROOT / "reports/2026_11_19_receiver_screening/inference/solver-tail"
ARCHIVE = ROOT / "reports/2026_11_19_receiver_screening/secant-full"
DIAGNOSTIC = ("DS26-0152", "DS26-0283", "DS26-0092")
EXCLUDED = set(DIAGNOSTIC) | {
    "DS26-0036", "DS26-0122", "DS26-0237", "DS26-0142", "DS26-0223", "DS26-0301",
    "DS26-0018", "DS26-0066", "DS26-0287", "DS26-0002", "DS26-0072", "DS26-0012",
    "DS26-0076", "DS26-0030", "DS26-0175", "DS26-0114", "DS26-0058", "DS26-0052",
}
SALT = "solver-tail-v1:"
VARIANTS = dict(stock="orbit_projector", secant="v5_secant_fit", tail="v5_armijo_tail")
CASE_LIMIT = 480


def seal():
    prior = json.loads((ARCHIVE / "plan.json").read_bytes())
    eligible = [ident for ident in prior["cases"] if ident.startswith("DS26-") and ident not in EXCLUDED]
    held = sorted(eligible, key=lambda ident: sha256((SALT + ident).encode()).digest())[:4]
    lanes = {
        "8": [("stock", DIAGNOSTIC[2]), ("secant", DIAGNOSTIC[2]),
              ("tail", held[0]), ("tail", held[1]), ("tail", DIAGNOSTIC[2])],
        "9": [("stock", DIAGNOSTIC[0]), ("secant", DIAGNOSTIC[0]),
              ("tail", held[2]), ("tail", held[3]),
              ("stock", DIAGNOSTIC[1]), ("secant", DIAGNOSTIC[1]),
              ("tail", DIAGNOSTIC[0]), ("tail", DIAGNOSTIC[1])],
    }
    dependencies = (v5_armijo_tail, v5_armijo_fit, v5_core, v5_lean, orbit_projector, v5_secant_fit)
    sources = [Path(module.__file__) for module in dependencies] + [Path(__file__), orbit_projector.KERNEL]
    return dict(
        diagnostics=list(DIAGNOSTIC),
        confirmation=held,
        exclusions=sorted(EXCLUDED),
        selector="First four eligible DS26 IDs by SHA-256(solver-tail-v1: + id), no scores read",
        lanes={cpu: [list(task) for task in lane] for cpu, lane in lanes.items()},
        case_limit_s=CASE_LIMIT,
        solver=dict(stop_km=0.001, symmetric_rounds=2, backtracks=6, armijo=0.0001,
                    min_decrease=1e-9, original_phase_refreshes=5,
                    trigger="small projected 20 m Armijo step"),
        bindings={ident: binding(ident) for ident in [*DIAGNOSTIC, *held]},
        sources={str(path.relative_to(ROOT)): _sha(path) for path in sources},
        frozen_panel_plan_sha256=_sha(ARCHIVE / "plan.json"),
        frozen_panel_predictions_sha256=_sha(ARCHIVE / "prediction-lock.json"),
    )


def check_plan(path):
    frozen = json.loads(path.read_bytes())
    if frozen != seal():
        raise ValueError("solver or inputs differ from the frozen schedule")
    return frozen


def attempt(ident, method, directory, frozen, plan_path):
    cpu = min(os.sched_getaffinity(0))
    if os.sched_getaffinity(0) != {cpu} or [method, ident] not in frozen["lanes"][str(cpu)]:
        raise ValueError("replay is outside its assigned CPU lane")
    output = directory / method / ident
    output.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    timeout = v5_lean.TIMEOUT_S
    try:
        v5_lean.TIMEOUT_S = CASE_LIMIT - 1
        result = v5_armijo_tail.run(
            _case(_load_case(ident)), output / "position", method, ident in DIAGNOSTIC
        )
        if "exceeded its " in result.get("reason", ""):
            result["status"] = "timed_out"
    finally:
        v5_lean.TIMEOUT_S = timeout
    validate_result(result)
    save(output / "prediction.json", dict(
        frozen["bindings"][ident], variant=VARIANTS[method], cpu=cpu, result=result,
        worker_wall_s=perf_counter() - started, plan_sha256=_sha(plan_path),
    ))
    print(ident, method, result["status"], perf_counter() - started, flush=True)


def predict_row(ident, method, attempts, frozen, plan_path):
    binding = dict(frozen["bindings"][ident], variant=VARIANTS[method])
    path = attempts / method / ident / "prediction.json"
    if not path.is_file():
        return dict(binding, worker_wall_s=None, plan_sha256=_sha(plan_path),
                    result=failed_result("missing", "No saved execution receipt before scoring"))
    row = json.loads(path.read_bytes())
    if (
        any(row.get(k) != v for k, v in binding.items())
        or row.get("plan_sha256") != _sha(plan_path)
        or [method, ident] not in frozen["lanes"][str(row["cpu"])]
    ):
        raise ValueError(f"{ident} does not match the locked prediction input")
    validate_result(row["result"])
    if row["result"]["status"] == "ok":
        metrics = row["result"]["metrics"]
        counts = metrics["initial_phase_refresh_counts"]
        if not counts or any(count != 5 for count in counts):
            raise ValueError(f"{ident} changed the original five phase passes")
    return row


def _gzip(path, lines):
    write(path, gzip.compress(b"".join(encoded(line) + b"\n" for line in lines), mtime=0))


def export(attempts, plan_path, output):
    frozen = check_plan(plan_path)
    lock = json.loads((ARCHIVE / "prediction-lock.json").read_bytes())
    for name, digest in lock["files"].items():
        if _sha(ARCHIVE / name) != digest:
            raise ValueError(f"Frozen broad-panel file changed: {name}")
    stocks = read_predictions(ARCHIVE / "orbit_projector.jsonl.gz")
    secants = read_predictions(ARCHIVE / "v5_secant_fit.jsonl.gz")
    keys = ("native_sha256", "catalog_sha256", "input_sha256")

    def check_controls(row):
        public = frozen["bindings"][row["id"]]
        if any(row[key] != public[key] for key in keys):
            raise ValueError(f"{row['id']} uses different immutable archive inputs")
        validate_result(row["result"])
        return dict(
            row, variant=row["method"],
            worker_wall_s=row.get("worker_wall_s", row.get("archived_worker_wall_s")),
        )

    output.mkdir(parents=True, exist_ok=True)
    diagnostic = [predict_row(i, m, attempts, frozen, plan_path)
                  for i in frozen["diagnostics"] for m in VARIANTS]
    _gzip(output / "diagnostic-traces.jsonl.gz", diagnostic)
    ids = frozen["confirmation"]
    rows = dict(
        candidate=[predict_row(i, "tail", attempts, frozen, plan_path) for i in ids],
        stock=[check_controls(stocks[i]) for i in ids],
        secant=[check_controls(secants[i]) for i in ids],
    )
    # Freeze predictions before obtaining the paired original controls and scorer references.
    pred_files = {}
    for method, data in rows.items():
        path = output / f"{method}-positions.jsonl.gz"
        _gzip(path, data)
        pred_files[path.name] = _sha(path)
    save(output / "blind-prediction-lock.json", dict(
        cases=ids, plan_sha256=_sha(plan_path), files=pred_files,
        diagnostic_trace_sha256=_sha(output / "diagnostic-traces.jsonl.gz"),
    ))
    from .projector_roof import roster

    refs = {row["id"]: row for row in roster() if row["id"] in (*ids, *DIAGNOSTIC)}
    rows["original"] = [original_result(_load_case(i), refs[i], frozen["bindings"][i]) for i in ids]
    path = output / "original-positions.jsonl.gz"
    _gzip(path, rows["original"])
    save(output / "prediction-lock.json", dict(
        cases=ids, plan_sha256=_sha(plan_path),
        files={**pred_files, path.name: _sha(path)},
    ))
    scores = []
    diagnostic_sets = [diagnostic, [check_controls(stocks[i]) for i in DIAGNOSTIC],
                       [check_controls(secants[i]) for i in DIAGNOSTIC],
                       [original_result(_load_case(i), refs[i], frozen["bindings"][i]) for i in DIAGNOSTIC]]
    for cohort, data in (("confirmation", rows.values()), ("diagnostic", diagnostic_sets)):
        for method in data:
            for row in method:
                ident, result = row["id"], row["result"]
                for arm in ARMS:
                    measured = result["arms"][arm]
                    scores.append(dict(
                        cohort=cohort, id=ident, variant=row["variant"], arm=arm,
                        status=result["status"], reason=result.get("reason"),
                        error_km=distance_km(measured["latlon"], refs[ident]["truth"]),
                        rf_rms_hz=measured.get("rf_rms_hz"), worker_wall_s=row["worker_wall_s"],
                        optimizer=result.get("metrics", {}).get("position_optimizer"),
                    ))
    save(output / "score.json", scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seal", "lane", "export"))
    parser.add_argument("--plan", type=Path, default=REPORT / "plan.json")
    parser.add_argument("--attempts", type=Path, default=Path("/tmp/leo-armijo-tail-20261119"))
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.mode == "seal":
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        save(args.plan, seal())
    elif args.mode == "lane":
        frozen = check_plan(args.plan)
        for method, ident in frozen["lanes"][str(min(os.sched_getaffinity(0)))]:
            attempt(ident, method, args.attempts, frozen, args.plan)
    else:
        export(args.attempts, args.plan, args.output)


if __name__ == "__main__":
    main()
