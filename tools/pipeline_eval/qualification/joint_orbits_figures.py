"""Index sealed joint-orbit evidence for the standard screening chart renderer."""

import gzip
import json
from pathlib import Path

from ..__main__ import encoded, save_json, write
from .fresh_scenes import _read, _sha
from .joint_orbits_trial import METHODS, PREDICTIONS, REPORT

GROUPS = (
    ("timing", ("timing",), "roof", "Stored timing recordings"),
    ("confirmation", ("confirmation",), "roof", "Disjoint captured recordings"),
    ("archive-controls", ("archive-omitted", "archive-shuffle"), "transfer", "Measured controls"),
    (
        "synthetic",
        ("synthetic-present", "synthetic-omitted", "synthetic-shuffle"),
        "transfer",
        "Fresh simulated sites",
    ),
)
CONDITIONS = {
    "archive-omitted": "Correct region omitted",
    "archive-shuffle": "Shuffled candidates · no geographic truth",
    "synthetic-present": "Correct tile supplied",
    "synthetic-omitted": "Correct region omitted",
    "synthetic-shuffle": "Shuffled candidates · no geographic truth",
}
MATCH = ("native_sha256", "catalog_sha256", "observation_sha256", "input_sha256")


def index(folder=REPORT):
    from . import cold_scenes as cold

    root_seal = _read(folder / "prediction-lock.json")
    inputs = _read(folder / "input-lock.json")
    scores = _read(folder / "scores.json")
    if (
        _sha(folder / PREDICTIONS) != root_seal["files"][PREDICTIONS]
        or _sha(folder / "input-lock.json") != root_seal["input_lock_sha256"]
        or _sha(folder / "source-lock.json") != root_seal["source_lock_sha256"]
    ):
        raise ValueError("the chart source fails its original prediction seal")
    with gzip.open(folder / PREDICTIONS, "rt") as stream:
        predictions = list(map(json.loads, stream))
    by_id = {r["id"]: r for r in predictions}
    synthetic = {
        case: scores["labels"][case]["latlon"]
        for case, row in by_id.items()
        if row["cohort"].startswith("synthetic-")
    }
    if cold._sha(encoded(synthetic) + b"\n") != inputs["private"]["labels.json"]:
        raise ValueError("synthetic chart labels differ from their pre-score commitment")
    for slug, cohorts, scope, title in GROUPS:
        target = folder / slug
        target.mkdir(parents=True, exist_ok=True)
        cases = [case for case in root_seal["cases"] if by_id[case]["cohort"] in cohorts]
        rows = [r for r in predictions if r["id"] in cases]
        if len(rows) != len(cases) * len(METHODS):
            raise ValueError("the chart prediction roster is incomplete")
        write(
            target / PREDICTIONS, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
        )
        keys = (
            ("one", "stock", "one_native_factors")
            if scope == "roof"
            else ("candidate", "stock", "one")
        )
        extras = {}
        if scope == "transfer":
            name = "figure-queries.json"
            save_json(
                target / name,
                dict(
                    queries=[
                        dict(
                            id=case,
                            condition=CONDITIONS[by_id[case]["cohort"]],
                            recording=by_id[case]["recording"],
                            truth=scores["labels"][case]["latlon"],
                            bindings={key: by_id[case][key] for key in MATCH},
                        )
                        for case in cases
                    ]
                ),
            )
            labels = [CONDITIONS[cohort] for cohort in cohorts]
            extras = dict(queries=name, condition_labels={label: label for label in labels})
        write(target / "source-lock.json", (folder / "source-lock.json").read_bytes())
        write(
            target / "original-prediction-lock.json", (folder / "prediction-lock.json").read_bytes()
        )
        files = [PREDICTIONS, "original-prediction-lock.json"]
        if extras:
            files.append(extras["queries"])
        save_json(
            target / "figure-lock.json",
            dict(
                cases=cases,
                files={name: _sha(target / name) for name in files},
                source_lock_sha256=root_seal["source_lock_sha256"],
            ),
        )
        save_json(
            target / "figures.json",
            dict(
                version=1,
                charts=[
                    dict(
                        id=f"joint-orbits-{slug}",
                        method="joint_orbits",
                        scope=scope,
                        title=f"Joint orbital assignment · {title}",
                        caption="Matched anonymous GLRT Doppler tracks and causal TLE.",
                        cases=cases if scope == "roof" else "sealed",
                        seal="figure-lock.json",
                        provenance=["original-prediction-lock.json"],
                        source_lock={
                            "file": "source-lock.json",
                            "digest_key": "source_lock_sha256",
                        },
                        series=[
                            dict(
                                key=key,
                                label=label,
                                file=PREDICTIONS,
                                value=method,
                                match=list(MATCH),
                            )
                            for key, label, method in zip(
                                keys,
                                ("Joint phase", "Exact orbit", "Lean robust EM"),
                                METHODS,
                                strict=True,
                            )
                        ],
                        **extras,
                    )
                ],
            ),
        )


if __name__ == "__main__":
    import sys

    index(Path(sys.argv[1]) if len(sys.argv) > 1 else REPORT)
