"""Score sealed compact transfer and the matched sealed native control."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import clock_offset_results, screening_figures
from . import compact_transfer as trial
from .fresh_scenes import _read, _sha

COMPACT = "predictions.jsonl.gz"
FIGURE_COMPACT = "figure-compact-positions.jsonl.gz"
CONTROL = "matched-clock-control.jsonl.gz"
METHOD = "native_clock_offset_ou"
LABELS = {
    "original": "Correct tile supplied",
    "far-outside": "Correct region omitted",
    "authentic": "Measured roof · supplied tile shifted east",
}
FIELDS = ("native_sha256", "catalog_sha256")
ARCHIVE_FILES = ("prediction-lock.json", "requests.json", "source-lock.json", COMPACT)
MEASURED_RECEIPT = "measured-replay-receipt.json"


def _records(path):
    with gzip.open(path, "rt") as stream:
        rows = list(map(json.loads, stream))
    records = {row["id"]: row for row in rows}
    if len(rows) != len(records):
        raise ValueError("predictions contain repeated queries")
    return records


def bindings(compact, control):
    return compact["tile"] == control["tile"] and all(compact[k] == control[k] for k in FIELDS)


def measured_replay(output, initial):
    retry = output / "measured-retry"
    lock_path = retry / "prediction-lock.json"
    if not lock_path.is_file():
        return initial
    seal = _read(lock_path)
    if any(_sha(retry / name) != sha for name, sha in seal.items()):
        raise ValueError("measured retry changed after its independent prediction seal")
    source = _read(retry / "source-lock.json")
    replay = _read(retry / "prediction.json")
    if (
        initial["result"]["status"] != "failed"
        or initial["trace"]
        or source["primary_sha256"] != _sha(output / "prediction-lock.json")
        or source["worker_input_sha256"] != replay["worker_input_sha256"]
        or not bindings(replay, initial)
        or any(replay[k] != initial[k] for k in ("id", "worker_input_sha256", "history_sha256"))
    ):
        raise ValueError("measured retry did not preserve the pre-inference failed request")
    save_json(
        output / MEASURED_RECEIPT,
        dict(
            worker_input_sha256=replay["worker_input_sha256"],
            retry_prediction_lock_sha256=_sha(lock_path),
            files=seal,
        ),
    )
    return replay


def score(output, baseline):
    seal = _read(output / "prediction-lock.json")
    if any(_sha(output / name) != sha for name, sha in seal["files"].items()):
        raise ValueError("compact predictions changed after the worker seal")
    records = _records(output / COMPACT)
    if set(records) != set(seal["cases"]):
        raise ValueError("compact prediction roster differs from its seal")
    records[trial.ROOF] = measured_replay(output, records[trial.ROOF])
    earlier = _read(baseline / "prediction-lock.json")
    public = _read(baseline / "input-lock.json")
    if (
        earlier["predictions_sha256"] != _sha(baseline / COMPACT)
        or earlier["input_lock_sha256"] != _sha(baseline / "input-lock.json")
        or public["private"]["private/truth.json"] != _sha(baseline / "truth.json")
    ):
        raise ValueError("cold control differs from its original pre-score seal")
    control = clock_offset_results._models(_records(baseline / COMPACT), {})[METHOD]
    truth = _read(baseline / "truth.json")
    sites = [ident for pair in trial.CASES for ident in pair]
    selected = {ident: control[ident] for ident in sites}
    if set(records) != set(sites) | {trial.ROOF} or any(
        not bindings(records[k], v) for k, v in selected.items()
    ):
        raise ValueError("paired control changed an input, cutoff or offer")
    _, [measured] = trial.portable.references("ds26-common127", [trial.portable.ROOF_CASE])
    targets = {ident: truth[ident] for ident in sites} | {
        trial.ROOF: dict(condition="authentic", latlon=measured["truth"])
    }
    queries = [
        dict(
            id=ident,
            recording=records[ident]["capture_id"],
            condition=LABELS[targets[ident]["condition"]],
            truth=targets[ident]["latlon"],
            bindings={field: records[ident][field] for field in FIELDS},
        )
        for ident in targets
    ]
    write(
        output / CONTROL,
        gzip.compress(b"".join(encoded(r) + b"\n" for r in selected.values()), mtime=0),
    )
    write(
        output / FIGURE_COMPACT,
        gzip.compress(
            b"".join(
                encoded(dict(row, authentic=ident == trial.ROOF)) + b"\n"
                for ident, row in records.items()
            ),
            mtime=0,
        ),
    )
    rows = []
    for group in (records, selected):
        for ident, row in group.items():
            answer = targets[ident]
            result = row["result"]
            for arm in ARMS:
                endpoint = result.get("arms", {}).get(arm, {})
                site = endpoint.get("latlon")
                rows.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        arm=arm,
                        role=answer["condition"],
                        status=(
                            "ok"
                            if site is not None
                            else "withheld"
                            if result["status"] == "ok"
                            else result["status"]
                        ),
                        prediction=site,
                        error_km=distance_km(site, answer["latlon"]),
                        rf_rms_hz=endpoint.get("rf_rms_hz"),
                        reason=result.get("reason"),
                        false_publication=answer["condition"] == "far-outside" and site is not None,
                        held_rf_rms_hz=result["metrics"]
                        .get("conditional_held_by_arm", {})
                        .get(arm, {})
                        .get("conditional_held_rf_rms_hz"),
                    )
                )
    groups = []
    for mode in (trial.METHOD, METHOD):
        for arm in ARMS:
            for role in LABELS:
                matching = [
                    r for r in rows if (r["method"], r["arm"], r["role"]) == (mode, arm, role)
                ]
                if matching:
                    groups.append(
                        dict(
                            method=mode,
                            arm=arm,
                            role=role,
                            statuses=dict(Counter(r["status"] for r in matching)),
                            position=distribution(r["error_km"] for r in matching),
                            conditional_rf_hz=distribution(r["rf_rms_hz"] for r in matching),
                            held_rf_hz=distribution(r["held_rf_rms_hz"] for r in matching),
                            false_publications=sum(r["false_publication"] for r in matching),
                        )
                    )
    save_json(output / "scores.json", dict(rows=rows, groups=groups))
    return queries


def describe(output, queries):
    cards = []
    for name, cases, authentic in (
        ("compact-secant-paired-transfer", [q for q in queries if q["id"] != trial.ROOF], False),
        ("compact-secant-measured-shift", [q for q in queries if q["id"] == trial.ROOF], True),
    ):
        queries_name = f"{name}-queries.json"
        lock_name = f"{name}-lock.json"
        methods = [
            dict(
                key="candidate",
                label="Compact secant",
                file=FIGURE_COMPACT,
                value=trial.METHOD,
                where={"authentic": authentic},
            )
        ]
        if not authentic:
            methods.append(
                dict(
                    key="stock",
                    label="Native clock + offset, OU",
                    file=CONTROL,
                    value=METHOD,
                    forced_label="Native clock + offset, OU · forced",
                    match=list(FIELDS),
                )
            )
        save_json(output / queries_name, dict(queries=cases))
        provenance = list(ARCHIVE_FILES)
        if authentic and (output / MEASURED_RECEIPT).is_file():
            provenance.append(MEASURED_RECEIPT)
        files = (*provenance, FIGURE_COMPACT, queries_name) + (() if authentic else (CONTROL,))
        save_json(
            output / lock_name,
            dict(
                cases=[q["id"] for q in cases],
                files={name: _sha(output / name) for name in files},
            ),
        )
        title = (
            "Compact secant on a measured roof with an east-shifted tile"
            if authentic
            else "Compact secant on two simulated sites with arbitrary offers"
        )
        caption = (
            "Original measured observations and causal history. The requested tile is "
            "7 km east of the original offered center."
            if authentic
            else "Same simulated GLRT factors and offered tiles. Compact secant also uses the "
            "authenticated preceding TLE history. "
            "Deadlines are shown separately from withheld fixes."
        )
        cards.append(
            dict(
                id=name,
                method=trial.METHOD,
                title=title,
                caption=caption,
                scope="transfer",
                cases="sealed",
                seal=lock_name,
                queries=queries_name,
                provenance=provenance,
                series=methods,
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=cards))


def export(output, *, baseline=trial.prior.REPORT):
    queries = score(output, baseline)
    describe(output, queries)
    screening_figures.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=Path, default=trial.REPORT)
    args = cli.parse_args()
    export(args.out)
