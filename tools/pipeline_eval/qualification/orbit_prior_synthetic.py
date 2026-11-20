"""Fresh synthetic geography with the measured donor's genuine orbit history."""

import argparse
import secrets
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json
from ..scoring import distance_km
from ..variants import robust_em as lean
from . import cold_scenes as cold
from . import orbit_prior_trial as trial
from . import site_transfer_samples as generated
from .fresh_scenes import _destination
from .robust_em_trials import load

DONOR = "DS26-0197"
BOXES = ((2, -55), (-32, 24))


def fixed_rows(observation, picked):
    frequencies = {}
    for track in observation["tracks"]:
        rf = track["rf_hz"]
        for t in track["times"]:
            key = track["receiver"], track["channel"], round(t, 6)
            frequencies.setdefault(key, set()).add(rf)
    result = []
    for point in picked:
        t, number, rx, ch = (point[k] for k in ("time_s", "norad", "receiver", "channel"))
        choices = frequencies[rx, ch, round(t, 6)]
        if len(choices) != 1:
            continue
        result.append(
            dict(
                v5_owner=number,
                lean_owner=number,
                lean_track=point["track"],
                component=f"synthetic-track-{point['track']}",
                time_s=t,
                rx=rx,
                channel=ch,
                rf_hz=next(iter(choices)),
                folded_hz=float(lean.fold(point["cfo_hz"])),
                lean_lift=point["lean_lift"],
            )
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    output = local_output(args.work)
    output.mkdir(parents=True, exist_ok=False)
    paths = (
        Path(__file__),
        Path(trial.__file__),
        Path(cold.__file__),
        Path(generated.__file__),
        trial.REPORT / "source-lock.json",
    )
    save_json(
        output / "source-lock.json",
        {str(p.relative_to(ROOT)): trial.digest(p.read_bytes()) for p in paths},
    )
    seed = secrets.token_bytes(32)
    (output / "seed.hex").write_text(seed.hex() + "\n")
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    donor, _ = load(DONOR, "matched-tile", output / "cache")
    authority = donor["observation"]
    anchor, cutoff, collected = (
        authority[k] for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns")
    )
    sky = cold._constellation(donor["catalogue"].encode("ascii"), collected)
    queries, labels = [], {}
    for box in BOXES:
        ident = rng.bytes(10).hex()
        position = np.asarray(box) + rng.uniform(-3, 3, size=2)
        probes, counter, _emitters = cold._generate_capture(sky, anchor, position, rng)
        observation = generated.projection(
            SimpleNamespace(
                probes=probes,
                first_counter=counter,
                sample_rate_hz=cold.RATE,
                probe_ms=cold.PROBE_MS,
                anchor_utc_ns=anchor,
                cutoff_utc_ns=cutoff,
                catalog_timestamp_ns=collected,
                duration_s=cold.SECONDS,
            )
        )
        offer = dict(
            id=ident,
            width_km=25,
            center=_destination(position, rng.uniform(8.0, 10.0), rng.uniform(0.0, 2 * np.pi)),
        )
        labels[ident] = position.tolist()
        queries.append(
            (ident, dict(observation=observation, catalogue=donor["catalogue"], offer=offer))
        )
    save_json(output / "private-labels.json", labels)
    results = []
    for i, (ident, packet) in enumerate(queries):
        chosen = trial.worker("blind", packet, 15)["rows"]
        rows = fixed_rows(packet["observation"], chosen)
        prior, history = trial.load_history(DONOR, packet, {row["lean_owner"] for row in rows})
        order = ("equal", "history") if i == 0 else ("history", "equal")
        request = dict(packet=packet, rows=rows, prior=prior, order=order)
        result = trial.worker("fit", request, 15)
        results.append(
            dict(
                id=ident,
                result=result,
                prior=prior,
                history=history,
                input_sha256=trial.digest(encoded(request)),
            )
        )
        print(ident, result["status"], flush=True)
    predictions = output / "predictions.json"
    save_json(predictions, results)
    save_json(
        output / "prediction-lock.json",
        dict(
            predictions_sha256=trial.digest(predictions.read_bytes()),
            truth_sha256=trial.digest((output / "private-labels.json").read_bytes()),
            source_sha256=trial.digest((output / "source-lock.json").read_bytes()),
        ),
    )
    scores = []
    for result in results:
        truth = labels[result["id"]]
        for method, fit in result["result"].get("methods", {}).items():
            for arm, row in fit["arms"].items():
                scores.append(
                    dict(
                        id=result["id"],
                        method=method,
                        arm=arm,
                        **row,
                        error_km=distance_km(truth, row["forced_latlon"]),
                    )
                )
    save_json(output / "scores.json", scores)


if __name__ == "__main__":
    main()
