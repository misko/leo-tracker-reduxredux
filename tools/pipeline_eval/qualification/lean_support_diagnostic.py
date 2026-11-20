"""Measure held-pass and conditioning margins for the previously evaluated lean receiver."""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..__main__ import local_output, save_json
from ..reference import grid
from ..variants import robust_em as lean
from . import raw_robust
from .full_v5_check import BULK, _load_case
from .robust_em_trials import TIMING_IDS, load
from .robust_orbit_fit_trials import CONFIRMATION


def audit(packet):
    doc, offer = packet["observation"], packet["offer"]
    tracks, metrics = lean.observations(doc)
    tile = grid.make_tile(grid.prepare_sky(doc, packet["catalogue"]), offer["center"])
    arcs = [a for t in tracks if (a := lean.shortlist(tile, t)) is not None]
    held = [a for a in arcs if int(a.track.t.mean() // 12) % 5 == 2]
    train = [a for a in arcs if int(a.track.t.mean() // 12) % 5 != 2]
    n, half = len(tile.positions_km), offer.get("width_km", 25) / 2
    state = lean.iterate(train, lean.initial(train, n), n, half)
    if state is None:
        return dict(metrics, failure="no_training_assignment")
    trained = [r for r in lean.assign(train, state, update_phase=False) if r.loss <= 6.25]
    known = {r.orbit for r in trained}
    held_rows = lean.assign(held, state, update_phase=False)
    profiled = lean.assign(held, state, update_phase=True)
    pooled = lean.iterate(arcs, state, n, half)
    if pooled is None:
        return dict(metrics, failure="no_pooled_assignment")
    owners = [r for r in lean.assign(arcs, pooled, update_phase=False) if r.loss <= 6.25]
    by_arc = {id(r.arc): r for r in owners}
    matched = [r for r in trained if id(r.arc) in by_arc]
    train_fit = lean.fit(trained, n, half, "c0")
    fits, final, reason = lean.solve(arcs, n, half)
    local = [r for r in held_rows if r.orbit in known]
    novel = [r for r in held_rows if r.orbit not in known]
    return dict(
        metrics,
        acceptance=reason,
        final=final,
        support=dict(
            training_known_orbits=len(known),
            training_tracks=len(trained),
            matched_training_tracks=len(matched),
            matched_owner_or_alias_changes=sum(
                (r.orbit, r.alias) != (by_arc[id(r.arc)].orbit, by_arc[id(r.arc)].alias)
                for r in matched
            ),
            trained_orbit_held_tracks=len(local),
            trained_orbit_compatible=sum(r.loss <= 6.25 for r in local),
            novel_orbit_held_tracks=len(novel),
            novel_orbit_compatible=sum(r.loss <= 6.25 for r in novel),
            held_compatible_with_free_phase=sum(r.loss <= 6.25 for r in profiled),
            spans_over_12_s_held=sum(bool(np.ptp(r.arc.track.t) > 12) for r in held_rows),
            arcs_over_32_s=sum(bool(np.ptp(a.track.t) >= 32) for a in arcs),
            trained_orbit_held_score=float(np.mean([1 / (1 + r.loss) for r in local]))
            if local
            else None,
            novel_orbit_held_score=float(np.mean([1 / (1 + r.loss) for r in novel]))
            if novel
            else None,
        ),
        conditional_train_radius95_km=train_fit.radius_km if train_fit else None,
        conditional_fit_radius95_km={arm: fit.radius_km for arm, fit in fits.items()}
        if fits
        else {},
    )


def execute(case, scope, cache, cpu):
    if scope == "capture-era":
        packet, bindings = load(case, "matched-tile", cache)
    else:
        item = _load_case(case)
        native, checksum, _ = raw_robust.bind_detector(item, "ordinary-native", None)
        graph = raw_robust.build_tracks(item, native, checksum, cpu)
        catalogue = item["catalog"]
        path = raw_robust._check(BULK / catalogue["path"], catalogue["sha256"])
        packet = dict(
            observation=graph["projection"], offer=item["regions"][0], catalogue=path.read_text()
        )
        bindings = dict(native_sha256=checksum, catalogue_sha256=catalogue["sha256"])
    row = dict(id=case, scope=scope, **bindings, **audit(packet))
    print(case, scope, row.get("acceptance"), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=local_output, required=True)
    parser.add_argument("--cache", type=local_output, required=True)
    args = parser.parse_args()
    jobs = [(c, "capture-era") for c in CONFIRMATION] + [(c, "ordinary") for c in TIMING_IDS]

    def lane(cpu):
        os.sched_setaffinity(0, {cpu})
        output = []
        for case, scope in jobs[cpu - 10 :: 2]:
            try:
                output.append(execute(case, scope, args.cache, cpu))
            except (KeyError, OSError, ValueError) as error:
                output.append(dict(id=case, scope=scope, failure=str(error)))
        return output

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = [row for values in pool.map(lane, (10, 11)) for row in values]
    save_json(args.output, rows)


if __name__ == "__main__":
    main()
