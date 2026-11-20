"""Expose training-only nominations in the already sealed DS26-0197 failed rescue."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import read_predictions, save_json
from ..variants import conditional_support_recovery as variant
from ..variants import native_lean as native
from . import conditional_support_trial as trial


def main(path):
    case = "DS26-0197"
    targets = {}
    stocks, _ = trial.jobs()
    query, paths, _ = next(r for r in stocks if r[0]["id"] == case)
    packet = query["packet"]
    clock, lanes, _ = native.peak_lanes(
        dict(packet["native"], path=str(paths["native"])), packet["probe_limit"], packet["cutoff"]
    )
    graph = native.graph_projection(lanes, json.loads(paths["track_config"].read_bytes())["config"])
    obs = dict(clock, tracks=graph, catalog_timestamp_ns=packet["catalog_timestamp"])
    lock = trial.joint.phase._read(trial.OUTPUT / "prediction-lock.json")
    trial.joint.secant_full._verify_files(trial.OUTPUT, lock["files"])
    row = read_predictions(trial.OUTPUT / "positions.jsonl.gz")[case]
    if native.projection_digest(obs) != row["observation_sha256"]:
        raise ValueError("forensic input differs from the blind Graph")
    real_bank, cells = variant.phase._shift_bank, variant.phase.cells

    def bank(sky, tile):
        wide, order, ids = real_bank(sky, tile)
        targets["norads"] = ids
        return wide, order, ids

    def capture(wide, track, sites, lane):
        result = cells(wide, track, sites, lane)
        key = [float(track.t[0]), float(track.t[-1]), len(track.t), track.lane, track.rf]
        if key[2] in (41, 30) and key[3] == 2 and 124.8 < key[0] < 124.9:
            targets.setdefault("data", []).append((key, result.copy(), sites.copy()))
        return result

    with (
        patch.object(variant.phase, "cells", capture),
        patch.object(variant.phase, "_shift_bank", bank),
    ):
        result, trace = variant.infer(obs, packet["offer"], paths["catalogue"].read_bytes())
    if (
        result["arms"] != row["result"]["arms"]
        or trace["proposals"] != row["recovery"]["proposals"]
    ):
        raise ValueError("training profile instrumentation changed candidate output")
    ids = targets["norads"]
    profile = []
    for key, tensor, sites in targets["data"]:
        m = tensor.min(axis=(0, 2))
        ranked = np.argsort(m, kind="stable")
        chosen = ids.index(67348)
        finalists = []
        for i in dict.fromkeys([*ranked[:5], chosen]):
            j, p = np.unravel_index(np.argmin(tensor[:, i]), tensor[:, i].shape)
            finalists.append(
                dict(
                    norad=ids[i],
                    rank=int(np.flatnonzero(ranked == i)[0]) + 1,
                    loss=float(m[i]),
                    site_en_km=sites[j].tolist(),
                    phase_s=float(variant.phase.PHASES[p]),
                    losses=[float(x) if np.isfinite(x) else None for x in tensor[:, i].min(axis=0)],
                )
            )
        profile.append(
            dict(track=key, finalists=finalists, horizon_orbits=int(np.isfinite(m).sum()))
        )
    save_json(
        path,
        dict(
            id=case,
            graph_sha256=row["observation_sha256"],
            phases_s=variant.phase.PHASES.tolist(),
            rows=profile,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
