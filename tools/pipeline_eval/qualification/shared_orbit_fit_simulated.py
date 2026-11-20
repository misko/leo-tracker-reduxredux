"""Rebuild native Graph for an opaque-ID offsite simulated capture."""

import argparse
import json
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded
from ..scoring import ARMS, distance_km, validate_result
from . import shared_orbit_fit_trial as trial
from .clock_model_trial import _gzip
from .full_v5_check import _sha
from .recording_to_v5 import save


def run(panel, output, bundle):
    authority = trial.prior.SCREENING / "recovery/clock-transfer/input-lock.json"
    seal = json.loads(authority.read_bytes())
    if any(_sha(panel / name) != digest for name, digest in seal["public"].items()):
        raise ValueError("published simulated factor or catalogue differs from its seal")
    public = panel / "public"
    requests = json.loads((public / "requests.json").read_bytes())
    captures = {r["capture_id"] for r in requests}
    chosen = min(
        (capture for capture in captures if sum(r["capture_id"] == capture for r in requests) >= 3),
        key=trial.rank,
    )
    selected = [r for r in requests if r["capture_id"] == chosen]
    if len(selected) != 4:
        raise ValueError("expected the sealed four offers for one offsite capture")
    output.mkdir()
    save(output / "plan.json", dict(
        source=trial.prepare(bundle)[0]["source_files"], source_receipt_sha256=_sha(authority),
        cases=selected, capture=chosen, cpu=4,
    ))
    rows = []
    for query in selected:
        packet = query["packet"]
        paths = dict(
            native=public / f"{chosen}.json",
            catalogue=public / f"{packet['catalogue']['sha256']}.tle",
            track_config=public / "track-config.json",
        )
        start = perf_counter()
        call = subprocess.run(
            trial.command(4, paths, bundle), input=encoded(packet),
            capture_output=True, check=True, timeout=60,
        )
        row = json.loads(call.stdout)
        validate_result(row["result"])
        rows.append(dict(id=query["id"], wall_s=perf_counter() - start, **row))
    path = output / "predictions.jsonl.gz"
    _gzip(path, rows)
    save(output / "prediction-lock.json", dict(
        cases=[r["id"] for r in rows], plan_sha256=_sha(output / "plan.json"),
        files={path.name: _sha(path)},
    ))
    truth_path = panel / "private/truth.json"
    if _sha(truth_path) != seal["private"]["private/truth.json"]:
        raise ValueError("the simulated scoring references differ from their sealed values")
    truth = json.loads(truth_path.read_bytes())
    scored = []
    for row in rows:
        label = truth[row["id"]]
        for method, fit in row["variants"].items():
            for arm in ARMS:
                r = fit["result"]
                endpoint = r["arms"][arm]
                scored.append(dict(
                    id=row["id"], method=method, arm=arm, condition=label["condition"],
                    margin_km=label["margin_km"], status=r["status"], reason=r["reason"],
                    error_km=distance_km(endpoint["latlon"], label["latlon"]),
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), label["latlon"]),
                ))
    save(output / "scores.json", scored)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=trial.REPORT / "simulated")
    parser.add_argument("--bundle", type=Path, default=trial.base.base.BUNDLE)
    args = parser.parse_args()
    run(args.panel, args.output, args.bundle)
