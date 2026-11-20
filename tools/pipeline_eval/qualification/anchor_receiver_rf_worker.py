"""Measure exact selected-track RF residuals without archived ownership or reference coordinates."""

from unittest.mock import patch

from ..variants import robust_em as lean
from ..variants import robust_orbit_fit as exact


def measure(solver, request):
    position, take = {}, {}
    original_valid, refine = exact.grid._valid_states, exact.refine

    def capture(*args):
        value = original_valid(*args)
        position["satellites"] = value[0]
        return value

    def replay(rows, initial, tile, region, half, arm):
        outcome = refine(rows, initial, tile, region, half, arm)
        state = outcome[0].state
        site = region.site(state.xy)[0]
        traces = []
        for row in rows:
            tr = row.arc.track
            frequency = exact.project(tile, row.orbit, tr.t, site, state.phase[row.orbit], tr.rf)[0]
            bias = (
                state.bias[tr.lane]
                + state.drift[tr.lane] * tr.drift
                + state.c_hz_per_ghz * (tr.rf / 1e9 - 11.5)
            )
            for t, measured, error in zip(
                tr.t, tr.hz, tr.hz - frequency - bias - row.alias * lean.PERIOD, strict=True
            ):
                folded = float(lean.fold(measured))
                lift = round((measured - folded) / lean.PERIOD) - row.alias
                traces.append(
                    dict(
                        key=[tr.lane, tr.rf, round(float(t), 6), round(folded, 3)],
                        norad=position["satellites"][row.orbit].satnum,
                        lift=lift,
                        error=float(error),
                    )
                )
        take[arm] = traces
        return outcome

    with patch.object(exact.grid, "_valid_states", capture), patch.object(exact, "refine", replay):
        result = solver.infer(request["observation"], request["offer"], request["catalogue"])
    return dict(result=result, samples=take)
