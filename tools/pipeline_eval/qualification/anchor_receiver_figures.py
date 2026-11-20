"""Index the sealed anchor and control fits for the standard position atlas."""

import argparse
from pathlib import Path

from ..__main__ import references, save_json, write
from .anchor_receiver_trial import (
    COHORTS,
    FILE,
    METHODS,
    REPORT,
    _jsonl,
    _verify,
)
from .fresh_scenes import _sha

MATCH = ["native_sha256", "catalog_sha256", "observation_sha256", "input_sha256"]


def index(folder):
    predictions = _verify(folder)
    identifiers = [c for group in COHORTS.values() for c in group]
    truth = {r["id"]: r["truth"] for r in references("ds26-common127", identifiers)[1]}
    for cohort in (*COHORTS, "omitted"):
        transfer = cohort == "omitted"
        target = folder / cohort
        target.mkdir(parents=True, exist_ok=True)
        rows = [r for r in predictions if r["cohort"] == cohort]
        by_case = {r["id"]: r for r in rows}
        cases = list(by_case)
        _jsonl(target / FILE, rows)
        for name, output in (
            ("prediction-lock.json", "original-prediction-lock.json"),
            ("input-lock.json", "input-lock.json"),
            ("source-lock.json", "source-lock.json"),
        ):
            write(target / output, (folder / name).read_bytes())
        files = [FILE, "original-prediction-lock.json", "input-lock.json"]
        extras = {}
        if transfer:
            queries = "figure-queries.json"
            save_json(
                target / queries,
                dict(
                    queries=[
                        dict(
                            id=ident,
                            condition="Correct region omitted",
                            recording=row["capture_id"],
                            truth=truth[row["capture_id"]],
                            bindings={name: row[name] for name in MATCH},
                        )
                        for ident, row in by_case.items()
                    ]
                ),
            )
            files.append(queries)
            extras["queries"] = queries
        save_json(
            target / "figure-lock.json",
            dict(
                cases=cases,
                files={name: _sha(target / name) for name in files},
                source_lock_sha256=_sha(target / "source-lock.json"),
            ),
        )
        title = "Omitted tiles" if transfer else f"Independent {cohort} cohort"
        keys = ("candidate", "stock", "one") if transfer else ("one", "stock", "one_native_factors")
        save_json(
            target / "figures.json",
            dict(
                version=1,
                charts=[
                    dict(
                        id=f"anchor-receiver-{cohort}",
                        method=METHODS[0],
                        scope="transfer" if transfer else "roof",
                        title=f"Independent Doppler anchors · {title}",
                        caption="Identical anonymous GLRT tracks, tile offer and causal TLE.",
                        cases="sealed" if transfer else cases,
                        seal="figure-lock.json",
                        provenance=["original-prediction-lock.json", "input-lock.json"],
                        source_lock={
                            "file": "source-lock.json",
                            "digest_key": "source_lock_sha256",
                        },
                        series=[
                            dict(key=k, label=label, file=FILE, value=method, match=MATCH)
                            for k, label, method in zip(
                                keys,
                                ("Independent anchors", "Full joint", "Exact orbit"),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=REPORT)
    index(parser.parse_args().evidence)
