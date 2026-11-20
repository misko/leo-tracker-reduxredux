"""Positive Doppler geometry control under correct ephemeris timing."""

import argparse
from functools import partial
from pathlib import Path

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km

from ..__main__ import ROOT, local_output, save_json
from ..scoring import distance_km
from ..variants import session_geometry as model
from . import session_geometry_simulation as stress
from . import session_geometry_trial as trial
from .full_v5_check import _sha

SEED = 90701
OFFSET_KM = (4.0, -4.5)
MAX_ERROR_KM = 1.0


def nominal_observations(truth):
    rng = np.random.default_rng(SEED)
    receiver = geodetic_to_ecef_km(*truth)
    captures = []
    for ordinal in range(10):
        tracks = []
        for j in range(2):
            times = np.arange(0.0, 201 + 10 * j)
            elapsed = times - times.mean() + rng.uniform(-40, 40)
            bearing = (137.508 * ordinal + 75 * j) % 360
            cross, altitude = rng.uniform(-350, 350), rng.uniform(510, 570)

            states = partial(stress.circular_states, stress.ORIGIN, bearing, cross, altitude)
            pos, vel = states(elapsed)
            step_s = 0.01
            early = np.linalg.norm(states(elapsed - step_s)[0] - receiver, axis=-1)
            late = np.linalg.norm(states(elapsed + step_s)[0] - receiver, axis=-1)
            independent_rate = (late - early) / (2 * step_s)
            doppler = -model.RF_HZ / model.LIGHT_KM_S * independent_rate
            receiver_clock = rng.uniform(-25000, 25000) + rng.uniform(-3, 3) * elapsed
            measured = doppler + receiver_clock + rng.normal(0, 40, len(elapsed))
            quantized = np.round(measured / model.BIN_HZ) * model.BIN_HZ
            tracks.append(model.Arc(times, quantized, pos, vel))
        captures.append(
            model.Capture(f"nominal-{ordinal + 1:02d}", str(1 + ordinal // 5), tuple(tracks))
        )
    return captures


def check(out):
    seal = out / "nominal-plan-lock.json"
    if seal.exists():
        raise FileExistsError("preserve the nominal simulation seal")
    truth = [*model.geographic(stress.ORIGIN, OFFSET_KM).tolist(), model.HEIGHT_M]
    captures = nominal_observations(truth)
    hashes = {capture.id: trial.observation_hash(capture) for capture in captures}
    offer = model.offer(stress.ORIGIN, "containing")
    save_json(
        seal,
        dict(
            seed=SEED,
            max_forced_error_km=MAX_ERROR_KM,
            observations=hashes,
            offer=offer,
            parent_prediction_lock_sha256=_sha(out / trial.LOCK),
            source_files={
                str(path.relative_to(ROOT)): _sha(path)
                for path in (
                    Path(__file__),
                    Path(model.__file__),
                    Path(stress.__file__),
                    Path(trial.__file__),
                )
            },
            scenario="Nominal orbit timing. CFO from finite-differenced slant range.",
        ),
    )
    predictions, _, resources = trial.evaluate(
        "simulation",
        captures,
        {"containing": offer},
        stress.ORIGIN,
        hashes,
    )
    prediction = out / "nominal-predictions.json"
    save_json(
        prediction, dict(plan_sha256=_sha(seal), predictions=predictions, resources=resources)
    )
    endpoints = []
    for row in predictions:
        point = row["result"]["arms"]["c0"]
        endpoints.append(
            dict(
                method=row["method"],
                held_visit=row["recording"],
                status=row["result"]["status"],
                forced_error_km=distance_km(point["forced_latlon"], truth[:2]),
                published_error_km=distance_km(point["latlon"], truth[:2]),
            )
        )
    positive = [a for a in endpoints if a["method"] == "phase-clock"]
    save_json(
        out / "nominal-score.json",
        dict(
            passed=len(positive) == 2
            and all(a["forced_error_km"] <= MAX_ERROR_KM for a in positive),
            prediction_sha256=_sha(prediction),
            survey_wgs84=truth,
            endpoints=endpoints,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.OUT)
    check(parser.parse_args().out)


if __name__ == "__main__":
    main()
