"""Score the frozen held selection on its separate DS26 and DS29 reference panels."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from .. import corpus
from ..__main__ import local_output, save_json
from ..scoring import ARMS
from . import full_held_pair as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file


def held_references(_panel, cases):
    sources = {"DS26": "ds26-all159", "DS29": "roof16"}
    all_cases = {}
    for group, source in sources.items():
        all_cases.update((r["id"], r) for r in corpus.references(source) if r["group"] == group)
    missing = set(cases) - all_cases.keys()
    if missing:
        raise ValueError(
            f"held recording has no authorized geographic reference: {sorted(missing)}"
        )
    return "ds26-all159+roof16", [all_cases[ident] for ident in cases]


def publish(runs, report):
    with patch.object(trial, "references", held_references):
        trial.publish(runs, report)
    cases = json.loads((report / "prediction-lock.json").read_bytes())["cases"]
    pins = json.loads((report / "source-lock.json").read_bytes())["inputs"]
    _, older = held_references("roof16", cases)
    records = []
    for reference in older:
        ident = reference["id"]
        for mode in ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks"):
            for arm in ARMS:
                fit = reference["reference"][mode][arm]
                latitude, longitude = fit.get("latlon") or (None, None)
                records.append(
                    dict(
                        id=ident,
                        mode=mode,
                        arm=arm,
                        status=fit["status"],
                        capture_era_native_sha256=pins[ident]["capture_era_native_sha256"],
                        latitude=latitude,
                        longitude=longitude,
                        error_km=fit.get("error_km"),
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        archived_wall_s=fit.get("wall_s"),
                    )
                )
    historical = report / "capture-era-v5.csv"
    csv_file(historical, records)
    save_json(
        report / "score-lock.json",
        dict(
            files={name: _sha(report / name) for name in ("scores.csv", historical.name)},
            exporter_sha256=_sha(Path(__file__)),
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=local_output, default=trial.RUNS)
    args = parser.parse_args()
    publish(args.runs, trial.REPORT)
