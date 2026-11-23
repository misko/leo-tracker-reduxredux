"""Keep released phase-transition arithmetic with a scan-local Julian split."""

from contextlib import contextmanager
from functools import lru_cache
from hashlib import sha256
from inspect import getclosurevars
from math import isfinite
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np


PHASE_SHA = "4659c0f6a49dbc3ae8e7f65272d2db9567dd67e6908fcb10c36bf0324decd6dd"
TABLE_MODULE = "tools.pipeline_eval.variants.algo08_causal_table"
TABLE_SHA = "66a63fd9c2fd0710dc872973ce820bb869bcc1d235f2fc2fa054b0bfdf2e0f46"


class UnreviewedTransition(ValueError):
    """The stock binding is outside this exact replacement's review."""


def checked_table_wrapper(operation, stock):
    """Recognize the installed causal table timing wrapper around the original."""
    module = sys.modules.get(TABLE_MODULE)
    source = getattr(module, "__file__", None)
    code = getattr(operation, "__code__", None)
    if (not source or code is None or code.co_filename != source or code.co_qualname != "timed.<locals>.measure"
            or getattr(operation, "__wrapped__", None) is not stock
            or getclosurevars(operation).nonlocals.get("operation") is not stock):
        return False
    try:
        return sha256(Path(source).read_bytes()).hexdigest() == TABLE_SHA
    except OSError:
        return False


def causal_sigma(alignment, age, gap):
    if not (isfinite(alignment) and isfinite(age) and isfinite(gap)) or age < 0 or gap <= 0:
        raise ValueError("finite causal ages and strictly ordered epochs required")
    return float(min(15., max(1., np.hypot(1., alignment * age / gap))))


def transition_port(module):
    @lru_cache(maxsize=256)
    def split(target):
        day, fraction = module.julian_day_from_utc_ns(np.array([target]))
        return float(day[0]), float(fraction[0])

    def transition(a, b, c):
        target = c["collected_utc_ns"]
        if not (
            a["collected_utc_ns"] <= b["collected_utc_ns"] <= target
            and a["epoch"] < b["epoch"] < c["epoch"] <= target
        ):
            return None
        gap = (b["epoch"] - a["epoch"]) / 1e9
        if gap < 1:
            return None
        day, fraction = split(target)
        # Preserve the original fresh scalar Satrec state for each propagation.
        states = [module.Satrec.twoline2rv(*row["lines"]).sgp4(day, fraction)
                  for row in (a, b, c)]
        if states[0][0] or states[1][0] or states[2][0]:
            return None
        pa, pb, pc = [np.asarray(state[1]) for state in states]
        velocity = np.asarray(states[1][2])
        norm = float(velocity @ velocity)
        alignment = float((pa - pb) @ velocity / norm)
        innovation = float((pc - pb) @ velocity / norm)
        age = (target - b["epoch"]) / 1e9
        # The causal ordering above guarantees a positive age and gap.
        return dict(
            validation_time_ns=target,
            old_middle_alignment_s=alignment,
            next_innovation_s=innovation,
            unit_forecast_s=-min(age / gap, 2.) * alignment,
            age_s=age,
            epoch_gap_s=gap,
            predicted_sigma_s=causal_sigma(alignment, age, gap),
        )

    return transition, split


def forecast(original, history):
    from leo.analysis.localization_v3 import phase_prior

    source = getattr(phase_prior, "__file__", None)
    stock = getattr(phase_prior, "transition", None)
    code = getattr(stock, "__code__", None)
    if not source or code is None or code.co_filename != source or stock.__name__ != "transition":
        raise UnreviewedTransition("unsupported phase transition binding")
    try:
        actual = sha256(Path(source).read_bytes()).hexdigest()
    except OSError as error:
        raise UnreviewedTransition("unreadable installed phase source") from error
    if actual != PHASE_SHA:
        raise UnreviewedTransition("unreviewed installed phase source " + actual)
    operation, split = transition_port(phase_prior)
    with patch.object(phase_prior, "transition", operation):
        result = original(history)
    info = split.cache_info()
    return result, dict(julian_cache_hits=info.hits, julian_cache_misses=info.misses,
                        julian_cache_entries=info.currsize, capacity=info.maxsize)


@contextmanager
def active_forecast(audit):
    from leo.analysis.localization_v3 import phase_prior
    from leo.application import localization_v3

    original = getattr(localization_v3, "forecast", None)
    audit["source_sha256"] = {
        "installed/phase_prior.py": PHASE_SHA,
        "exact_phase_forecast.py": sha256(Path(__file__).read_bytes()).hexdigest(),
    }

    if not callable(original):
        audit["fallback"] = "missing application phase forecast"
        yield
        return

    stock = getattr(phase_prior, "forecast", None)
    table = checked_table_wrapper(original, stock)
    if table:
        audit["source_sha256"]["installed/algo08_causal_table.py"] = TABLE_SHA

    def solve(history):
        execution = {"used": False}
        cpu, wall = process_time_ns(), perf_counter_ns()
        if original is stock or table:
            try:
                value, counts = forecast(original, history)
            except UnreviewedTransition as error:
                execution["fallback"] = str(error)
            else:
                execution.update(used=True, **counts)
        else:
            execution["fallback"] = "unsupported phase forecast binding"
        if not execution["used"]:
            value = original(history)
        execution.update(cpu_ns=process_time_ns() - cpu, elapsed_ns=perf_counter_ns() - wall)
        audit["executions"].append(execution)
        return value

    with patch.object(localization_v3, "forecast", solve):
        yield
