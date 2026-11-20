"""Score sealed complete and interleaved capture-era GLRT inputs on the same roof recordings."""

import argparse
from pathlib import Path

from ..__main__ import implementation_digest, local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import interleaved_trial as trial
from .full_receiver_comparison import read, require_fields, roster_matches, seal, sha
from .prefix_figures import csv_file


def publish(source, out):
    files = ("plan.json", "positions.jsonl.gz", "stock.jsonl.gz")
    proof = seal(source, "prediction-lock.json", files)
    plan = read(source / "plan.json")
    require_fields(
        plan,
        dict(
            cases=trial.roster(trial.baseline.frozen_inputs()),
            stock=sha(source / "stock.jsonl.gz"),
            protocol=sha(trial.REPORT / "PROTOCOL.md"),
            policy=implementation_digest(trial.policy.METHOD, Path(trial.policy.__file__)),
            trial=sha(Path(trial.__file__)),
        ),
    )
    if proof["cases"] != plan["cases"]:
        raise ValueError("predictions and prelaunch schedule disagree")
    refs = trial.baseline._frozen_roof()[0]
    full = read_predictions(source / "stock.jsonl.gz")
    replay = read_predictions(source / "positions.jsonl.gz")
    for data in (full, replay):
        roster_matches(data, plan["cases"], "interleaved recording set")
    scores = []
    for ident in plan["cases"]:
        common = {k: plan["bindings"][ident][k] for k in trial.baseline.MATCH}
        for row, method in ((full[ident], "v5_secant_fit"), (replay[ident], trial.policy.METHOD)):
            require_fields(row, dict(method=method, **common))
            result = row["result"]
            validate_result(result)
            if method == trial.policy.METHOD and result["status"] == "ok":
                require_fields(row, dict(implementation_sha256=plan["policy"]))
                metrics = result["metrics"]
                if sum(metrics["retained_by_channel"]) != metrics["retained_visits"]:
                    raise ValueError("channel counts disagree with the total retained visits")
        for arm in ARMS:
            a = replay[ident]["result"].get("arms", {}).get(arm, {})
            b = full[ident]["result"].get("arms", {}).get(arm, {})
            metrics = replay[ident]["result"]["metrics"]
            scores.append(
                dict(
                    id=ident,
                    subset="example" if ident in trial.EXAMPLES else "confirmation",
                    arm=arm,
                    status=replay[ident]["result"]["status"],
                    error_km=distance_km(a.get("latlon"), refs[ident]["truth"]),
                    stock_error_km=distance_km(b.get("latlon"), refs[ident]["truth"]),
                    original_error_km=refs[ident]["reference"]["baseline"][arm].get("error_km"),
                    rf_rms_hz=a.get("rf_rms_hz"),
                    stock_rf_rms_hz=b.get("rf_rms_hz"),
                    valid_visits=metrics.get("valid_visits"),
                    retained_visits=metrics.get("retained_visits"),
                    worker_wall_s=replay[ident]["worker_wall_s"],
                )
            )
    if source != out:
        for name in (*files, "prediction-lock.json"):
            write(out / name, (source / name).read_bytes())
    csv_file(out / "scores.csv", scores)
    save_json(
        out / "figure-lock.json",
        dict(
            cases=plan["cases"],
            files={n: sha(out / n) for n in (*files, "prediction-lock.json", "scores.csv")},
        ),
    )
    series = [
        dict(
            key="one",
            label="Three of four visits per channel",
            file=files[1],
            value=trial.policy.METHOD,
        ),
        dict(
            key="stock",
            label="All visits · compact v5",
            file=files[2],
            value="v5_secant_fit",
            match=list(trial.baseline.MATCH),
        ),
    ]
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="interleaved-visits-roof6",
                    method=trial.policy.METHOD,
                    scope="roof",
                    title="Skip one in four visits on every RF channel",
                    caption="Complete five-minute capture-era GLRT records, full-clock tracking "
                    "and the same compact solver. Four recording IDs were drawn by hash.",
                    cases=plan["cases"],
                    seal="figure-lock.json",
                    series=series,
                    provenance=["prediction-lock.json", "plan.json", "scores.csv"],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-work", type=Path, default=trial.REPORT)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    publish(local_output(args.from_work), local_output(args.out))
