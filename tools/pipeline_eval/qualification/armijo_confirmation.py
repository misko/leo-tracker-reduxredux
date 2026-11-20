"""Confirm the sealed Armijo solver and measure two deliberate cavity stress cases."""

import argparse
import gzip
import json
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, read_predictions, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import v5_armijo_fit as armijo
from ..variants import v5_lean
from .armijo_fit_trial import CASE_LIMIT_S, compare, source_seal
from .broad_search_budget import _case, _stock_archive
from .full_v5_check import _load_case, _sha
from .projector_roof import input_hash
from .recording_to_v5 import save
from .secant_fit_trial import failed_result

LANES = {
    8: ("DS26-0066", "DS26-0223", "DS29-0357"),
    9: ("DS26-0287", "DS26-0301", "DS29-0519"),
    20: ("DS26-0142", "DS26-0018"),
    21: ("DS29-0127", "DS29-0316"),
}
STRESS = ("DS26-0066", "DS26-0287")
CPUS = {ident: cpu for cpu, lane in LANES.items() for ident in lane}
PRIOR = ROOT / "reports/2026_11_19_receiver_convergence"


def binding(ident):
    item = _load_case(ident)
    case = _case(item)
    return dict(
        id=ident,
        variant="v5_armijo_fit",
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        input_sha256=input_hash(case),
        request_sha256=item["request"]["sha256"],
    )


def plan(prior, solver_seal):
    held = prior / "secant-confirmation"
    roster = json.loads((held / "roster.json").read_bytes())
    lock = json.loads((held / "prediction-lock.json").read_bytes())
    confirmed = roster["cases"]
    if (
        confirmed != lock["cases"]
        or len(confirmed) != 8
        or set(confirmed) | set(STRESS) != set(CPUS)
        or set(confirmed) & set(STRESS)
        or any(_sha(held / name) != digest for name, digest in lock["files"].items())
    ):
        raise ValueError("independent secant controls differ from their sealed roster")
    if json.loads(solver_seal.read_bytes()) != json.loads(
        encoded(source_seal(prior / "position-fit"))
    ):
        raise ValueError("Armijo candidate differs from the six-case source seal")
    case_bindings = {ident: binding(ident) for ident in CPUS}
    if any(
        case_bindings[ident][key] != digest
        for ident, item in roster["case_bindings"].items()
        for key, digest in item.items()
    ):
        raise ValueError("frozen confirmation native inputs differ")
    return dict(
        cohorts=dict(confirmation=confirmed, stress=list(STRESS)),
        cases=case_bindings,
        cpus=CPUS,
        case_limit_s=CASE_LIMIT_S,
        armijo_source_seal_sha256=_sha(solver_seal),
        secant_confirmation_lock_sha256=_sha(held / "prediction-lock.json"),
    )


def run(ident, output, prior, solver_seal, plan_path):
    expected = json.loads(plan_path.read_bytes())
    if expected != plan(prior, solver_seal) or os.sched_getaffinity(0) != {CPUS[ident]}:
        raise ValueError("replay differs from its frozen plan or CPU")
    case = _case(_load_case(ident))
    output.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    timeout = v5_lean.TIMEOUT_S
    try:
        v5_lean.TIMEOUT_S = CASE_LIMIT_S - 1
        result = armijo.run(case, output / "position")
        if "exceeded its " in result.get("reason", ""):
            result["status"] = "timed_out"
    finally:
        v5_lean.TIMEOUT_S = timeout
    validate_result(result)
    row = dict(
        binding(ident),
        cpu=CPUS[ident],
        result=result,
        worker_wall_s=perf_counter() - started,
        source_seal_sha256=_sha(solver_seal),
        plan_sha256=_sha(plan_path),
    )
    if expected != plan(prior, solver_seal):
        raise ValueError("solver source or independent controls changed during confirmation")
    save(output / "prediction.json", row)
    print(ident, result["status"], row["worker_wall_s"], flush=True)


def original_result(item, ref, public):
    from . import phase_confirmation as phase

    ident = item["id"]
    binding_receipt = phase._original_v5_bindings(item)["baseline"]
    root = phase.ARCHIVE if ident.startswith("DS26") else phase.DS29
    path = root / f"{ident}-r0" / "baseline-execution.json"
    if _sha(path) != binding_receipt["execution_sha256"]:
        raise ValueError("original execution receipt differs from the frozen request")
    control = json.loads(path.read_bytes())
    arms = {}
    for arm in ARMS:
        measured = control["worker"]["arms"][arm]
        frozen = ref["reference"]["baseline"][arm]
        if (
            point_delta := distance_km(measured["endpoint_latlon"], frozen["latlon"])
        ) is None or point_delta > 1e-6:
            raise ValueError(f"{ident} {arm} original endpoint differs from the scorer target")
        arms[arm] = dict(
            latlon=measured["endpoint_latlon"],
            rf_rms_hz=measured["residual_rms_hz"],
            associated_observations=measured["associated_points"],
            associated_tracks=measured["tracks"],
            frequency_score=measured["frequency_score"],
        )
    return dict(
        public,
        variant="original_no_repair_v5",
        cpu=control.get("cpu"),
        worker_wall_s=control["process"]["wall_seconds"],
        worker_cpu_s=control["process"].get("cpu_seconds"),
        execution_receipt=binding_receipt,
        result=dict(
            status="ok",
            boundary="Original stored native inputs to no-repair v5 scientific output",
            metrics={},
            arms=arms,
        ),
    )


