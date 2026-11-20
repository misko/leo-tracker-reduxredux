"""Challenge a four-offer Doppler nomination with a longitude rotation test."""

import json
from pathlib import Path
from time import perf_counter

from ..reference import grid, receiver
from . import arc_validation

BOUNDARY = "Anonymous Doppler tracks and causal TLEs through endpoint and longitude controls"
ROTATION_COUNT = 20
NULL_REJECTION = "outside_longitude_control_matches"


def _usable_nomination(nomination):
    return (
        nomination is not None
        and nomination["training_score"] >= receiver.MIN_SHAPE_SCORE
        and nomination["held_score"] >= receiver.MIN_SHAPE_SCORE
        and nomination["held_orbits"] >= arc_validation.MIN_ORBITS
    )


def _rotated_offers(offered, step):
    shift = step * (360.0 / ROTATION_COUNT)
    return [(lat, (lon + shift + 180.0) % 360.0 - 180.0) for _, (lat, lon) in offered]


def _longitude_control(observation, regions, catalog, observed_score):
    offered = receiver._offered_regions(regions)
    tracks = receiver._screen_tracks(observation["tracks"], float(observation["duration_s"]))
    usable = [track for track in tracks if len(track["times"]) >= 6][: receiver.MAX_TRACKS]
    sky = grid.prepare_sky(observation, catalog)
    max_score, tests = 0.0, 0
    for step in range(1, ROTATION_COUNT):
        for center in _rotated_offers(offered, step):
            tests += 1
            nomination = arc_validation._nomination(grid.make_tile(sky, center), usable)
            if not _usable_nomination(nomination):
                continue
            score = nomination["held_score"]
            max_score = max(max_score, score)
            if score >= observed_score - receiver.TIE_TOLERANCE:
                return dict(
                    veto=True,
                    null_tiles_tested=tests,
                    max_seen_held_score=max_score,
                    witness_step=step,
                    witness_center=list(center),
                )
    return dict(veto=False, null_tiles_tested=tests, max_seen_held_score=max_score)


def _result(winner, reason, evidence, boundary, elapsed):
    arm = dict(latlon=None, forced_latlon=None if winner is None else winner["latlon"])
    if reason == "accepted":
        arm.update(latlon=winner["latlon"], rf_rms_hz=winner["held_rms_hz"])
    return dict(
        status="ok" if reason == "accepted" else "withheld",
        boundary=boundary,
        reason=reason,
        metrics=dict(evidence, candidate_s=elapsed),
        # The same track-relative frequency is used at nominal RF in both arms.
        arms=dict(c0=dict(arm), fitted_c=dict(arm)),
    )


def compare(observation, regions, catalog):
    """Run original arc validation and challenge any region that passed its check."""
    started = perf_counter()
    winner, reason, evidence = arc_validation.solve(observation, regions, catalog)
    baseline = _result(winner, reason, evidence, arc_validation.BOUNDARY, perf_counter() - started)
    evidence = dict(evidence)
    if evidence.get("region_accepted", False):
        control = _longitude_control(observation, regions, catalog, winner["held_score"])
        evidence["longitude_control"] = control
        if control["veto"]:
            reason = NULL_REJECTION
            evidence["region_accepted"] = False
    return baseline, _result(winner, reason, evidence, BOUNDARY, perf_counter() - started)


def run(case, work_dir):
    if not case.get("observation_path") or not case.get("catalog_path"):
        return dict(
            status="unavailable",
            reason="missing_observation_or_catalog",
            boundary=BOUNDARY,
            metrics={},
        )
    try:
        observation = json.loads(Path(case["observation_path"]).read_bytes())
        catalog = Path(case["catalog_path"]).read_bytes()
        _, candidate = compare(observation, case["regions"], catalog)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        return dict(
            status="unavailable",
            reason=f"invalid_input: {error}",
            boundary=BOUNDARY,
            metrics={},
        )
    return candidate
