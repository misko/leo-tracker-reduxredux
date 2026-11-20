"""The frozen track receiver and separate compatibility diagnostics."""

import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

import numpy as np

from tools.pipeline_eval.reference import grid
from tools.pipeline_eval.variants import robust_em


def calibration_geometry(tracks):
    lanes = sorted({t.lane for t in tracks})
    lane_design = np.equal.outer([t.lane for t in tracks], lanes).astype(float)
    c = np.array([t.rf / 1e9 - 11.5 for t in tracks])
    design = np.column_stack((lane_design, c))
    rank = int(np.linalg.matrix_rank(design)) if tracks else 0
    return dict(
        observed_lanes=lanes,
        rf_hz=sorted({t.rf for t in tracks}),
        lane_offset_rank=len(lanes),
        lane_offset_and_c_rank=rank,
        c_has_independent_rf_contrast=rank > len(lanes),
    )


def offset_support(arcs):
    """Optimistic shape-screened level support at the offered tile center."""
    output = []
    offsets = np.linspace(-robust_em.PERIOD / 2, robust_em.PERIOD / 2, 181, endpoint=False)
    rates = np.array([-1000.0, -500.0, 0.0, 500.0, 1000.0])
    for lane in sorted({arc.track.lane for arc in arcs}):
        rows = [arc for arc in arcs if arc.track.lane == lane]
        folded = np.zeros((len(rates), len(offsets)), dtype=int)
        independent = 0
        unwrapped = 0
        limits = [[] for _ in rates]
        for row in rows:
            good = row.shape_loss <= 6.25
            levels = (row.residual - row.phase * row.phase_seed[:, None]).mean(axis=1)[good]
            if not len(levels):
                continue
            independent += 1
            shifted = levels[None, :] - rates[:, None] * row.track.drift.mean()
            error = robust_em.fold(shifted[:, :, None] - offsets)
            folded += (abs(error) <= 1500).any(axis=1)
            for i, values in enumerate(shifted):
                limits[i].append(values)
        for values in limits:
            if values:
                candidates = np.concatenate(values) - 1500
                overlap = sum(
                    (abs(row[:, None] - candidates) <= 1500 + 1e-9).any(axis=0) for row in values
                )
                unwrapped = max(unwrapped, int(overlap.max()))
        output.append(
            dict(
                lane=lane,
                shortlisted_tracks=len(rows),
                shape_supported_independent_offset=independent,
                shared_offset_folded=int(folded.max()),
                shared_offset_unwrapped=unwrapped,
            )
        )
    return output


def compatibility(observation, offer, catalogue):
    tracks, _ = robust_em.observations(observation)
    geometry = calibration_geometry(tracks)
    tile = grid.make_tile(grid.prepare_sky(observation, catalogue), offer["center"])
    margins = {"locked": -0.035, "0_deg": 0.0, "5_deg": np.sin(np.deg2rad(5)), "30_deg": 0.5}
    counts = {key: [] for key in margins}
    arcs = []
    for track in tracks:
        position, _, _ = grid._interpolated_states(tile, track.t)
        delta = position - tile.ecef_center_km
        minimum_up = ((delta @ tile.enu_frame[2]) / np.linalg.norm(delta, axis=-1)).min(axis=1)
        for key, limit in margins.items():
            counts[key].append(int(np.count_nonzero(minimum_up >= limit)))
        arc = robust_em.shortlist(tile, track)
        if arc is not None:
            arcs.append(arc)
    return dict(
        calibration=geometry,
        horizon={
            key: dict(
                tracks_with_candidate=sum(n > 0 for n in ns),
                orbit_track_pairs=sum(ns),
                per_track_candidates=ns,
            )
            for key, ns in counts.items()
        },
        common_offset=offset_support(arcs),
        fine_satellites=tile.stats["fine_satellites"],
    )


def main():
    packet = json.load(sys.stdin)
    observation, offer, catalogue = (packet[key] for key in ("observation", "offer", "catalogue"))
    start, cpu = perf_counter(), process_time()
    result = robust_em.infer(observation, offer, catalogue)
    receipt = dict(
        result=result, fit_wall_s=perf_counter() - start, worker_cpu_s=process_time() - cpu
    )
    start = perf_counter()
    receipt["observable_check"] = compatibility(observation, offer, catalogue)
    receipt["observable_check_wall_s"] = perf_counter() - start
    receipt["max_rss_kib"] = getrusage(RUSAGE_SELF).ru_maxrss
    json.dump(receipt, sys.stdout, allow_nan=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