def stress_secant(item, public, broad, frozen_sources):
    from .secant_full import _binding, _validate_fresh

    path = broad / "runs" / f"{item['id']}.json"
    if not path.is_file():
        return dict(
            public,
            variant="v5_secant_fit",
            worker_wall_s=None,
            result=failed_result("missing", "independent broad secant run has no saved receipt"),
        )
    plan = json.loads((broad / "plan.json").read_bytes())
    row = json.loads(path.read_bytes())
    if plan["source_sha256"] != frozen_sources or item["id"] not in plan["fresh_cases"]:
        raise ValueError("broad secant stress source differs from the historical implementation")
    _validate_fresh(row, _binding(item, _case(item)), plan)
    return dict(row, variant="v5_secant_fit", archived_run_sha256=_sha(path))


def prediction(ident, source, solver_seal, plan_path):
    expected = binding(ident)
    path = source / ident / "prediction.json"
    if not path.exists():
        return dict(
            expected,
            worker_wall_s=None,
            result=failed_result("missing", "no sealed Armijo attempt receipt"),
        )
    row = json.loads(path.read_bytes())
    if (
        any(row.get(k) != v for k, v in expected.items())
        or row["source_seal_sha256"] != _sha(solver_seal)
        or row["plan_sha256"] != _sha(plan_path)
        or row["cpu"] != CPUS[ident]
    ):
        raise ValueError("independent Armijo prediction differs from its sealed request")
    validate_result(row["result"])
    if row["result"]["status"] == "ok":
        refreshes = row["result"]["metrics"]["initial_phase_refresh_counts"]
        if not refreshes or any(count != 5 for count in refreshes):
            raise ValueError(f"{ident} changed the original initial phase refresh count")
    return row


def score(output, source, prior, solver_seal, plan_path, broad, selected=None):
    from . import projector_roof

    frozen = json.loads(plan_path.read_bytes())
    if frozen != plan(prior, solver_seal):
        raise ValueError("confirmation plan or independent archive changed")
    stock, stock_hashes = _stock_archive()
    refs = {r["id"]: r for r in projector_roof.roster() if r["id"] in CPUS}
    held = prior / "secant-confirmation"
    secant = read_predictions(held / "v5_secant_fit.jsonl.gz")
    frozen_sources = json.loads((held / "source-lock.json").read_bytes())
    archived_sources = json.loads((prior / "position-fit" / "seal.json").read_bytes())
    if frozen_sources != archived_sources["compact_source_sha256"]:
        raise ValueError("independent secant archive used different numerical sources")

    for cohort, ids in frozen["cohorts"].items():
        if selected is not None and cohort != selected:
            continue
        results, scored = {m: [] for m in ("reference", "secant", "original", "armijo")}, []
        for ident in ids:
            item, ref = _load_case(ident), refs[ident]
            public = binding(ident)
            current = prediction(ident, source, solver_seal, plan_path)
            compact = projector_roof.validate_prediction(
                stock[ident], stock_hashes, case=_case(item)
            )
            compact = dict(compact, **{k: v for k, v in public.items() if k not in compact})
            compact["variant"] = "compact-v5-bounded-gn"
            if ident in secant:
                saved = secant[ident]
                checks = {k: public[k] for k in ("input_sha256", "native_sha256", "catalog_sha256")}
                if (
                    any(saved.get(k) != v for k, v in checks.items())
                    or saved["source_sha256"] != frozen_sources
                    or saved["method"] != "v5_secant_fit"
                ):
                    raise ValueError("independent secant record differs from the frozen input")
                old_secant = dict(saved, variant="v5_secant_fit")
            else:
                old_secant = stress_secant(item, public, broad, frozen_sources)
            original = original_result(item, ref, public)
            rows = dict(reference=compact, secant=old_secant, original=original, armijo=current)
            for method, row in rows.items():
                validate_result(row["result"])
                results[method].append(row)
            paired = {
                method: compare(row, current, ref["truth"])
                for method, row in rows.items()
                if method != "armijo"
            }
            compact_metrics, current_metrics = (r["result"]["metrics"] for r in (compact, current))
            paired["reference"]["matched_inventory"] = all(
                key in current_metrics and current_metrics[key] == compact_metrics.get(key)
                for key in ("tracks", "observations", "cavity_offered", "initial_branches")
            )
            paired["original"]["matched_inventory"] = None
            scored.append(dict(id=ident, **paired))

        directory = output / cohort
        files = {}
        for method, rows in results.items():
            target = directory / f"{method}-positions.jsonl.gz"
            write(target, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
            files[target.name] = _sha(target)
        write(directory / "scores.json", json.dumps(scored, indent=2, allow_nan=False).encode())
        write(
            directory / "prediction-lock.json",
            encoded(
                dict(
                    cases=ids,
                    files=files,
                    source_seal_sha256=_sha(solver_seal),
                    confirmation_plan_sha256=_sha(plan_path),
                )
            )
            + b"\n",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, required=True)
    parser.add_argument("--solver-seal", type=Path, required=True)
    parser.add_argument("--prior", type=Path, default=PRIOR)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("plan")
    replay = actions.add_parser("run")
    replay.add_argument("case", choices=CPUS)
    replay.add_argument("--plan", type=Path, required=True)
    evaluate = actions.add_parser("score")
    evaluate.add_argument("--plan", type=Path, required=True)
    evaluate.add_argument("--source", type=Path, required=True)
    evaluate.add_argument("--broad", type=Path, required=True)
    evaluate.add_argument("--cohort", choices=("confirmation", "stress"))
    args = parser.parse_args()
    if args.action == "plan":
        save(args.out, plan(args.prior, args.solver_seal))
    elif args.action == "run":
        run(args.case, args.out, args.prior, args.solver_seal, args.plan)
    else:
        score(
            args.out, args.source, args.prior, args.solver_seal, args.plan, args.broad, args.cohort
        )


if __name__ == "__main__":
    main()
