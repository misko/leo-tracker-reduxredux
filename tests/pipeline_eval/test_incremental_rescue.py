from contextlib import ExitStack
from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval import wide_runtime
from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import (
    differential_pilot_eval,
    incremental_rescue_build,
    incremental_rescue_eval,
    incremental_rescue_gate,
)
from tools.pipeline_eval.variants import incremental_rescue


def test_fit_free_sham_has_one_fixed_valid_epoch_per_visit_and_lane():
    identities = ("DS26-0197:112", "DS29-0316:112", "control:lower:zero")
    expected = {
        (i, rx): incremental_rescue_eval.sham_epoch(i, rx) for i in identities for rx in (0, 1)
    }
    assert all(0 <= value < 13_333 for value in expected.values())
    assert len(set(expected.values())) == 6
    assert expected == {
        (i, rx): incremental_rescue_eval.sham_epoch(i, rx) for i in identities for rx in (1, 0)
    }


def test_fallback_requires_exact_rows_and_rejects_stock_regions():
    stock = dict(rows=[{"candidates": [], "receiver_id": i} for i in (0, 1)])
    trace = [
        dict(
            rx=i,
            stock_positive=False,
            donor_positive=False,
            ordinary=[10],
            evaluated_epochs=[1, 2, 3],
        )
        for i in (0, 1)
    ]
    incremental_rescue_gate.check(stock, stock, trace, [0, 1])
    with pytest.raises(ValueError, match="fallback or positive stock row changed"):
        incremental_rescue_gate.check(stock, {"rows": list(reversed(stock["rows"]))}, trace, [0, 1])
    trace[0]["evaluated_epochs"] = [7, 8, 9]
    with pytest.raises(ValueError, match="new disjoint native region"):
        incremental_rescue_gate.check(stock, stock, trace, [0, 1])


@pytest.mark.hardware
def test_release_native_install_scope_and_real_control_routing(tmp_path):
    # Exact authenticated detector build uses the pinned compiler and FFTW on the measured host.
    root = tmp_path / "wide"
    wide_runtime.build(root, Path("/usr"), variants=("stock",))
    work = tmp_path / "rescue"
    incremental_rescue_build.build(work, root / "stock" / wide_runtime.OUTPUTS[0], Path("/usr"))
    paths, _ = incremental_rescue_gate.release(work)
    with ExitStack() as stack:
        native = incremental_rescue_gate.attach(stack, paths, "lower")
        real_scout = stack.enter_context(
            incremental_rescue.SingleLaneScout(paths["scout"], "lower")
        )
        requested = []
        nominations = {}

        def select(sample, edge, rx):
            requested.append(rx)
            return ([nominations[rx]], []) if rx in nominations else real_scout(sample, edge, rx)

        candidate = incremental_rescue.IncrementalRescueCall(
            native["detector"], "lower", scout=select
        )
        plant = differential_pilot_eval.synthetic("lower", "one-frame")[0]
        null = np.zeros_like(plant)
        null_stock = native["stock"].analyze(null)
        nominations.update({0: 0, 1: 13_332})
        result, _, trace, time = candidate(null, decode=native["detector"].analyze)
        assert requested == [0, 1]
        assert [lane["evaluated_epochs"] for lane in trace] == [[0, 1], [13_331, 13_332]]
        assert all(lane["decision"] == "donor_negative" for lane in trace)
        assert encoded(result) == encoded(null_stock)
        assert time["combined_wall_ns"] == sum(
            time[f"{key}_wall_ns"] for key in ("stock", "scout", "rescue")
        )
        nominations.clear()
        requested.clear()
        assert any(row["donor_positive"] for row in candidate(plant)[2])
        strong = differential_pilot_eval.synthetic("lower", "strong")[0]
        requested.clear()
        rescued, _, trace, _ = candidate(strong)
        assert requested == []
        assert all(row["stock_positive"] for row in trace)
        assert encoded(rescued) == encoded(native["stock"].analyze(strong))
