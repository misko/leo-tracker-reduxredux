"""Transfer the frozen robust CFO model to four existing randomized DS6 scans.

Local search uses another scan's inferred position, never the roof reference.
This is a development generalization check, not blind global localization.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from leo.analysis.adaptive_tle_prediction import (
    LIGHT_KM_S, REFERENCE_RF_HZ, propagate_candidate_states,
)
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_09_27_ds6_exact_timing"))
from robust import robust_scores


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    source = REPORTS / "2026_09_27_ds6_common_rate_validation"
    previous = REPORTS / "2026_09_27_ds6_exact_timing/robust-extended/results.json"
    center = json.loads(previous.read_text())["best"]["quarter"]["cfo"]
    paths = sorted(source.glob("scan-fw-*-plan.json"))
    assert len(paths) == 4
    protocol = dict(
        inputs={p.name: digest(p) for p in paths},
        center_source_sha256=digest(previous),
        center=[center["latitude"], center["longitude"]],
        estimator_sha256=digest(REPORTS / "2026_09_27_ds6_exact_timing/robust.py"),
        search_source_sha256=digest(Path(__file__)),
        scales_deg=[0.05, 0.0125, 0.003125], grid_side=7,
        model="Frozen Student-t4 scale100Hz; training-profiled per-track offsets",
        timing="Shared -5..5 seconds, quarter-second grid, marginalized across tracks",
        selection="All four pre-existing hash-selected rate-stratified scans; no replacements",
        partitions="Existing whole-visit randomized assignments; evaluation never ranks locations",
        scope="Conditional local transfer from an inferred development-scan position; no reference loaded",
    )
    path = HERE / "protocol.json"
    with path.open("x") as f:
        json.dump(protocol, f, indent=2)


def site(lat, lon):
    a, b = np.radians([lat, lon])
    return geodetic_to_ecef_km(lat, lon, 0), np.array([
        np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a),
    ])


def run(session):
    started = time.monotonic()
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert digest(Path(__file__)) == protocol["search_source_sha256"]
    assert digest(REPORTS / "2026_09_27_ds6_exact_timing/robust.py") == protocol["estimator_sha256"]
    source = REPORTS / "2026_09_27_ds6_common_rate_validation" / f"{session}-plan.json"
    assert digest(source) == protocol["inputs"][source.name]
    data = json.loads(source.read_text())
    tracks = []
    for row in data["tracks"]:
        t = dict(row, t=np.array(row["times_s"]), y=np.array(row["measured_hz"]),
                 mask=np.array(row["training_mask"], dtype=bool))
        if t["mask"].sum() >= 2 and (~t["mask"]).sum() >= 1:
            tracks.append(t)
    assert tracks
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snap = archive.select_latest_before(data["start_utc_ns"] - 505_000_000_000)
    assert snap.digest == data["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snap))
    cat = parse_element_sets(payload)
    taus = np.arange(-5., 5.001, .25)
    nodes = np.arange(np.floor(min(t["t"].min() for t in tracks)) - 6,
                      np.ceil(max(t["t"].max() for t in tracks)) + 7)
    pos, vel, ids = propagate_candidate_states(
        cat, np.arange(len(cat.satellite_numbers)), data["start_utc_ns"], nodes, np.array([0.]))
    pos, vel = pos[:, 0], vel[:, 0]
    center = protocol["center"]
    output = HERE / f"{session}.json"
    if output.exists():
        raise FileExistsError(output)
    stages = []
    for stage, width in enumerate(protocol["scales_deg"]):
        coordinates = [(float(a), float(b))
                       for a in np.linspace(center[0] - width, center[0] + width, 7)
                       for b in np.linspace(center[1] - width, center[1] + width, 7)]
        selected = {t["track_id"]: set() for t in tracks}
        minimum_mass = 1.
        for lat, lon in [tuple(center), coordinates[0], coordinates[6], coordinates[-7], coordinates[-1]]:
            rec, up = site(lat, lon)
            delta = pos - rec
            unit = delta / np.linalg.norm(delta, axis=-1)[..., None]
            elevation = unit @ up
            active = np.flatnonzero(np.any(elevation >= 0, axis=1))
            pred = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(unit[active] * vel[active], axis=-1)
            for t in tracks:
                q = t["t"][None, :] + taus[:, None] - nodes[0]
                lo = np.floor(q).astype(int)
                w = q - lo
                predicted = pred[:, lo] * (1-w) + pred[:, lo+1] * w
                visible = np.any((elevation[active][:, lo] * (1-w)
                                  + elevation[active][:, lo+1] * w)[:, :, t["mask"]] >= 0, axis=-1)
                score = np.where(visible, robust_scores(t["y"][None, None, :] - predicted, t["mask"])[0], -np.inf)
                chosen = np.argsort(score, axis=0)[-8:]
                selected[t["track_id"]].update(ids[active[chosen.ravel()]].tolist())
                mass = np.exp(logsumexp(np.take_along_axis(score, chosen, axis=0), axis=0)
                              - logsumexp(score, axis=0))
                minimum_mass = min(minimum_mass, float(mass.min()))
        banks = {t["track_id"]: propagate_candidate_states(
            cat, np.array(sorted(selected[t["track_id"]])), data["start_utc_ns"], t["t"], taus)
            for t in tracks}
        rows = []
        for lat, lon in coordinates:
            rec, up = site(lat, lon)
            train, joint = [], []
            for t in tracks:
                p, v, _ = banks[t["track_id"]]
                delta = p - rec
                unit = delta / np.linalg.norm(delta, axis=-1)[..., None]
                pred = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(unit * v, axis=-1)
                visible = np.any((unit @ up)[:, :, t["mask"]] >= 0, axis=-1)
                a, b = robust_scores(t["y"][None, None, :] - pred, t["mask"])
                train.append(logsumexp(np.where(visible, a, -np.inf), axis=0)-np.log(len(ids)))
                joint.append(logsumexp(np.where(visible, b, -np.inf), axis=0)-np.log(len(ids)))
            a, b = np.sum(train, axis=0), np.sum(joint, axis=0)
            rows.append(dict(latitude=lat, longitude=lon,
                             train=float(logsumexp(a)-np.log(len(taus))),
                             held=float(logsumexp(b)-logsumexp(a)),
                             map_time_s=float(taus[np.argmax(a)])))
        best = max(rows, key=lambda r: r["train"])
        boundary = (best["latitude"] in (coordinates[0][0], coordinates[-1][0])
                    or best["longitude"] in (coordinates[0][1], coordinates[-1][1]))
        stages.append(dict(stage=stage, center=center, width_deg=width, rows=rows,
                           best=best, boundary=boundary, minimum_anchor_top8_mass=minimum_mass,
                           shortlists={key: sorted(value) for key, value in selected.items()}))
        result = dict(session_id=session, complete=stage == 2, stages=stages,
                      input_sha256=digest(source), protocol_sha256=digest(HERE / "protocol.json"),
                      tracks=len(tracks), excluded_tracks=len(data["tracks"])-len(tracks),
                      elapsed_s=time.monotonic()-started)
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(dict(session=session, stage=stage, best=best, boundary=boundary,
                              elapsed_s=result["elapsed_s"])), flush=True)
        center = [best["latitude"], best["longitude"]]
        if boundary:
            print("Boundary optimum: stopping rather than claiming local convergence", flush=True)
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--session")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        run(args.session)
