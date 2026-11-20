"""Supplementary frozen anchor predictions on the independent near-edge offers."""

import argparse
import gzip
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import anchor_receiver_full as full
from .fresh_scenes import _read, _sha

AUTHORITY = Path("/srv/bulk/leo-dev/receiver-screening-20261119/boundary-roof/primary")
REQUESTS_SHA = "4c9783938d301031b176bb864629562ec84e3da5e8d8700611e834db545ca084"
REPORT = full.REPORT.with_name("anchor-near-edge")
FILE = "positions.jsonl.gz"
LABELS = {
    "original": "Original tile",
    "near-inside": "Near boundary · site inside",
    "near-outside": "Near boundary · site outside",
    "six-outside": "6 km outside",
}


def requests():
    path = AUTHORITY / "requests.json"
    if _sha(path) != REQUESTS_SHA:
        raise ValueError("independent offer requests differ from their sealed digest")
    document = _read(path)
    rows = document["cases"]
    if len(rows) != 40 or len({r["id"] for r in rows}) != 40:
        raise ValueError("expected all forty independent offers")
    return document, rows


def predict(output, bundle):
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= set(full.CPUS):
        raise ValueError("pin supplementary inference to assigned CPUs")
    sources = full.sources(bundle)
    primary = full.REPORT / "prediction-lock.json"
    target = full.REPORT / FILE
    if _sha(target) != _read(primary)["files"][FILE]:
        raise ValueError("the primary native panel must already be sealed")
    _, items = requests()
    inventory = full.old.base.phase.frozen_inputs()
    bound = []
    for row in items:
        item = inventory[row["recording"]]
        packet, files = full.old.base.native.request(item, "native", offer=row["packet"]["offer"])
        if packet != row["packet"]:
            raise ValueError("near-edge capture, catalogue or offer differs from the sealed input")
        bound.append((row, files))
    if (output / "prediction-lock.json").exists():
        raise FileExistsError("the independent prediction seal already exists")
    save_json(
        output / "source-lock.json",
        dict(
            sources=sources,
            request_sha256=REQUESTS_SHA,
            primary_sha256=_sha(primary),
            analysis_sha256=_sha(Path(__file__)),
            cpus=cpus,
        ),
    )

    def lane(index):
        return [
            full.attempt(row, paths, cpus[index], bundle)
            for row, paths in bound[index :: len(cpus)]
        ]

    with ThreadPoolExecutor(len(cpus)) as pool:
        rows = [r for batch in pool.map(lane, range(len(cpus))) for r in batch]
    if full.sources(bundle) != sources or [r["id"] for r in items] != [
        r["id"] for r in requests()[1]
    ]:
        raise ValueError("independent source or requests changed during inference")
    write(output / FILE, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in items],
            requests_sha256=REQUESTS_SHA,
            source_lock_sha256=_sha(output / "source-lock.json"),
            files={FILE: _sha(output / FILE)},
        ),
    )


def score(output):
    document, items = requests()
    seal = _read(output / "prediction-lock.json")
    if (
        seal["requests_sha256"] != REQUESTS_SHA
        or seal["files"][FILE] != _sha(output / FILE)
        or seal["source_lock_sha256"] != _sha(output / "source-lock.json")
        or seal["cases"] != [row["id"] for row in items]
    ):
        raise ValueError("unsealed near-edge predictions")
    with gzip.open(output / FILE, "rt") as stream:
        rows = list(map(json.loads, stream))
    predictions = {r["id"]: r for r in rows}
    evaluator = AUTHORITY / "evaluator.json"
    if (
        len(rows) != len(items)
        or set(predictions) != set(seal["cases"])
        or _sha(evaluator) != document["evaluator_sha256"]
    ):
        raise ValueError("sealed near-edge cases or evaluator bytes differ")
    labels = _read(evaluator)["labels"]
    if isinstance(labels, dict):
        labels = list(labels.values())
    if {r["id"] for r in labels} != set(predictions):
        raise ValueError("near-edge labels do not cover the sealed roster")
    scores, queries = [], []
    match = ("input_sha256", "native_sha256", "catalog_sha256")
    for r in labels:
        pred = predictions[r["id"]]
        if any(r[k] != pred[k] for k in ("recording", "tile", "input_sha256")):
            raise ValueError("near-edge label differs from inference request")
        queries.append(
            dict(
                id=r["id"],
                recording=r["recording"],
                truth=r["truth"],
                condition=LABELS[r["condition"]],
                bindings={k: pred[k] for k in match},
            )
        )
        for arm in ARMS:
            endpoint = pred["result"]["arms"][arm]
            scores.append(
                dict(
                    r,
                    arm=arm,
                    status=pred["result"]["status"],
                    published=endpoint["latlon"] is not None,
                    reason=pred["result"].get("reason"),
                    error_km=distance_km(endpoint["latlon"], r["truth"]),
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), r["truth"]),
                    residual_rms_hz=endpoint.get("rf_rms_hz"),
                )
            )
    groups = defaultdict(list)
    for row in scores:
        groups[row["arm"], row["condition"]].append(row)
    out = [
        dict(
            arm=arm,
            condition=condition,
            requested_margin_km=distribution(r["requested_margin_km"] for r in rows),
            attempts=len(rows),
            published=sum(r["published"] for r in rows),
            errors=distribution(r["error_km"] for r in rows),
            forced=distribution(r["forced_error_km"] for r in rows),
        )
        for (arm, condition), rows in groups.items()
    ]
    save_json(
        output / "scores.json",
        dict(
            evaluator_sha256=document["evaluator_sha256"],
            scoring_source_sha256=_sha(Path(__file__)),
            groups=out,
            cases=scores,
        ),
    )
    save_json(output / "figure-queries.json", dict(queries=queries))
    save_json(
        output / "figure-lock.json",
        dict(
            cases=seal["cases"],
            files={
                n: _sha(output / n) for n in (FILE, "prediction-lock.json", "figure-queries.json")
            },
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="native-anchor-near-edge",
                    method=full.METHOD,
                    scope="transfer",
                    title="Independent anchors · blind near-edge offers",
                    caption="A separate forty-query near-edge panel with complete native GLRT.",
                    cases="sealed",
                    seal="figure-lock.json",
                    queries="figure-queries.json",
                    provenance=["prediction-lock.json"],
                    condition_labels={label: label for label in LABELS.values()},
                    series=[
                        dict(
                            key="candidate",
                            label="Streamed orbit anchors",
                            file=FILE,
                            value=full.METHOD,
                        )
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("predict", "score"))
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--bundle", type=Path, default=full.old.base.BUNDLE)
    args = parser.parse_args()
    if args.action == "predict":
        predict(args.output, args.bundle)
    else:
        score(args.output)
