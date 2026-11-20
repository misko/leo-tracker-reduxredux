"""Read only authenticated causal TLEs inside the native Graph worker."""

import json
import sys
from unittest.mock import patch

from tools.pipeline_eval.qualification import phase_forecast_history as history
from tools.pipeline_eval.variants import native_lean as native
from tools.pipeline_eval.variants import phase_forecast as law
from tools.pipeline_eval.variants import robust_orbit_fit as exact


def worker(packet):
    if packet["mode"] != "native":
        raise ValueError("expected complete archived native GLRT")
    detail, index, retained = {}, {}, {}
    refine, bank = exact.refine, law.gauge._shift_bank

    def selected_bank(*args):
        wide, order, ids = bank(*args)
        index.update(zip(order, ids, strict=True))
        return wide, order, ids

    def fit(rows, starting_fit, tile, region, half, arm):
        fit_value, diagnostic = refine(rows, starting_fit, tile, region, half, arm)
        retained[arm] = [
            dict(
                norad=index.get(r.orbit),
                rf_hz=r.arc.track.rf,
                points=len(r.arc.track.t),
                lane=r.arc.track.lane,
                start_s=float(r.arc.track.t[0]),
                end_s=float(r.arc.track.t[-1]),
                relative_phase_s=float(fit_value.state.phase[r.orbit]),
                alias=r.alias,
            )
            for r in rows
        ]
        return fit_value, diagnostic

    def forecast(document, offer, catalogue):
        def past(current, metadata, audit):
            return history.predecessors(current, metadata, packet["phase_history"], audit)

        result, receipt = law.infer(document, offer, catalogue, past)
        detail.update(receipt)
        return result

    with (
        patch.object(exact, "infer", forecast),
        patch.object(exact, "refine", fit),
        patch.object(law.gauge, "_shift_bank", selected_bank),
    ):
        result = native.worker(packet)
    result["result"]["boundary"] = law.BOUNDARY
    result["stages"]["signed_phase_joint"] = result["stages"].pop("same_exact_backend")
    result["signed_phase"] = dict(detail, kept_by_arm=retained)
    return result


if __name__ == "__main__":
    start = native._now()
    result = worker(json.load(sys.stdin))
    result["worker"] = native._elapsed(start)
    json.dump(result, sys.stdout, sort_keys=True, allow_nan=False)
