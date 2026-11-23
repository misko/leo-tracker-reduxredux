"""Measure exact reusable operands in the installed two-arm curved grid posterior."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np


PINNED_BOUND = "fa7b67e0e539be9971ee1a530c2d1d941c7940701d40dae7cc6744cbc20de6a2"
PINNED_HANDOFF = "aa5d7ab17ce82e4bd64e463de0fddf710275634cf48675cf6076eeba6c184831"
FITTED_COLUMN = 8
FIXED_INPUTS = ("s", "g", "power", "counts", "alpha", "pa", "dimensions", "alpha0", "beta0", "pa0", "pb0", "v0", "iterations")


def same_bits(left, right):
    a, b = np.asarray(left), np.asarray(right)
    if a.shape != b.shape or a.dtype != b.dtype:
        raise ValueError("Incompatible aligned inputs in the original calibration pair")
    item = f"u{a.dtype.itemsize}"
    return a.view(item) == b.view(item)


def compare_inputs(zero, fitted):
    """Compare exact operands, without changing products or factorization order."""
    x, fitted_x = zero["u"], fitted["u"]
    z = np.delete(fitted_x, FITTED_COLUMN, axis=1)
    flags = {name: bool(same_bits(zero[name], fitted[name]).all()) for name in FIXED_INPUTS}
    if not flags["g"]:
        raise ValueError("Expected aligned noise groups on the selected common curved support")
    same_response = same_bits(zero["y"], fitted["y"])
    same_scale = same_bits(zero["s"], fitted["s"])
    same_design = same_bits(x, z)
    same_normalized_design = same_design & same_scale[:, None]
    same_normalized_response = same_response & same_scale
    g = zero["g"]
    order = np.argsort(g, kind="stable")
    offsets = np.r_[0, np.cumsum(zero["counts"])[:-1]]
    if not np.array_equal(g[order][offsets], np.arange(len(offsets))):
        raise ValueError("Expected nonempty, ordered noise group IDs")
    grouped_active = np.logical_or.reduceat(fitted_x[order] != 0., offsets, axis=0)
    active_common = np.delete(grouped_active, FITTED_COLUMN, axis=1)
    local_match = np.logical_and.reduceat(same_normalized_design[order], offsets, axis=0)
    response_groups = np.logical_and.reduceat(same_normalized_response[order], offsets)
    shared = (local_match & active_common).sum(axis=1)
    fitted_active = grouped_active.sum(axis=1)
    c = fitted_x[:, FITTED_COLUMN]
    # A nonzero group intercept–c product already couples this new parameter to the common block.
    intercept_cross = np.add.reduceat((fitted_x[:, :4] / fitted["s"][:, None] * (c/fitted["s"])[:, None])[order],
                                      offsets, axis=0)
    precision_matches = same_bits(zero["noise_precision"], fitted["noise_precision"])
    common_prior = same_bits(zero["prior"], np.delete(fitted["prior"], FITTED_COLUMN)).all()
    common_coefficient = same_bits(zero["coefficient"], np.delete(fitted["coefficient"], FITTED_COLUMN))
    coupled = np.any(intercept_cross != 0., axis=1)
    return dict(rows=len(g), groups=len(offsets), widths=[x.shape[1], fitted_x.shape[1]], fixed_inputs=flags,
                equal_response_rows=int(same_response.sum()), equal_full_common_design_rows=int(same_design.all(axis=1).sum()),
                equal_common_design_columns=int(same_design.all(axis=0).sum()),
                equal_common_design_cells=int(same_design.sum()), common_design_cells=x.size,
                equal_nonzero_common_design_cells=int((same_design & (x != 0.)).sum()),
                equal_prior_indices=bool(common_prior), active_fitted_column_rows=int(np.count_nonzero(c)),
                coupled_noise_groups=int(coupled.sum()), equal_precision_slots=int(precision_matches.sum()),
                equal_precision_vectors=int(precision_matches.all()), equal_common_coefficients=int(common_coefficient.sum()),
                eligible_common_gram_entries=int(shared @ shared), total_fitted_gram_entries=int(fitted_active @ fitted_active),
                eligible_common_rhs_entries=int(shared @ response_groups.astype(int)), total_fitted_rhs_entries=int(fitted_active.sum()),
                groups_with_every_common_column_equal=int(np.all(local_match | ~active_common, axis=1).sum()),
                groups_with_all_response_equal=int(response_groups.sum()),
                full_posterior_reusable=False)


def compare_models(zero, fitted):
    assignments = lambda p: [(r["component"], r["candidate_index"], r["candidate_norad"]) for r in p.rows]
    same_support = (assignments(zero) == assignments(fitted) and list(zero.alias) == list(fitted.alias)
                    and list(zero.labels) == list(fitted.labels) and list(zero.supported) == list(fitted.supported)
                    and bool(same_bits(zero.keep, fitted.keep).all())
                    and bool(same_bits(zero.flat_times, fitted.flat_times).all())
                    and bool(same_bits(zero.flat_labels, fitted.flat_labels).all()))
    if not same_support or (zero.hardware.shape[1], fitted.hardware.shape[1]) != (8, 9):
        raise ValueError("Expected common selected support and exactly one additional fitted RF column")
    phase0, phase1 = zero.reference, fitted.reference
    equal = same_bits(phase0, phase1)
    return dict(same_support=True, full_curved_rows=len(zero.keep), selected_rows=int(zero.keep.sum()),
                phase_references=len(equal), equal_phase_references=int(equal.sum()),
                equal_retained_reference_rows=int(equal[zero.flat_labels[zero.keep]].sum()),
                maximum_phase_reference_difference_s=float(np.max(np.abs(phase1-phase0))))


def ceiling(paired, unmatched):
    """Grant one entire counterpart per point even where no operands match."""
    def price(domain):
        paired_ns = sum(max(row["clocks"][arm][domain] for arm in ("c0", "fitted_c")) for row in paired)
        unmatched_ns = sum(row["clock"][domain] for row in unmatched)
        return dict(granted_peer_cpu_s=paired_ns/1e9, endpoint_only_cpu_s=unmatched_ns/1e9,
                    both_arms_cpu_s=(sum(sum(arms[domain] for arms in row["clocks"].values()) for row in paired)+unmatched_ns)/1e9)

    return {domain: price(domain) for domain in ("curved", "bound", "native", "validation")}


class Audit:
    def __init__(self):
        self.current = None
        self.handoff = None
        self.model = {}
        self.pairs = []
        self.unmatched = []
        self.pending = None

    @contextmanager
    def count_handoff(self, original, *args, **kwargs):
        with original(*args, **kwargs) as counts:
            self.handoff = counts
            yield counts

    def capture(self, original):
        def run(owner, *args):
            start = process_time_ns()
            result = original(owner, *args)
            self.current["clock"]["native"] = process_time_ns()-start
            self.current["export_width"] = owner.width
            self.current["exported"] = owner.exported.value
            return result

        return run

    def validation(self, original):
        def validate(*args, **kwargs):
            start = process_time_ns()
            data = original(*args, **kwargs)
            self.current["clock"]["validation"] = process_time_ns()-start
            self.current["input"] = data
            return data

        return validate

    def bound(self, original):
        def run(owner, *args, **kwargs):
            start = process_time_ns()
            result = original(owner, *args, **kwargs)
            self.current["clock"]["bound"] = process_time_ns()-start
            self.current["input"].update({key: result[key].copy() for key in ("noise_precision", "coefficient")})
            self.current["precision_iterations"] = result["precision_iterations"]
            return result

        return run

    def objective(self, original):
        def calculate(problem, context, position):
            arm = self.current["arm"]
            if arm not in self.model:
                self.model[arm] = problem
            return original(problem, context, position)

        return calculate

    def finish_point(self):
        current = self.current
        if current["arm"] == "c0":
            self.pending = current
            return
        zero, self.pending = self.pending, None
        if zero["point"] != current["point"]:
            raise ValueError("Expected adjacent same-coordinate calibration arms")
        fresh = [row for row in (zero, current) if "input" in row]
        for row in fresh:
            if (row["exported"] != 1 or row["export_width"] != row["input"]["width"]
                    or set(row["clock"]) != {"curved", "bound", "native", "validation"}):
                raise ValueError("Expected one checked original native export per fresh curved arm")
        if len(fresh) != 2:
            for row in fresh:
                self.unmatched.append({key: value for key, value in row.items() if key != "input"})
            return
        self.pairs.append(dict(point=current["point"], clocks={row["arm"]: row["clock"] for row in fresh},
                               updates={row["arm"]: row["precision_iterations"] for row in fresh},
                               operands=compare_inputs(zero["input"], current["input"])))

    def grid(self, sample):
        from leo.analysis.localization_v4 import native_bound
        from leo.presentation import localization_v3 as presentation
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

        if any(sha256(Path(module.__file__).read_bytes()).hexdigest() != pin for module, pin in (
                (native_bound, PINNED_BOUND), (handoff, PINNED_HANDOFF))):
            raise ValueError("Unexpected release source for posterior input and clock capture")

        def grid(score, endpoints, **kwargs):
            def observe(arm, point):
                self.current = dict(arm=arm, point=tuple(point), clock={})
                before = self.handoff["curved_cpu_ns"]
                value = score(arm, point)
                used = self.handoff["curved_cpu_ns"]-before
                if used:
                    self.current["clock"]["curved"] = used
                self.finish_point()
                self.current = None
                return value

            with ExitStack() as scope:
                scope.enter_context(patch.object(handoff.Capture, "run", self.capture(handoff.Capture.run)))
                scope.enter_context(patch.object(native_bound, "_VALIDATE", self.validation(native_bound._VALIDATE)))
                scope.enter_context(patch.object(native_bound.NativeBound, "__call__", self.bound(native_bound.NativeBound.__call__)))
                scope.enter_context(patch.object(presentation, "objective", self.objective(presentation.objective)))
                return sample(observe, endpoints, **kwargs)

        return grid

    def records(self):
        coverage = Counter(row["arm"] for row in self.unmatched)
        if len(self.pairs) != 177 or coverage != {"c0": 1, "fitted_c": 1}:
            raise ValueError("Expected the complete original paired grid and two asymmetric cached endpoints")
        return dict(ceiling=ceiling(self.pairs, self.unmatched),
                    model=compare_models(self.model["c0"], self.model["fitted_c"]), pairs=self.pairs,
                    unmatched_endpoints=self.unmatched)
