"""Skip the second constrained rescue when the first arm has definitively failed."""

from contextlib import contextmanager
from functools import wraps
from math import isfinite
from numbers import Real
from time import process_time_ns
from unittest.mock import patch


ARMS = ("c0", "fitted_c")


def incompatible_tracks(record):
    """Only a completed constrained result can disqualify this trial."""
    if not isinstance(record, dict):
        return []
    history = record.get("history")
    scalars = (record.get("minimum_gate_slack"), record.get("final_phase_change_s"))
    if (not isinstance(history, (list, tuple)) or len(history) != 5
            or any(not isinstance(value, Real) or not isfinite(value) for value in scalars)):
        return []
    gates = record.get("gates")
    if not isinstance(gates, dict):
        return []
    groups = (
        ("conditional", gates.get("tracks")),
        ("predictive", record.get("linear_gates", ())),
    )
    if any(not isinstance(tracks, (list, tuple)) or any(
            not isinstance(track, dict) or type(track.get("compatible")) is not bool for track in tracks)
           for _, tracks in groups):
        return []
    return [
        (role, index)
        for role, tracks in groups
        for index, track in enumerate(tracks)
        if track["compatible"] is False
    ]


class IneligiblePair(Exception):
    """A completed arm failed an original mandatory residual gate."""

    def __init__(self, record, failed):
        super().__init__("Completed arm failed a required track gate")
        self.record = record
        self.failed = failed


@contextmanager
def guard(family, feasible, audit, *, first_arm="c0"):
    """Install only inside an isolated research worker with the named two-arm policy."""
    if tuple(feasible.ARMS) != ARMS:
        raise ValueError("Unknown constrained rescue order")
    if first_arm not in ARMS:
        raise ValueError("Unknown first calibration arm")
    second_arm, = (arm for arm in ARMS if arm != first_arm)
    old_constrained = family.constrained
    old_configuration = family.fit_configuration
    audit.update(first_arm=first_arm, rescues=0, second_arms_started=0, rejected_trials=[], rescue_cpu_ns=0,
                 arms={arm: dict(phase_fits_started=0, recorded_visits=0) for arm in ARMS})

    def charge_visits(records):
        for arm, record in records.items():
            history = record.get("history") if isinstance(record, dict) else None
            if isinstance(history, (list, tuple)):
                for phase in history:
                    fit = phase.get("fit") if isinstance(phase, dict) else None
                    count = fit.get("evaluations") if isinstance(fit, dict) else None
                    if type(count) is int and count >= 0:
                        audit["arms"][arm]["recorded_visits"] += count

    @wraps(old_constrained)
    def constrained(*args, **kwargs):
        # summary() returns the same dictionary that constrained() completes with
        # five phase steps and the final slack before constructing the next arm.
        old_problem, old_summary = feasible._problem, feasible.summary
        arm = None
        records = {}
        audit["rescues"] += 1

        def problem(scan, node, mask, current_arm, *values, **options):
            nonlocal arm
            if current_arm == second_arm and arm == first_arm:
                first = records.get(first_arm)
                failed = incompatible_tracks(first)
                if failed:
                    charge_visits(records)
                    raise IneligiblePair(first, failed)
                audit["second_arms_started"] += 1
            arm = current_arm
            audit["arms"][arm]["phase_fits_started"] += 1
            return old_problem(scan, node, mask, current_arm, *values, **options)

        def summary(*values, **options):
            record = old_summary(*values, **options)
            records[arm] = record
            return record

        start = process_time_ns()
        try:
            with (
                patch.object(feasible, "ARMS", (first_arm, second_arm)),
                patch.object(feasible, "_problem", problem),
                patch.object(feasible, "summary", summary),
            ):
                result = old_constrained(*args, **kwargs)
        finally:
            audit["rescue_cpu_ns"] += process_time_ns() - start
        charge_visits(records)
        return {arm: result[arm] for arm in ARMS} if set(result) == set(ARMS) else result

    @wraps(old_configuration)
    def configuration(d, node, entries, means):
        try:
            return old_configuration(d, node, entries, means)
        except IneligiblePair as veto:
            audit["rejected_trials"].append(
                {
                    "failed_tracks": veto.failed,
                    "phase_change_s": float(veto.record["final_phase_change_s"]),
                    "skipped_arm": second_arm,
                }
            )
            return {
                "paired_valid": False,
                "arms": {first_arm: veto.record},
                "node": node,
                "entries": entries,
                "means": means,
                "constrained_refinement_attempted": True,
            }

    with (
        patch.object(family, "constrained", constrained),
        patch.object(family, "fit_configuration", configuration),
    ):
        yield
