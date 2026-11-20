"""Challenge the locked receiver at a fresh simulated site with smooth clock drift."""

import argparse
import hashlib
import json
import secrets
from pathlib import Path

import numpy as np

from ..__main__ import encoded
from ..scoring import ARMS, distance_km
from . import clock_model_trial as trial
from . import cold_scenes as cold
from . import fresh_scenes as offers
from . import joint_orbits_inputs as inputs
from . import site_transfer_samples as generator
from .clock_model_worker import FIXED_CONTROL
from .full_v5_check import _sha
from .recording_to_v5 import save

PERIODS_S = np.array([95.0, 180.0])
AMPLITUDES_HZ = np.array([180.0, 120.0])


def oscillator(times, phases):
    grid = np.arange(301.0)

    def affine(t):
        return np.column_stack((np.ones(len(t)), (t - 150.0) / 150.0))

    def thermal(t):
        return np.sin(2 * np.pi * t[:, None] / PERIODS_S + phases) @ AMPLITUDES_HZ

    affine_clock = np.linalg.lstsq(affine(grid), thermal(grid), rcond=None)[0]
    return thermal(times) - affine(times) @ affine_clock


def prepare(work):
    work.mkdir(mode=0o700)
    seed = secrets.token_bytes(32)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    catalogue, received = generator._catalogue()
    site = np.array([11.0, -18.0]) + rng.uniform(-5.0, 5.0, 2)
    anchor = received + 4230 * cold.NS
    constellation = cold._constellation(catalogue, received)
    native, counter, _ = cold._generate_capture(constellation, anchor, site, rng)
    document = dict(
        case_id=rng.bytes(12).hex(), probes=native, sample_rate_hz=cold.RATE,
        probe_ms=cold.PROBE_MS, first_counter=counter, anchor_utc_ns=anchor,
        cutoff_utc_ns=anchor, catalog_timestamp_ns=received, duration_s=cold.SECONDS,
    )
    bearing = rng.uniform(0.0, 2 * np.pi)
    center = offers._destination(site, rng.uniform(8.0, 10.0), bearing)
    wrong = offers._destination(site, rng.uniform(40.0, 55.0), bearing)
    phases = rng.uniform(0.0, 2 * np.pi, (2, len(PERIODS_S)))
    plain_offer = dict(id=rng.bytes(12).hex(), center=center, width_km=25.0)
    plain = inputs._synthetic(document, catalogue, plain_offer, "clock-free")
    plain_observation = plain["packet"]["observation"]
    drifted = dict(plain_observation, tracks=[
        dict(track, values=(
            np.asarray(track["values"]) + track["rf_hz"] / 11.5e9
            * oscillator(np.asarray(track["times"]), phases[track["receiver"] - 1])
        ).tolist())
        for track in plain_observation["tracks"]
    ])
    rows = [plain]
    for cohort, coord in (("clock-injected", center), ("outside-offer", wrong)):
        offer = dict(id=rng.bytes(12).hex(), center=coord, width_km=25.0)
        rows.append(dict(
            plain, id=offer["id"], cohort=cohort,
            observation_sha256=hashlib.sha256(encoded(drifted)).hexdigest(),
            packet=dict(plain["packet"], observation=drifted, offer=offer),
        ))
    for row in rows:
        row["input_sha256"] = hashlib.sha256(encoded(row["packet"])).hexdigest()
        row["tile"] = row["packet"]["offer"]
    save(work / "private.json", dict(seed=seed.hex(), truth=site.tolist(), phases=phases.tolist()))
    save(work / "cases.json", rows)
    save(work / "plan.json", dict(
        primary=trial.seal(), source_sha256=_sha(Path(__file__)),
        cases_sha256=_sha(work / "cases.json"), private_sha256=_sha(work / "private.json"),
        periods_s=PERIODS_S.tolist(), amplitudes_hz=AMPLITUDES_HZ.tolist(),
    ))


def run(work, output):
    plan_file = work / "plan.json"
    plan = json.loads(plan_file.read_bytes())
    if (
        trial.seal() != plan["primary"] or _sha(Path(__file__)) != plan["source_sha256"]
        or _sha(work / "cases.json") != plan["cases_sha256"]
        or _sha(work / "private.json") != plan["private_sha256"]
    ):
        raise ValueError("synthetic cases or exact receiver changed")
    cases = json.loads((work / "cases.json").read_bytes())
    methods = trial.joint_clock_model.METHOD, FIXED_CONTROL, "joint_orbits"
    output.mkdir(parents=True, exist_ok=False)
    for method in methods:
        rows = [trial.attempt(row, method, trial.CPUS[i % 2]) for i, row in enumerate(cases)]
        trial._gzip(output / f"{method}.jsonl.gz", rows)
    save(output / "prediction-lock.json", dict(
        cases=[r["id"] for r in cases], plan_sha256=_sha(plan_file),
        files={file.name: _sha(file) for file in output.glob("*.jsonl.gz")},
    ))
    hidden = json.loads((work / "private.json").read_bytes())
    scores = []
    for method in methods:
        pairs = trial.read_predictions(output / f"{method}.jsonl.gz")
        for ident, row in pairs.items():
            for arm in ARMS:
                info = row["result"]["arms"][arm]
                scores.append(dict(
                    id=ident, cohort=row["cohort"], arm=arm, variant=method,
                    status=row["result"]["status"],
                    error_km=distance_km(info["latlon"], hidden["truth"]),
                    forced_error_km=distance_km(info.get("forced_latlon"), hidden["truth"]),
                    in_sample_rf_rms_hz=info.get("rf_rms_hz"),
                    held_rf_rms_hz=row["result"]["metrics"].get(
                        "held_by_arm", {}
                    ).get(arm, {}).get("held_rf_rms_hz"),
                ))
    save(output / "scores.json", scores)
    save(output / "plan.json", plan)
    save(output / "synthetic-truth.json", hidden)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work", type=Path, default=Path("/tmp/leo-joint-clock-synthetic-20261119")
    )
    parser.add_argument("--output", type=Path, default=trial.REPORT / "synthetic")
    args = parser.parse_args()
    prepare(args.work)
    run(args.work, args.output)
