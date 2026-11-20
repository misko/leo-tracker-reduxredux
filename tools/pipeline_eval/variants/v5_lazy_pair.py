"""Demand the second predictive-linear fit only when the frozen gate reads it."""

import sys
from collections.abc import Mapping
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_lean

METHOD = "v5_lazy_pair"


def _cpu():
    children = getrusage(RUSAGE_CHILDREN)
    return process_time() + children.ru_utime + children.ru_stime


class _FittedArm(Mapping):
    """Private mapping used during the original ordered conjunction only."""

    def __init__(self, fit):
        self.fit = fit
        self.value = None
        self.gate_read = False

    def evaluate(self):
        if self.value is None:
            self.value = self.fit()
        return self.value

    def __getitem__(self, key):
        self.gate_read = True
        return self.evaluate()[key]

    def __iter__(self):
        return iter(self.evaluate())

    def __len__(self):
        return len(self.evaluate())


@contextmanager
def predictive_pair(module, *, eager=False):
    """Instrument the frozen compact history call with its default ordered mapper."""
    original = module.history_policy
    refit = module.linear_refit
    receipts = []

    def policy(*args, **kwargs):
        if kwargs.get("map_arms") is not None:
            raise ValueError("the compact predictive shortcut requires the original ordered map")
        calls = {arm: [] for arm in module.ARMS}

        def measure(arm, operation):
            wall, cpu = perf_counter(), _cpu()
            value = operation()
            calls[arm].append(
                dict(
                    wall_s=perf_counter() - wall,
                    cpu_s=_cpu() - cpu,
                    rounds=len(value["history"]),
                    phase_change_s=value["final_phase_change_s"],
                )
            )
            return value

        def linear_refit(scan, node, keep, powers, means, model, arm, entries):
            operation = partial(refit, scan, node, keep, powers, means, model, arm, entries)
            if arm == "c0":
                return measure(arm, operation)
            fitted = _FittedArm(partial(measure, arm, operation))
            if eager:
                fitted.evaluate()
            return fitted

        with patch.object(module, "linear_refit", linear_refit):
            outcome = original(*args, **kwargs)
        linear = outcome.get("linear_arms")
        if linear is None:
            return outcome
        fitted = linear["fitted_c"]
        if not isinstance(fitted, _FittedArm) or len(calls["c0"]) != 1:
            raise ValueError("unexpected predictive history call contract")
        accepted = outcome["linear_paired_valid"]
        if fitted.value is None:
            if accepted or fitted.gate_read or outcome["policy_arms"] is not outcome["curved_arms"]:
                raise ValueError("uncomputed predictive arm reached the selected policy")
            del linear["fitted_c"]
        else:
            linear["fitted_c"] = fitted.value
        receipts.append(
            dict(
                c0_passed=fitted.gate_read,
                pair_accepted=accepted,
                fallback=outcome["fallback"],
                fitted_diagnostic="evaluated"
                if fitted.value is not None
                else "omitted_after_c0_failure",
                calls=calls,
                linear_offered_tracks=outcome["linear_offered_tracks"],
                linear_offered_points=outcome["linear_offered_points"],
                linear_used_points=outcome["linear_used_points"],
                mask_sha256=sha256(outcome["mask"].tobytes()).hexdigest(),
                original_mask_sha256=sha256(outcome["original_mask"].tobytes()).hexdigest(),
                weights_sha256=sha256(outcome["weights"].tobytes()).hexdigest(),
                phase_prior=outcome["hyperparameters_from_pre_RF_TLE_only"],
                policy_endpoints={
                    arm: list(value["endpoint_latlon"])
                    for arm, value in outcome["policy_arms"].items()
                },
            )
        )
        return outcome

    with patch.object(module, "history_policy", policy):
        yield receipts


def worker(request, target, library, mode):
    from leo.analysis.localization_v3 import history_policy

    from tools.pipeline_eval.__main__ import save_json

    if mode not in ("eager", "lazy"):
        raise ValueError("expected an eager or lazy predictive policy")
    with predictive_pair(history_policy, eager=mode == "eager") as evidence:
        compact_finish.worker(request, target, library)
    result = v5_lean._read(target)
    if result["status"] == "ok" and len(evidence) != 1:
        raise ValueError("a compact publication needs exactly one measured predictive decision")
    result["metrics"]["predictive_pair"] = evidence
    save_json(Path(target), result)


def run(case, work_dir, *, eager=False):
    from tools.pipeline_eval.__main__ import local_output

    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(
        case, work_dir, Path(__file__), worker_args=(str(library), "eager" if eager else "lazy")
    )


if __name__ == "__main__":
    worker(*sys.argv[1:])
