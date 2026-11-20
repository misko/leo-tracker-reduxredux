"""Emit inferred tracks and training diagnostics without opening reference ownership."""

import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import process_time
from unittest.mock import patch

from ..variants import joint_orbits as joint
from ..variants import robust_em as lean
from ..variants import robust_orbit_fit as exact

METHODS = {module.METHOD: module for module in (lean, exact, joint)}


def trace(document, rows, satellites):
    source = {}
    for track in document["tracks"]:
        lane = 2 * (track["receiver"] - 1) + int(track["channel"] > 4)
        for seconds, cfo in zip(track["times"], track["values"], strict=True):
            source.setdefault(
                (lane, track["rf_hz"], seconds, cfo), (track["receiver"], track["channel"])
            )
    for index, row in enumerate(rows):
        tr = row.arc.track
        for t, f in zip(tr.t, tr.hz, strict=True):
            rx, ch = source[tr.lane, tr.rf, t, f]
            yield dict(
                track=index,
                receiver=rx,
                channel=ch,
                time_s=float(t),
                cfo_hz=float(f),
                norad=satellites[row.orbit].satnum,
            )


def measured(request):
    method = request["method"]
    document, offer, catalogue = (request[k] for k in ("observation", "offer", "catalogue"))
    captured = {}
    valid, iterate, fit, refine = exact.grid._valid_states, lean.iterate, lean.fit, exact.refine

    def capture_bank(*args):
        result = valid(*args)
        captured["satellites"] = result[0]
        return result

    def capture_train(arcs, state, count, half):
        predicted = iterate(arcs, state, count, half)
        captured.setdefault("train", (arcs, predicted, count, half))
        return predicted

    def capture_fit(rows, n, half, arm):
        result = fit(rows, n, half, arm)
        if method == lean.METHOD and arm == "fitted_c":
            captured["owners"] = rows
        return result

    def capture_refine(rows, start, tile, region, half, arm):
        captured["owners"] = rows
        return refine(rows, start, tile, region, half, arm)

    began = process_time()
    with (
        patch.object(exact.grid, "_valid_states", capture_bank),
        patch.object(lean, "iterate", capture_train),
        patch.object(lean, "fit", capture_fit),
        patch.object(exact, "refine", capture_refine),
    ):
        result = METHODS[method].infer(document, offer, catalogue)
    measured_cpu = process_time() - began
    measured_rss = getrusage(RUSAGE_SELF).ru_maxrss
    owners = list(trace(document, captured.get("owners", []), captured.get("satellites", [])))
    held = result["metrics"].get("held_by_arm", {})
    if "train" in captured and captured["train"][1] is not None:
        training, state, count, half = captured["train"]
        # Diagnostic replay on the original prepared measurements. It never changes either fix.
        sky = exact.grid.prepare_sky(document, catalogue)
        tile = exact.grid.make_tile(sky, offer["center"])
        held_arcs = [
            row
            for tr in lean.observations(document)[0]
            if int(tr.t.mean() // 12) % 5 == 2 and (row := lean.shortlist(tile, tr)) is not None
        ]
        if held_arcs:
            held["c0"] = joint._validation(held_arcs, state)
            matched = [
                r for r in lean.assign(training, state, update_phase=False) if r.loss <= 6.25
            ]
            fitted = fit(matched, count, half, "fitted_c")
            if fitted is not None:
                held["fitted_c"] = joint._validation(held_arcs, fitted.state)
    return dict(
        result=result,
        owners=owners,
        heldout_diagnostics=held,
        worker_cpu_s=measured_cpu,
        max_rss_kib=measured_rss,
    )


def main():
    json.dump(measured(json.load(sys.stdin)), sys.stdout, allow_nan=False)


if __name__ == "__main__":
    main()
