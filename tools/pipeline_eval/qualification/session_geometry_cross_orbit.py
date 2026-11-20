"""Repeat the containing-offer fit with a different real orbit per training track."""

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicHermiteSpline

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import distance_km
from ..variants import session_geometry as model
from . import session_geometry_trial as trial
from .full_v5_check import _sha

HALF_WINDOW_S = 16


def paired_tracks(capture, donor):
    paired, wrong = [], []
    for i, arc in enumerate(capture.arcs):
        relative = arc.times_s - (arc.times_s[0] + arc.times_s[-1]) / 2
        sample = np.abs(relative) <= HALF_WINDOW_S
        clean = model.Arc(
            arc.times_s[sample],
            arc.frequency_hz[sample],
            arc.position_km[sample],
            arc.velocity_km_s[sample],
        )
        other = donor.arcs[i % len(donor.arcs)]
        donor_midpoint = (other.times_s[0] + other.times_s[-1]) / 2
        if (other.times_s[-1] - other.times_s[0]) / 2 < HALF_WINDOW_S or sample.sum() < 16:
            raise ValueError("tracks have insufficient support for the fixed mismatch window")
        curve = CubicHermiteSpline(other.times_s, other.position_km, other.velocity_km_s)
        shifted = relative[sample] + donor_midpoint
        paired.append(clean)
        wrong.append(replace(clean, position_km=curve(shifted), velocity_km_s=curve(shifted, 1)))
    return replace(capture, arcs=tuple(paired)), replace(capture, arcs=tuple(wrong))


def run(source, out):
    seal = out / "cross-orbit-plan-lock.json"
    if seal.exists():
        raise FileExistsError("preserve the cross-orbit control seal")
    parent = out / trial.LOCK
    for filename, digest in whole_iq.read(parent)["files"].items():
        whole_iq.checked(out / filename, digest)
    captures, members, _ = trial.load_ctu(source)
    original_plan = whole_iq.read(out / trial.PLAN)
    if members != original_plan["ctu_members"]:
        raise ValueError("mismatch control must use the original captures")
    tile = original_plan["offers"]["prague"]["containing"]
    visits = {
        visit: [c for c in captures if c.visit == visit]
        for visit in sorted({c.visit for c in captures})
    }
    matched, null = {}, {}
    pairings = []
    for day, set_ in visits.items():
        matches = list(zip(set_, set_[1:] + set_[:1], strict=True))
        pairs = [paired_tracks(c, donor) for c, donor in matches]
        matched[day], null[day] = zip(*pairs, strict=True)
        pairings.extend(dict(capture=c.id, donor=donor.id, visit=day) for c, donor in matches)
    save_json(
        seal,
        dict(
            parent_prediction_lock_sha256=_sha(parent),
            source_sha256=_sha(Path(__file__)),
            pairings=pairings,
            half_window_s=HALF_WINDOW_S,
            offer=tile,
            purpose="Post-release check with a distinct donor capture on the same date",
        ),
    )
    points = model.candidates(tile)
    predictions = []
    for mode, groups in (("matched", matched), ("wrong-pass", null)):
        for day, group in groups.items():
            held = next(others for visit, others in matched.items() if visit != day)
            costs = [
                model.capture_grid(c, points, trial.PRAGUE_ORIGIN, 0)["phase-clock"] for c in group
            ]
            pooled = np.mean(costs, axis=0)
            best = np.argmin(pooled)
            predictions.append(
                dict(
                    mode=mode,
                    train_visit=day,
                    point=points[best].tolist(),
                    train_rms_hz=float(np.sqrt(pooled[best])),
                    frequency=[dict(capture=c.id, **model.predict(c, points[best])) for c in held],
                )
            )
    pred = out / "cross-orbit-predictions.json"
    save_json(pred, dict(plan_sha256=_sha(seal), predictions=predictions))
    released = whole_iq.read(out / "survey-release.json")
    if released["prediction_lock_sha256"] != _sha(parent):
        raise ValueError("survey and cross-orbit prediction are bound to different trial inputs")
    truth = released["wgs84"]["prague"][:2]
    save_json(
        out / "cross-orbit-scores.json",
        dict(
            prediction_sha256=_sha(pred),
            rows=[
                dict(row, forced_error_km=distance_km(row["point"], truth)) for row in predictions
            ],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=local_output)
    parser.add_argument("--out", type=local_output, default=trial.OUT)
    args = parser.parse_args()
    run(args.source, args.out)


if __name__ == "__main__":
    main()
