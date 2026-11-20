from functools import lru_cache
from types import SimpleNamespace
from weakref import ref

import numpy as np
import pytest

from tools.pipeline_eval.qualification import cavity_pressure_bundle as bundle

SOURCE = """def constrained(scan, node, mask, powers, means, hyper, entries, pair):
    output = {}
    for arm in ARMS:
        reference = np.asarray(pair[arm]["phase_reference"])
        x = np.asarray(pair[arm]["endpoint_east_north_km"])
        history = []
        for _epoch in range(5):
            p = _problem(scan, node, mask, arm, reference, powers, means, hyper, entries)
            fitted = feasible_fit(
                lambda z, p=p: p.calculate(z)["negative_twice_elbo"],
                lambda z, p=p: np.asarray(list(gate_slacks(p, z, entries).values())) - 0.01,
                x,
                p.lower,
                p.upper,
                iterations=40,
            )
            x = np.asarray(fitted["parameters"])
            phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
            history.append(dict(fit=fitted, phase_change_s=float(np.max(abs(phase - reference)))))
            reference = phase
        output[arm] = summary(p, x, entries)
        output[arm].update(
            history=history,
            final_phase_change_s=history[-1]["phase_change_s"],
            minimum_gate_slack=min(gate_slacks(p, x, entries).values()),
        )
    return output
"""


def run_refits(source):
    models, reads = [], []

    def problem(_scan, _node, _mask, arm, phase, _powers, _means, _hyper, _entries):
        model = SimpleNamespace(
            labels=[0], lower=[-12.5, -12.5], upper=[12.5, 12.5], arm=arm, phase=phase
        )

        @lru_cache(maxsize=8)
        def calculate(x):
            return {"negative_twice_elbo": -(sum(x) ** 2) + model.phase[0]}

        model.calculate = lambda x: calculate(tuple(x))
        model.state = lambda _x: {"phases": np.array([model.phase[0] + 0.25])}
        models.append(ref(calculate))
        return model

    def feasible_fit(objective, slacks, x, lower, upper, *, iterations):
        assert lower == [-12.5, -12.5] and upper == [12.5, 12.5] and iterations == 40
        z = x + [0.25, 0.5]
        reads.append((objective(z), tuple(slacks(z))))
        return {"parameters": z.tolist()}

    def slacks(p, x, _entries):
        return {p.arm: 1 + p.calculate(x)["negative_twice_elbo"] / 100}

    def summary(p, x, _entries):
        return {
            "endpoint": x.tolist(),
            "phase": p.state(x)["phases"].tolist(),
            "score": p.calculate(x)["negative_twice_elbo"],
        }

    arms = ("c0", "fitted_c")
    globals_ = dict(
        ARMS=arms,
        np=np,
        _problem=problem,
        feasible_fit=feasible_fit,
        gate_slacks=slacks,
        summary=summary,
    )
    exec(source, globals_)
    raw = {"phase_reference": [0.0], "endpoint_east_north_km": [0.0, 0.0]}
    values = globals_["constrained"](*([None] * 7), dict.fromkeys(arms, raw))
    return values, reads, models


def test_last_use_breaks_cache_cycle_and_preserves_both_arm_rounds():
    import gc

    before = gc.isenabled()
    gc.disable()
    try:
        stock, stock_reads, old = run_refits(SOURCE)
        released, released_reads, new = run_refits(bundle.release_source(SOURCE))
        assert released == stock and released_reads == stock_reads
        assert len(old) == len(new) == len(released_reads) == 10
        assert all(model() is not None for model in old)
        assert all(model() is None for model in new)
        assert all(arm["minimum_gate_slack"] > 0.8 for arm in released.values())
    finally:
        if before:
            gc.enable()
        gc.collect()


@pytest.mark.parametrize("source", ("", SOURCE.replace("reference = phase", "reference = x")))
def test_staging_fails_closed_on_missing_source_anchors(source):
    with pytest.raises(ValueError, match="pinned source"):
        bundle.release_source(source)
