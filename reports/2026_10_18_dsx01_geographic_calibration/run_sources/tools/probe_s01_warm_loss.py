"""Repeat the same local loss with a fixed, better GPS-calibration restart."""

import argparse
import hashlib
import json
import shutil
import time
import types
from pathlib import Path

import probe_s01_local_loss as probe
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

BASE = probe.OUTPUT
OUTPUT = BASE / "warm_restart"


def fine_done(surface):
    return surface.get("fine_start", False) and all(
        r["stationary_stencil_scale_km"] is not None and r["stationary_stencil_scale_km"] <= 0.0625
        for r in surface["endpoints"].values()
    )


class WarmScan(Scan):
    def __init__(self, case):
        super().__init__(case)
        cold = json.loads((BASE / "truth_eight_rounds.json").read_text())
        prior = json.loads((BASE / "truth_prior_state_restart.json").read_text())
        self.starts = {
            key: min((cold[key], prior[key]), key=lambda r: r["score"])["state"] for key in cold
        }

    def at_point(self, point, *, models=METHODS, rounds=3, all_tracks=False):
        latitude, longitude = self.latlon(point)
        base = phase_linear_frequency(self.geometry, latitude, longitude)
        output = {}
        for method in models:
            for arm in ("c0", "fitted_c"):
                key = f"{arm}/{method}"
                state = probe.state_from_json(self.starts[key])
                history, best = [], None
                for i in range(rounds + 1):
                    score, rows, nominations, predicted = self.association(
                        state, base, point, method
                    )
                    history.append(
                        dict(
                            iteration=i,
                            score=score,
                            curved_points=sum(r["points"] for r in rows if r["compatible"]),
                        )
                    )
                    if best is None or score < best[0]:
                        best = score, state, rows
                    if i < rounds:
                        state, _ = self.update(state, nominations, predicted, point, method)
                score, state, rows = best
                if all_tracks:
                    score, rows, _, _ = self.association(
                        state, base, point, method, all_tracks=True
                    )
                output[key] = dict(
                    score=score,
                    state=state,
                    rows=rows,
                    history=history,
                    latitude_deg=latitude,
                    longitude_deg=longitude,
                )
        return output


def run(method):
    directory = OUTPUT / method
    directory.mkdir(parents=True, exist_ok=True)
    cold = [r for p in BASE.glob("grid_worker_*.json") for r in json.loads(p.read_text())]
    assert len(cold) == len(probe.grid_points())
    scan = WarmScan("DSX01-S01")
    grid_path = directory / "grid_worker_0.json"
    rows = json.loads(grid_path.read_text()) if grid_path.exists() else []
    completed = {tuple(r["east_north_km"]) for r in rows}
    for row in sorted(
        cold, key=lambda r: (sum(x * x for x in r["east_north_km"]), r["east_north_km"])
    ):
        point = row["east_north_km"]
        if tuple(point) in completed:
            continue
        start = time.monotonic()
        fits = scan.at_point(probe.position(scan, point), models=(method,))
        rows.append(probe.compact(point, fits))
        write(directory / "grid_worker_0.json", rows)
        if point == [0.0, 0.0]:
            write(directory / "truth_fits.json", fits)
        print(
            json.dumps(
                dict(
                    method=method,
                    warm_grid=len(rows),
                    point=point,
                    seconds=time.monotonic() - start,
                )
            ),
            flush=True,
        )
    # Reuse the identical bounded stencil search and c-arm query policy.
    probe.OUTPUT = directory
    # The grid fitter already owns the prepared orbit geometry. Reuse it for
    # local refinement instead of allocating a second complete geometry bank.
    probe.Scan = lambda case: scan
    surface = directory / f"{method}_surface.json"
    existing = json.loads(surface.read_text()) if surface.exists() else {}
    if not existing.get("fine_start", False):
        probe.local_search(method)
    if not fine_done(existing):
        probe.local_search(method, fine_start=True)
    for suffix in (
        "surface",
        "endpoints",
        "truth_all_tracks",
        "frozen_cuts",
        "iteration_sensitivity",
    ):
        source = directory / f"{method}_{suffix}.json"
        shutil.copyfile(source, OUTPUT / source.name)
    # The spatial experiment also needs a genuinely local, small-step start
    # for the cold branch. Reuse the same geometry with the base cold fitter.
    probe.OUTPUT = BASE
    scan.at_point = types.MethodType(Scan.at_point, scan)
    surface = BASE / f"{method}_surface.json"
    if not fine_done(json.loads(surface.read_text())):
        probe.local_search(method, fine_start=True)
    write(
        directory / "warm_protocol.json",
        dict(
            reference_intentionally_used=True,
            physical_model_priors_observations_candidates_gates_unchanged=True,
            candidate_identity_locking=False,
            initializer=(
                "best at GPS of cold eight-round and prior-blind-state eight-round restarts"
            ),
            fixed_initializer_reused_at_every_position=True,
            nuisance_rounds_per_location=3,
            not_a_gaussian_position_prior=True,
            not_an_exact_profile_likelihood=True,
            source_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    BASE / "truth_eight_rounds.json",
                    BASE / "truth_prior_state_restart.json",
                )
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", required=True, choices=METHODS)
    run(parser.parse_args().method)
