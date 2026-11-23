"""Skip the second constrained rescue when the first arm has definitively failed."""

from contextlib import contextmanager
from functools import wraps
from time import process_time_ns
from unittest.mock import patch


def incompatible_tracks(record):
    """Only a completed constrained result can disqualify this trial."""
    if len(record.get("history", ())) != 5 or "minimum_gate_slack" not in record:
        return []
    groups = (("conditional", record["gates"]["tracks"]), ("predictive", record.get("linear_gates", ())))
    return [(role, index) for role, tracks in groups for index, track in enumerate(tracks)
            if track["compatible"] is False]


class IneligiblePair(Exception):
    """A completed c0 result failed an original mandatory residual gate."""

    def __init__(self, record, failed):
        super().__init__("Completed fixed-zero arm failed a required track gate")
        self.record = record
        self.failed = failed


@contextmanager
def guard(family, feasible, audit):
    """Install only inside an isolated research worker with the named two-arm policy."""
    if tuple(feasible.ARMS) != ("c0", "fitted_c"):
        raise ValueError("Unknown constrained rescue order")
    old_constrained = family.constrained
    old_configuration = family.fit_configuration
    audit.update(rescues=0, second_arms_started=0, rejected_trials=[], rescue_cpu_ns=0)

    @wraps(old_constrained)
    def constrained(*args, **kwargs):
        # summary() returns the same dictionary that constrained() completes with
        # five phase steps and the final slack before constructing the next arm.
        old_problem, old_summary = feasible._problem, feasible.summary
        arm = None
        first = None
        audit["rescues"] += 1

        def problem(scan, node, mask, current_arm, *values, **options):
            nonlocal arm
            if current_arm == "fitted_c" and arm == "c0":
                failed = incompatible_tracks(first) if first is not None else []
                if failed:
                    raise IneligiblePair(first, failed)
                audit["second_arms_started"] += 1
            arm = current_arm
            return old_problem(scan, node, mask, current_arm, *values, **options)

        def summary(*values, **options):
            nonlocal first
            record = old_summary(*values, **options)
            if arm == "c0":
                first = record
            return record

        start = process_time_ns()
        try:
            with patch.object(feasible, "_problem", problem), patch.object(feasible, "summary", summary):
                return old_constrained(*args, **kwargs)
        finally:
            audit["rescue_cpu_ns"] += process_time_ns() - start

    @wraps(old_configuration)
    def configuration(d, node, entries, means):
        try:
            return old_configuration(d, node, entries, means)
        except IneligiblePair as veto:
            audit["rejected_trials"].append(dict(failed_tracks=veto.failed,
                                                phase_change_s=float(veto.record["final_phase_change_s"]),
                                                skipped_arm="fitted_c"))
            return dict(paired_valid=False, arms={"c0": veto.record}, node=node, entries=entries,
                        means=means, constrained_refinement_attempted=True)

    with patch.object(family, "constrained", constrained), patch.object(family, "fit_configuration", configuration):
        yield
