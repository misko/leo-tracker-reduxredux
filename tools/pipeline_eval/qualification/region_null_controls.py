"""Replay the two sealed shuffled controls after a serialization-only format correction."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, read_predictions, save_json, write
from . import region_null_trial as trial


def recover(output, work, bundle):
    phase = trial.phase
    lock = phase._read(output / "prediction-lock.json")
    trial.base.clock.base.secant_full._verify_files(output, lock["files"])
    if phase._read(output / "source-lock.json") != trial.sources(bundle)[0]:
        raise ValueError("the original blind receiver sources have changed")
    plan = phase._read(output / "roster.json")
    records = read_predictions(output / f"{trial.METHOD}.jsonl.gz")
    queries = [q for q in plan["cases"] if q["cohort"] == "shuffled-native"]
    entries = []
    for query in queries:
        ident, packet = query["recording"], query["packet"]
        prior = records[query["id"]]
        original = work / f"{ident}.native.json"
        if (
            phase.digest(original) != packet["native"]["sha256"]
            or prior["result"]["status"] != "failed"
            or "unexpected native archive header" not in prior["result"]["reason"]
        ):
            raise ValueError("only the two sealed archive-header failures are eligible")
        corrected = work / f"{ident}.compact-native.json"
        write(corrected, encoded(phase._read(original)))
        assets = dict(
            native=corrected,
            catalogue=work / "catalogue.tle",
            track_config=work / "track-config.json",
        )
        fixed = query | {
            "packet": packet | {"native": packet["native"] | {"sha256": phase.digest(corrected)}}
        }
        if any(
            phase.digest(path) != fixed["packet"][key]["sha256"] for key, path in assets.items()
        ):
            raise ValueError("compact serialization changed an unrelated input")
        entries.append((fixed, assets))
    if len(entries) != 2:
        raise ValueError("exactly two sealed shuffled controls are expected")
    path = output / "shuffled-control-requests.json"
    save_json(
        path,
        dict(
            cases=[q for q, _ in entries],
            source_sha256=phase.digest(Path(__file__)),
            original_prediction_sha256=phase.digest(output / "prediction-lock.json"),
            rationale="Identical JSON objects encoded as compact key-ordered native archives",
        ),
    )

    def launch(entry, cpu):
        return trial.base.attempt(*entry, bundle, cpu)

    with (
        patch.object(trial.base, "command", trial.command),
        patch.object(trial.base, "METHOD", trial.METHOD),
        ThreadPoolExecutor(2) as pool,
    ):
        fixed = list(pool.map(launch, entries, trial.CPUS))
    name = "shuffled-controls.jsonl.gz"
    corrected_sha = trial.base.pack(output, name, fixed)
    save_json(
        output / "shuffled-control-lock.json",
        dict(
            cases=[r["id"] for r in fixed],
            files={name: corrected_sha, path.name: phase.digest(path)},
        ),
    )


if __name__ == "__main__":
    recover(trial.REPORT, trial.WORK, trial.base.clock.base.BUNDLE)
