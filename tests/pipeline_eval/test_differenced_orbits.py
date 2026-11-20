from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import differenced_orbits as model


def test_staggered_stencils_cancel_quadratic_shared_clock_alias_and_fixed_rf():
    sample = np.arange(-3.7, 4, 0.7)
    rows, physical = [], np.array([-250.0, 50.0, 420.0])
    for i, (rf, rate) in enumerate(zip((11.2e9, 11.5e9, 11.7e9), physical, strict=True)):
        t = sample + 0.12 * i
        hz = (10 + i) * model.tracker.PERIOD + rate * t + 13 * rf / 1e9 + 200 * t + 50 * t**2
        d = model.stencil(t, hz, 0)
        np.testing.assert_allclose(
            d.weights @ np.stack((t**0, t, t**2), axis=1), [0, 1, 0], atol=1e-12
        )
        rows.append(d.rate)
    np.testing.assert_allclose(model.HELMERT @ rows, model.HELMERT @ physical, atol=1e-8)
    assert model.stencil(np.array([-3.8, -3, 2, 3]), np.zeros(4), 0) is None


def test_scaled_carrier_copies_do_not_supply_independent_rates():
    rfs = [11.2e9, 11.45e9, 11.7e9]
    values = np.array([[0, -12e2], [10, -1182], [-400, -500]])
    arcs = [
        [SimpleNamespace(rate=r * rf / 12e9) for r in a] for a, rf in zip(values, rfs, strict=True)
    ]
    assert model.potential_copy(arcs, rfs)
    arcs[1] = [SimpleNamespace(rate=-300), SimpleNamespace(rate=-2350)]
    assert not model.potential_copy(arcs, rfs)


def test_triplet_search_recovers_assignment_and_excludes_reuse():
    rng = np.random.default_rng(852)
    rates = rng.normal(0, 500, size=(3, 32, 3))
    expected = np.array([15, 6, 19])
    observed = rates[np.arange(3), expected] + [450, 530, -10]
    options, loss = model.ranked_triples(rates, observed)
    assert (options[np.argmin(loss)] == expected).all()
    assert loss.min() < 1e-9
    assert all(len(set(row)) == 3 for row in options)


def test_prefix_group_survives_missing_held_continuation():
    probes = []
    for i, rate in enumerate((-1000.0, -650.0, -240.0)):
        for local in np.arange(0.2, 40.0, 0.5):
            t = local + 0.07 * i
            probes.append(
                dict(
                    valid_start_counter=round(t * 1000),
                    probe_start_ms=0,
                    receiver_id=0,
                    channel=i + 1,
                    actual_rf_hz=11e9 + i * 2.5e8,
                    candidates=[
                        dict(
                            fractional_tracking_cfo_hz=float(model.tracker.wrap(110000 + rate * t)),
                            candidate_rank=1,
                            fractional_margin=0.5,
                            passed_fractional_margin_gate=True,
                        )
                    ],
                )
            )
    fields = dict(first_counter=0, sample_rate_hz=1000, probe_ms=20)
    full, _, inventory = model.support(SimpleNamespace(probes=probes, **fields))
    truncated, _, missing = model.support(
        SimpleNamespace(probes=[p for p in probes if p["valid_start_counter"] < 23990], **fields)
    )
    assert inventory["exact_distinct_rf_path_windows"] == 0
    assert inventory["train_groups"] == missing["train_groups"] == len(full) == len(truncated) == 1
    assert full[0].slots == (0, 1, 2, 3, 4)
    assert truncated[0].slots == (0, 1, 2)
    for all_windows, early in zip(full[0].arcs, truncated[0].arcs, strict=True):
        np.testing.assert_equal([s.rate for s in all_windows[:3]], [s.rate for s in early])
