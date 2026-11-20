"""Standard position cards from the sealed four-model clock transfer replay."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import encoded, save_json, write
from . import clock_offset_results as original
from . import clock_transfer as trial
from . import screening_figures as standard
from .fresh_scenes import _read, _sha

QUERIES = "figure-queries.json"
POSITIONS = "figure-positions.jsonl.gz"
LOCK = "figure-lock.json"
LABELS = dict(
    zip(
        trial.custodian.KINDS,
        (
            "Correct tile supplied",
            "Near edge · site inside",
            "Near edge · site outside",
            "Far omitted tile",
            "Time shuffle · no geographic truth",
        ),
        strict=True,
    )
)
NAMES = ("Clock + offset, OU", "Clock + offset, diagonal", "Clock only, OU", "Offset only, OU")
PROVENANCE = (
    "prediction-lock.json",
    "input-lock.json",
    "source-lock.json",
    "frozen-clock-offset-results.py.txt",
    "truth.json",
    trial.ARCHIVE,
)
KEYS = ("candidate", "stock", "one", "four")
FIELDS = ("input_sha256", "native_sha256", "catalog_sha256")


def describe(folder):
    seal = _read(folder / "prediction-lock.json")
    inputs = _read(folder / "input-lock.json")
    if (
        seal["predictions_sha256"] != _sha(folder / trial.ARCHIVE)
        or seal["input_lock_sha256"] != _sha(folder / "input-lock.json")
        or inputs["private"]["private/truth.json"] != _sha(folder / "truth.json")
        or inputs["sources"]["source-lock.json"] != _sha(folder / "source-lock.json")
        or _read(folder / "source-lock.json")["files"][
            "tools/pipeline_eval/qualification/clock_offset_results.py"
        ]
        != _sha(folder / "frozen-clock-offset-results.py.txt")
        or seal["methods"] != list(trial.METHODS)
    ):
        raise ValueError("clock-transfer chart input differs from the prospective seals")
    with gzip.open(folder / trial.ARCHIVE, "rt") as stream:
        rows = list(map(json.loads, stream))
    by_id = {row["id"]: row for row in rows}
    truth = _read(folder / "truth.json")
    roster = seal["cases"]
    if (
        len(rows) != 25
        or len(roster) != 25
        or set(roster) != set(by_id)
        or set(truth) != set(by_id)
    ):
        raise ValueError("clock-transfer chart requires the complete independent query roster")
    queries = [
        dict(
            id=ident,
            condition=LABELS[truth[ident]["condition"]],
            recording=row["capture_id"],
            truth=truth[ident]["latlon"],
            bindings={field: row[field] for field in FIELDS},
        )
        for ident, row in by_id.items()
    ]
    save_json(folder / QUERIES, dict(queries=queries))
    models = original._models(by_id, {})
    write(
        folder / POSITIONS,
        gzip.compress(
            b"".join(encoded(rows[ident]) + b"\n" for rows in models.values() for ident in roster),
            mtime=0,
        ),
    )
    save_json(
        folder / LOCK,
        dict(
            cases=roster,
            files={name: _sha(folder / name) for name in (*PROVENANCE, QUERIES, POSITIONS)},
        ),
    )


def specs():
    model_names = dict(zip(trial.METHODS, NAMES, strict=True))
    for i, candidate in enumerate(trial.METHODS):
        order = list(trial.METHODS) if i == 0 else [candidate, trial.METHODS[0]]
        labels = model_names[candidate]
        yield dict(
            id=f"{candidate}-clock-transfer",
            method=candidate,
            scope="transfer",
            title=f"{labels} across six independent simulated locations",
            caption=(
                "Controller-generated GLRT factors carry measured residual and visit-gap windows. "
                "Workers use the earlier TLEs and construct their own Graph. "
                "Forced estimates are diagnostic. White-noise and reduced fits share the gate."
            ),
            cases="sealed",
            seal=LOCK,
            queries=QUERIES,
            condition_labels=dict(zip(LABELS.values(), LABELS.values(), strict=True)),
            provenance=list(PROVENANCE),
            series=[
                dict(
                    key=key,
                    label=model_names[method],
                    forced_label=f"{model_names[method]} · forced",
                    file=POSITIONS,
                    value=method,
                    match=list(FIELDS),
                )
                for key, method in zip(KEYS[: len(order)], order, strict=True)
            ],
        )


def generate(out, *, evidence=trial.REPORT):
    describe(evidence)
    descriptor = dict(version=1, charts=list(specs()))
    write(evidence / "figures.json", (json.dumps(descriptor, indent=2) + "\n").encode())
    return standard.generate(out, evidence=evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--evidence", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    generate(args.out, evidence=args.evidence)
