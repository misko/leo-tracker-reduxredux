"""Retry one failed final reassociation after binding its missing phase initializer."""

import argparse
import json
import os
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.qualification import armijo_finish_trial as trial
from tools.pipeline_eval.qualification.broad_search_budget import _case
from tools.pipeline_eval.qualification.full_v5_check import _load_case, _sha
from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, stamp
from tools.pipeline_eval.scoring import validate_result
from tools.pipeline_eval.variants import orbit_projector, v5_armijo_finish, v5_lean

CASE = "DS26-0066"
CPU = 1
LOCK = trial.REPORT / "phase-retry-lock.json"
METHOD = "v5_armijo_finish_phase_seed"


def prepare_remap(context, before, adopted):
    scan = context["scan"]
    catalogue = tuple(map(int, scan.norads))
    node = context["node"]
    seed = node["seed"]
    state = seed["state"]
    phases = np.asarray(state["phases"])
    if phases.ndim == 1 and len(phases) == len(catalogue):
        return context, None
    if (
        before is None
        or adopted in before
        or catalogue != (*before, adopted)
        or phases.shape != (len(before),)
        or not np.isfinite(phases).all()
        or len(before) != len(set(before))
        or any(
            not 0 <= row["candidate_index"] < len(before)
            or before[row["candidate_index"]] != row["candidate_norad"]
            for row in seed["rows"]
        )
    ):
        raise ValueError("short phase initializer has no exact adopted catalogue-slot authority")
    # The frozen remapper uses zero to initialize an appended lane. The selected
    # posterior references and causal prior arrays already have their own bindings.
    extended = dict(state, phases=np.r_[phases, 0.0])
    adapted = dict(context, node=dict(node, seed=dict(seed, state=extended)))
    receipt = dict(
        original_catalogue_order=list(before),
        added_norad=adopted,
        added_catalogue_index=len(before),
        old_phase_initial_seconds=phases.tolist(),
        added_phase_initial_seconds=0.0,
        prior_mean_seconds=np.asarray(context["means"]).tolist(),
        reference_seconds={
            a: np.asarray(p.reference).tolist() for a, (p, _) in context["problems"].items()
        },
        retained_label_indices={
            a: list(map(int, p.labels)) for a, (p, _) in context["problems"].items()
        },
    )
    return adapted, receipt


def worker(request, target, library):
    from leo.analysis.localization_v3 import reassociation_context, reassociation_recovery

    add = reassociation_context.add_target
    remap = reassociation_recovery.remap
    adopted, receipts = {}, []
    receipt_path = Path(target).with_name("phase-shape.json")

    def capture_addition(context, *args, **kwargs):
        before = tuple(map(int, context["scan"].norads))
        entry = add(context, *args, **kwargs)
        after = tuple(map(int, context["scan"].norads))
        if before != after:
            number = int(entry["norad"])
            if after != (*before, number) or entry["candidate_index"] != len(before):
                raise ValueError("adoption changed an existing ordered sky identity")
            adopted.update(before=before, number=number)
        return entry

    def aligned_remap(context, hypothesis, ledger):
        adapted, receipt = prepare_remap(context, adopted.get("before"), adopted.get("number"))
        if receipt is not None:
            receipt["hypothesis"] = hypothesis["name"]
            receipt["mapping"] = {key: int(number) for key, number in hypothesis["mapping"].items()}
            receipts.append(receipt)
            save_json(receipt_path, receipts)
        return remap(adapted, hypothesis, ledger)

    with (
        patch.object(reassociation_context, "add_target", capture_addition),
        patch.object(reassociation_recovery, "remap", aligned_remap),
    ):
        v5_armijo_finish.worker(request, target, library)
    result = json.loads(Path(target).read_bytes())
    if result["status"] == "ok" and not receipts:
        raise ValueError("retry did not exercise the recorded missing phase slot")
    result["metrics"]["verified_phase_slot_repairs"] = len(receipts)
    save_json(Path(target), result)


def source_lock(prior):
    first = json.loads(prior.read_bytes())
    if (
        first["id"] != CASE
        or first["method"] != trial.METHOD
        or first["source_lock_sha256"] != _sha(trial.SEAL)
        or "out of bounds for axis 0" not in first["result"].get("reason", "")
    ):
        raise ValueError("retry requires the recorded ordered-phase worker failure")
    return dict(
        case=trial.public_binding(CASE),
        cpu=CPU,
        case_limit_s=trial.CASE_LIMIT_S,
        retry_source_sha256=_sha(Path(__file__)),
        primary_source_lock_sha256=_sha(trial.SEAL),
        failed_worker_receipt_sha256=_sha(prior),
        failed_worker_log_sha256=_sha(prior.parent / "position/worker.log"),
    )


def run(prior, output):
    locked = json.loads(LOCK.read_bytes())
    if (
        locked != source_lock(prior)
        or json.loads(trial.SEAL.read_bytes()) != trial.source_lock()
        or os.sched_getaffinity(0) != {CPU}
    ):
        raise ValueError("phase retry differs from its sealed input, source or affinity")
    path = local_output(output)
    path.mkdir(parents=True, exist_ok=False)
    library = path / "orbit_projector.so"
    case = _case(_load_case(CASE))
    wall, cpu = perf_counter(), cpu_s()
    orbit_projector.compile_kernel(library)
    timeout = v5_lean.TIMEOUT_S
    try:
        v5_lean.TIMEOUT_S = trial.CASE_LIMIT_S - 4
        result = v5_lean.run_bound_worker(case, path, Path(__file__), worker_args=(str(library),))
    finally:
        v5_lean.TIMEOUT_S = timeout
    duration = stamp(wall, cpu)
    if "exceeded its " in result.get("reason", ""):
        result["status"] = "timed_out"
    result["boundary"] = v5_armijo_finish.BOUNDARY + " with ordered phase seed alignment"
    validate_result(result)
    if locked != source_lock(prior):
        raise ValueError("retry source or original failure changed during computation")
    sidecar = path / "phase-shape.json"
    save_json(
        path / "prediction.json",
        dict(
            trial.public_binding(CASE),
            method=METHOD,
            cpu=CPU,
            worker_wall_s=duration["wall_s"],
            worker_cpu_s=duration["cpu_s"],
            resources=duration,
            retry_lock_sha256=_sha(LOCK),
            phase_shape_sha256=_sha(sidecar) if sidecar.is_file() else None,
            result=result,
        ),
    )
    print(CASE, METHOD, result["status"], round(duration["wall_s"], 3), flush=True)


def main():
    if len(sys.argv) == 4 and sys.argv[1] not in ("lock", "run"):
        worker(*sys.argv[1:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("lock", "run"))
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.action == "lock":
        if LOCK.exists():
            raise ValueError("phase retry lock already exists")
        save_json(LOCK, source_lock(args.prior))
    else:
        run(args.prior, args.out)


if __name__ == "__main__":
    main()
