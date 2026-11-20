from tempfile import TemporaryFile
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.armijo_finish_phase_retry import prepare_remap
from tools.pipeline_eval.qualification.compact_entry_results import SCIENTIFIC, parity
from tools.pipeline_eval.variants import v5_compact_receiver as direct
from tools.pipeline_eval.variants import v5_stream_recovery


def test_unhashed_scratch_matches_qualified_rows_and_eligibility():
    stored = np.arange(36.0).reshape(4, 3, 3)
    stored[2, 0, 1] = np.nan
    with TemporaryFile("w+b", buffering=0) as a, TemporaryFile("w+b", buffering=0) as b:
        old, new = v5_stream_recovery.OrbitRows(a, 3), direct.ScratchRows(b, 3)
        for bank in (old, new):
            bank.append(stored[:2])
            bank.append(stored[2:])
            bank.append(stored[:0])
            with pytest.raises(ValueError, match="state block shape"):
                bank.append(np.ones((3, 3)))
        assert old.nbytes == new.nbytes == stored.nbytes
        assert old.shape == new.shape and not old.finite and not new.finite
        np.testing.assert_array_equal(old[:], new[:])
        np.testing.assert_array_equal(old[-1], new[-1])
        assert not hasattr(new, "digest")


def test_ordered_phase_initializer_matches_the_archived_repair():
    problem = SimpleNamespace(reference=np.zeros(2), labels=[0])
    state = dict(phases=np.array([2.0]))
    ctx = dict(
        scan=SimpleNamespace(norads=[7, 8]),
        node=dict(seed=dict(rows=[dict(candidate_index=0, candidate_norad=7)], state=state)),
        means=np.zeros(2),
        problems={a: (problem, np.zeros(2)) for a in ("c0", "fitted_c")},
    )
    old, _ = prepare_remap(ctx, (7,), 8)
    new = direct.align_phase_seed(ctx, (7,), 8)
    np.testing.assert_array_equal(
        old["node"]["seed"]["state"]["phases"], new["node"]["seed"]["state"]["phases"]
    )
    np.testing.assert_array_equal(state["phases"], [2.0])
    assert direct.align_phase_seed(new, None, None) is new
    with pytest.raises(ValueError, match="exact adopted catalogue-slot authority"):
        direct.align_phase_seed(ctx, (7,), 9)


def test_parity_requires_scientific_fields_and_named_work_counters():
    binding = dict(input_sha256="raw", native_sha256="native", catalog_sha256="tle", tile="roof")
    common = dict.fromkeys(SCIENTIFIC, 3)
    stock_metrics = dict(
        common,
        position_optimizer={"calls": 2, "wall_s": 1},
        tiled_salvage={"counters": {"tiles": 3}},
    )
    live_metrics = dict(common, position_optimizer={"calls": 2}, salvage_work={"tiles": 3})
    arms = {"c0": {"latlon": [0, 0]}, "fitted_c": {"latlon": [0.01, 0]}}
    old = dict(binding, result=dict(status="ok", arms=arms, metrics=stock_metrics))
    new = dict(binding, result=dict(status="ok", arms=arms, metrics=live_metrics))
    assert parity(old, new)["exact"]
    stock_metrics.pop("c0_conditional_rms_hz")
    live_metrics.pop("c0_conditional_rms_hz")
    result = parity(old, new)
    assert result["missing_in_both"] == ["c0_conditional_rms_hz"]
    assert result["all_reported_fields_match"] and not result["exact"]
    live_metrics.pop("reassociation_selected")
    assert not parity(old, new)["all_reported_fields_match"]
