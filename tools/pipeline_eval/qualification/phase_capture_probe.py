"""Audit the two predeclared curves against every causal regional orbit after sealing."""

import gzip
import json
from types import SimpleNamespace

import numpy as np

from ..__main__ import read_predictions, save_json
from ..variants import phase_capture as method
from . import association_evidence as prior
from . import phase_capture_trial as trial


def view(case, observation, trace, data, receipt, paths):
    tracks, _ = method.lean.observations(observation)
    sky = method.grid.prepare_sky(observation, paths["catalogue"].read_bytes())
    tile = method.grid.make_tile(sky, receipt["tile"]["center"])
    bank, _, ids = method._shift_bank(sky, tile)
    if ids != data["norads"] or trace["observation_sha256"] != receipt["observation_sha256"]:
        raise ValueError("orbit universe or native Graph differs from the blind experiment")
    lane = SimpleNamespace(bias=data["lane_bias_hz"], drift=data["lane_drift_hz_per_100s"])
    sites = np.asarray(data["sites_en_km"])
    other = trace["selected"]
    expected = int(max(other["v5_c0"], key=other["v5_c0"].get))
    origin = other["joint_train"]
    nominated = set((expected, origin))

    def locate(record):
        t = record["times"]
        return next(
            i
            for i, r in enumerate(tracks)
            if np.array_equal(r.t, t)
            and r.rf == record["rf_hz"]
            and r.lane == 2 * (record["receiver"] - 1) + int(record["channel"] > 4)
        )

    expected_index = ids.index(expected)
    basin = data["basins"][str(expected_index)]
    options = []
    owner = str(expected)
    for arc in trace["track_inventory"]:
        graph_index = arc["index"]
        if graph_index != other["index"] and not arc["v5_c0"].get(owner):
            continue
        rec = observation["tracks"][graph_index]
        track_i = locate(rec)
        track = tracks[track_i]
        cost = method.cells(bank, track, sites, lane)
        own_cost = cost.min(axis=(0, 2))
        ranked = np.argsort(own_cost, kind="stable")
        lean_basin = float(cost[basin["site"], expected_index, basin["phase_index"]])
        phase_curves = []
        for k in ranked:
            if ids[k] not in nominated and not (
                len(phase_curves) < 4 and graph_index == other["index"]
            ):
                continue
            if not np.isfinite(own_cost[k]):
                continue
            j, p = np.unravel_index(np.argmin(cost[:, k]), cost[:, k].shape)
            phase_curves.append(
                dict(
                    norad=ids[k],
                    rank=int(np.flatnonzero(ranked == k)[0] + 1),
                    min_loss=float(own_cost[k]),
                    phase_s=float(method.PHASES[p]),
                    sentinel=int(j),
                    cost_profile=[
                        float(x) if np.isfinite(x) else None for x in cost[:, k].min(axis=0)
                    ],
                )
            )
        options.append(
            dict(
                graph_track=graph_index,
                track=track_i,
                points=len(track.t),
                start_s=float(track.t[0]),
                end_s=float(track.t[-1]),
                lane=track.lane,
                curved=track.curved,
                candidate_count=int(np.isfinite(own_cost).sum()),
                downstream_holdout=method._held(track),
                acquisition_check=method._anchor_check(track),
                expected_loss_at_shared_basin=lean_basin if np.isfinite(lean_basin) else None,
                finalists=phase_curves,
            )
        )
    return dict(
        id=case,
        target=other["index"],
        published_norad=expected,
        competing_training_norad=origin,
        norads=len(ids),
        phases=method.PHASES.tolist(),
        fitted_basin=basin,
        curves=options,
        source_graph_sha256=receipt["observation_sha256"],
        source_catalog_sha256=receipt["catalog_sha256"],
    )


def main():
    trial.joint.secant_full._verify_files(
        trial.OUTPUT, trial.joint.phase._read(trial.OUTPUT / "prediction-lock.json")["files"]
    )
    rows = read_predictions(trial.OUTPUT / "positions.jsonl.gz")
    with gzip.open(trial.OUTPUT / "phase-evidence.jsonl.gz", "rt") as stream:
        data = {row["id"]: row for row in map(json.loads, stream)}
    jobs, _ = trial.setup()
    paths = {query["id"]: paths for query, paths, _ in jobs}
    results = []
    for case in trial.DEVELOPMENT:
        trace = json.loads(
            gzip.decompress((prior.OUTPUT / (case + "-native-trace.json.gz")).read_bytes())
        )
        results.append(
            view(case, trace["trace"]["observation"], trace, data[case], rows[case], paths[case])
        )
    save_json(trial.OUTPUT / "diagnostic-phase-profiles.json", results)


if __name__ == "__main__":
    main()
