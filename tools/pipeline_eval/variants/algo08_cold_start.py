"""Reuse the exact initial centre residual and audit fixed-zero overlap."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import wraps
from hashlib import sha256
from inspect import getsource
import pickle
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import conservative_recovery, marginal, position
from tools.pipeline_eval.variants import v5_core, v5_direct_cavity
from tools.pipeline_eval.variants.v5_likelihood_reuse import exact_value

SNAPSHOT_LIMIT = 8 * 1024**2
ARRAYS = (
    "reference", "phase_sigma", "keep", "point_noise", "flat_times", "flat_labels",
    "values", "q", "noise_groups", "hardware", "smooth", "constants",
)
BANK_ARRAYS = ("time_s", "position_km", "velocity_km_s")
CENTRE = bytes(2 * np.dtype(np.float64).itemsize)


def at_centre(point):
    coordinates = np.asarray(point, dtype=np.float64)
    return coordinates.shape == (2,) and coordinates.tobytes() == CENTRE


def cold_model_key(problem):
    """Bind the complete fixed-input normal residual rather than its owner labels alone."""
    scan = problem.scan
    arrays = [np.asarray(getattr(problem, name)) for name in ARRAYS]
    arrays.extend(getattr(problem, bank)[field]
                  for bank in ("sky", "mode_bank") for field in BANK_ARRAYS)
    if sum(array.nbytes for array in arrays) > SNAPSHOT_LIMIT:
        return None
    config = (
        scan.search_region, scan.origin_utc_ns, scan.previous_tle_sha256, scan.previous_tle,
        tuple(problem.members), tuple(problem.labels), tuple(problem.supported),
        tuple(problem.supported_local), tuple(problem.alias), problem.fitted_c,
        exact_value(problem.sigma), exact_value(problem.noise_volume), problem.variant,
    )
    data = tuple((array.strides, exact_value(array)) for array in arrays)
    return scan, scan.bound, config, data


def native_key(arguments, keywords):
    values = tuple(map(exact_value, arguments))
    options = tuple((key, exact_value(value)) for key, value in sorted(keywords.items()))
    return sha256(pickle.dumps((values, options), protocol=5)).hexdigest()


class ColdStarts:
    def __init__(self, enabled):
        self.enabled = enabled
        self.stage = None
        self.rank = []
        self.counts = Counter()
        self.zero_calls = []

    def record(self, model):
        clock = process_time_ns()
        value = model.residual(np.zeros(2))
        self.counts["cold_score_ns"] += process_time_ns() - clock
        self.counts["cold_scores"] += 1
        if not self.enabled:
            return value
        score = float(value @ value)
        if len(self.rank) < 3 or score < self.rank[-1][0]:
            clock = process_time_ns()
            key = cold_model_key(model)
            if key is not None:
                self.rank.append((score, key, value.copy()))
                self.rank.sort(key=lambda item: item[0])
                del self.rank[3:]
                self.counts["snapshot_ns"] += process_time_ns() - clock
            else:
                self.counts["snapshot_fallbacks"] += 1
        return value

    def ranking(self, original):
        source = getsource(original)
        anchor = "residual = model.residual(np.zeros(2))"
        if source.count(anchor) != 1:
            raise ValueError("Unexpected cold score in the release ranking")
        namespace = dict(vars(v5_core), record_cold=self.record)
        code = source.replace(anchor, "residual = record_cold(model)")
        exec(compile(code, original.__code__.co_filename, "exec"), namespace)
        return self.in_stage("initial_rank", namespace[original.__name__])

    def in_stage(self, name, operation):
        @wraps(operation)
        def run(*args, **kwargs):
            previous, self.stage = self.stage, name
            try:
                return operation(*args, **kwargs)
            finally:
                if name == "initial_refit":
                    self.rank.clear()
                self.stage = previous
        return run

    def calculate(self, original, model, point):
        if self.stage is None or not at_centre(point) or np.any(model.reference):
            return original(model, point)
        operation = model.scan.bound

        def audited(*args, **kwargs):
            # Use a separate digest for the complete numeric call. This can expose
            # unexpected overlap without allowing reuse across causal scan contexts.
            clock = process_time_ns()
            digest = native_key(args, kwargs)
            self.zero_calls.append(dict(
                stage=self.stage, native_input=digest,
                previous_tle_sha256=model.scan.previous_tle_sha256,
                reference=sha256(model.reference.tobytes()).hexdigest(),
                phase_width=sha256(model.phase_sigma.tobytes()).hexdigest(),
                active_points=int(model.keep.sum()), fitted=bool(model.fitted_c),
            ))
            self.counts[f"{self.stage}_audit_ns"] += process_time_ns() - clock
            return operation(*args, **kwargs)

        with patch.object(model.scan, "bound", audited):
            return original(model, point)

    def optimize(self, original, residual, start, lower, upper, **kwargs):
        model = getattr(residual, "__self__", None)
        if (
            not self.enabled or self.stage != "initial_refit"
            or type(model) is not position.NormalPosition or np.any(model.reference)
            or not at_centre(start)
        ):
            return original(residual, start, lower, upper, **kwargs)
        clock = process_time_ns()
        key = cold_model_key(model)
        self.counts["lookup_ns"] += process_time_ns() - clock
        for _, prior, saved in self.rank:
            if (key is not None and key[0] is prior[0] and key[1] is prior[1]
                    and key[2:] == prior[2:]):
                break
        else:
            self.counts["start_misses"] += 1
            return original(residual, start, lower, upper, **kwargs)
        first = True

        def initial(point):
            nonlocal first
            if first:
                first = False
                if at_centre(point):
                    self.counts["start_hits"] += 1
                    return saved.copy()
            return residual(point)

        return original(initial, start, lower, upper, **kwargs)


@contextmanager
def measured_cold_start(*, enabled):
    audit = ColdStarts(enabled)
    optimize, calculate = v5_direct_cavity.bounded_secant, position.NormalPosition.calculate
    layout = marginal.AnchoredFamilies
    initialize = position.NormalPosition.__init__

    def measured_constructor(model, *args, **kwargs):
        stage = audit.stage
        start = process_time_ns()
        initialize(model, *args, **kwargs)
        if stage is not None:
            audit.counts[f"{stage}_model_ns"] += process_time_ns() - start

    def measured_layout(*args, **kwargs):
        stage = audit.stage
        start = process_time_ns()
        result = layout(*args, **kwargs)
        if stage is not None:
            audit.counts[f"{stage}_constructs"] += 1
            audit.counts[f"{stage}_layout_ns"] += process_time_ns() - start
        return result

    with ExitStack() as stack:
        for module, name, replacement in (
            (marginal, "AnchoredFamilies", measured_layout),
            (position.NormalPosition, "__init__", measured_constructor),
            (position.NormalPosition, "calculate",
             lambda model, point: audit.calculate(calculate, model, point)),
            (v5_direct_cavity, "bounded_secant",
             lambda residual, start, lower, upper, **kw:
             audit.optimize(optimize, residual, start, lower, upper, **kw)),
            (v5_core, "ranked_initial_nodes", audit.ranking(v5_core.ranked_initial_nodes)),
            (v5_core, "fit_initial_nodes",
             audit.in_stage("initial_refit", v5_core.fit_initial_nodes)),
            (conservative_recovery, "repaired_fit",
             audit.in_stage("recovery_unit", conservative_recovery.repaired_fit)),
            (conservative_recovery, "causal_fit",
             audit.in_stage("recovery_causal", conservative_recovery.causal_fit)),
        ):
            stack.enter_context(patch.object(module, name, replacement))
        yield audit
