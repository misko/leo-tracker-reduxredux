from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import algo08_conservative_continuation as continuation


def fixture_fit(*, initial_phase=(0., 0.), point=(1., 2.), last_phase_change=0.005,
                stopped="small_bounded_step"):
    point = np.asarray(point)
    fit = dict(stopped=stopped, parameters=point, evaluations=6, history=[dict(parameters=point)])
    p = SimpleNamespace(labels=[0, 2], lower=np.full(2, -12.5), upper=np.full(2, 12.5),
                        rows=[dict(component="arc", candidate_index=0)], alias=[0])
    row = dict(fit=fit, max_last_phase_change_s=last_phase_change, endpoint_east_north_km=point,
               state=dict(phases=np.array([2., 44., -18.])), frequency_rms_hz=1.,
               phase_reference=np.zeros(2),
               history=[dict(fit=fit, phase_reference=np.asarray(initial_phase))])
    return p, row


def test_uses_physical_phase_with_original_clipping_and_bounds():
    p, record = fixture_fit()
    position, phase = continuation.physical_seed(p, record)
    np.testing.assert_array_equal(position, [1., 2.])
    np.testing.assert_array_equal(phase, [2., -15.])
    out_of_bounds = dict(record, endpoint_east_north_km=[13., 0.])
    assert continuation.physical_seed(p, out_of_bounds) is None
    assert continuation.physical_seed(p, dict(record, max_last_phase_change_s=0.1)) is None


@pytest.mark.parametrize("changed", (None, "scan", "node", "mask", "budget", "unstable"))
def test_seed_is_scoped_to_the_immediately_following_matched_fitted_arm(changed):
    scan, node = object(), object()
    keep = np.array([True, True])
    calls, observed = [], []

    def stock(scan, node, keep, arm, *, rounds, iterations):
        observed.append(arm)
        return fixture_fit()

    def seeded(scan, node, keep, scales, arm, model, *, start, initial_phase, rounds, iterations):
        assert model == "native" and arm == "fitted_c" and scales == []
        assert (rounds, iterations) == (5, 48)
        np.testing.assert_array_equal(start, [1., 2.])
        np.testing.assert_array_equal(initial_phase, [2., -15.])
        observed.append("seeded")
        return fixture_fit(initial_phase=initial_phase, last_phase_change=.1 if changed == "unstable" else 0.)

    compare = continuation.pair_calls(stock, seeded, calls, audit=lambda *args: {"replay_delta": 0.})
    compare(scan, node, keep, "c0")
    compare(object() if changed == "scan" else scan, object() if changed == "node" else node,
            np.array([True, False]) if changed == "mask" else keep, "fitted_c",
            rounds=4 if changed == "budget" else 5)
    compare(scan, node, keep, "fitted_c")
    suffix = {None: ["seeded", "fitted_c"], "unstable": ["seeded", "fitted_c", "fitted_c"]}
    assert observed == ["c0", *suffix.get(changed, ["fitted_c", "fitted_c"])]
    assert calls[1]["mode"] == ("continued" if changed is None else "stock")
    if changed == "unstable":
        assert calls[1]["fallback"] == "seeded fit did not settle"


def test_seedable_fit_preserves_the_original_signature_for_its_other_inputs():
    import inspect

    seeded = continuation.seedable_position()
    params = dict(inspect.signature(seeded).parameters)
    assert params.pop("initial_phase").kind == inspect.Parameter.KEYWORD_ONLY
    assert params == inspect.signature(continuation.retained_position.fit_position).parameters
