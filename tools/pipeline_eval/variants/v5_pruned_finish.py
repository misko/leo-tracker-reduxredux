"""Check necessary evidence before the two expensive final compact-v5 searches."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_armijo_aligned_finish, v5_lean

METHOD = "v5_pruned_finish"
BOUNDARY = "Native GLRT to aligned Armijo v5 final selection with eligibility before fitting"
POLICY = "72h_30s"


def target_reason(times, families, partitions):
    if families == 2:
        return "two_existing_families"
    t = np.asarray(times)
    if t.ndim != 1 or len(t) == 0 or not np.isfinite(t).all():
        return None
    for train, held, _ in partitions(t):
        if train.sum() < 8 or held.sum() < 4:
            return "required_time_fold_unavailable"
    return None


def check_causal_ledger(catalogue, packet):
    """The geometry can be skipped. Its input still needs the original causal bounds."""
    cutoff = packet["scan_receipt"]["cutoff_utc_ns"]
    if cutoff != catalogue["cutoff_utc_ns"]:
        raise ValueError("causal catalogue cutoff differs from the scan")
    for record in catalogue["elements"].values():
        for key in ("element_epoch_utc_ns", "collected_utc_ns"):
            if not 0 <= cutoff - record[key] <= 72 * 3_600_000_000_000:
                raise ValueError("causal catalogue entry falls outside its 72-hour interval")


def residual_targets(packet, catalogue, region, original, partitions, metrics):
    targets = packet["targets"]
    reasons = [
        target_reason(t["times_s"], packet["incumbent_family_count"], partitions) for t in targets
    ]
    required = [t for t, reason in zip(targets, reasons, strict=True) if reason is None]
    metrics.update(
        offered=len(targets),
        evaluated=len(required),
        reasons=reasons,
        propagated_residual_catalogue=bool(required),
    )
    if required:
        result = original(dict(packet, targets=required), catalogue, region)
    else:
        check_causal_ledger(catalogue, packet)
        result = dict(case=packet["case"], targets=[])
    evaluated = iter(result["targets"])
    restored = []
    for target, reason in zip(targets, reasons, strict=True):
        if reason is None:
            restored.append(next(evaluated))
        else:
            restored.append(
                dict(
                    source=target["source"],
                    eligibility=reason,
                    summaries=[dict(policy=POLICY, screen_pass=False)],
                )
            )
    if next(evaluated, None) is not None:
        raise ValueError("unexpected residual target in the numerical screen")
    return dict(result, targets=restored)


def support(problem):
    counts = {}
    for row, sl in zip(problem.rows, problem.slices, strict=True):
        points = int(problem.keep[sl].sum())
        if points:
            count = counts.setdefault(row["candidate_norad"], [0, 0])
            count[0] += points
            count[1] += 1
    return counts


def rank_eligible(context, original, metrics):
    support_by_arm = {}
    first = {}
    for arm, (problem, _) in context["problems"].items():
        counts = support_by_arm[arm] = support(problem)
        for norad, count in counts.items():
            # Stock persists the first observed arm's support via rows.setdefault.
            first.setdefault(norad, count)
    scores = {n: 0.0 for n, (points, tracks) in first.items() if points >= 30 and tracks >= 2}
    full_pairs = sum(map(len, support_by_arm.values()))
    evaluated = 0
    directions = np.eye(2) * 0.05
    for arm, (problem, x) in context["problems"].items():
        eligible = sorted(scores.keys() & support_by_arm[arm].keys())
        if not eligible:
            continue
        gradient, hessian = original.derivatives(
            lambda v, problem=problem: original.objective(problem, context, v), x
        )
        inverse = np.linalg.pinv(hessian)
        for norad in eligible:
            reduced, omitted = original.build(context, arm, problem.reference, omit=norad)
            reduced_gradient = np.array(
                [
                    (
                        original.objective(reduced, omitted, x + v)
                        - original.objective(reduced, omitted, x - v)
                    )
                    / 0.1
                    for v in directions
                ]
            )
            scores[norad] += float(np.linalg.norm(inverse @ (reduced_gradient - gradient)))
            evaluated += 1
    rows = [
        dict(norad=n, rank_score=scores[n], points=first[n][0], tracks=first[n][1])
        for n in sorted(scores, key=lambda n: (-scores[n], n))
    ]
    selected = [r["norad"] for r in rows if r["rank_score"] >= 0.5][:2]
    metrics.update(
        observed_families=len(first),
        eligible_families=len(scores),
        original_arm_omissions=full_pairs,
        evaluated_arm_omissions=evaluated,
        evaluated_scores=rows,
        selected=selected,
    )
    return rows, selected


def worker(request, target, library):
    from leo.analysis.localization_v3 import (
        reassociation_context,
        residual_preflight,
        residual_screen,
    )

    preflight = residual_preflight.preflight
    screen = residual_screen.screen_candidates
    measured = dict(residual={}, influence={})

    def with_family_count(context, *args, **kwargs):
        packet = preflight(context, *args, **kwargs)
        return dict(packet, incumbent_family_count=len(context["families"]))

    def filtered(packet, catalogue, region, *, policy=POLICY, on_target=None):
        if policy != POLICY or on_target is not None or "incumbent_family_count" not in packet:
            return screen(packet, catalogue, region, policy=policy, on_target=on_target)

        def partitions(t):
            return (residual_screen.split(t, seed) for seed in residual_screen.SEEDS)

        return residual_targets(packet, catalogue, region, screen, partitions, measured["residual"])

    def ranked(context):
        return rank_eligible(context, reassociation_context, measured["influence"])

    with (
        patch.object(residual_preflight, "preflight", with_family_count),
        patch.object(residual_screen, "screen_candidates", filtered),
        patch.object(reassociation_context, "rank_families", ranked),
    ):
        v5_armijo_aligned_finish.worker(request, target, library)
    result = json.loads(Path(target).read_bytes())
    if result["status"] == "ok" and not all(measured.values()):
        raise ValueError("missing eligibility observations for a complete finish")
    result["boundary"] = BOUNDARY
    result["metrics"]["finish_eligibility"] = measured
    save_json(Path(target), result)


def run(case, work_dir):
    folder = local_output(work_dir)
    folder.mkdir(parents=True, exist_ok=True)
    library = folder / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, folder, Path(__file__), worker_args=(str(library),))
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
