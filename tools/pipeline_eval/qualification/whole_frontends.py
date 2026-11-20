"""Compare complete saved-IQ detector changes at the same compact cavity endpoint."""

import argparse
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from .full_receiver_comparison import require_fields, roster_matches, seal, sha
from .interleaved_trial import REPORT

ROOT = REPORT.parent
CASES = ("DS26-0036", "DS29-0082")
SOURCES = (
    ("whole-fractional", "whole_fractional", "one", "Optimized GLRT · all visits"),
    ("whole-pair", "whole_cavity", "stock", "Ordinary GLRT · all visits"),
    ("iq-schedule", "iq_schedule", "one_native_factors", "Ordinary GLRT · three of four"),
)


def compare_sources(studies):
    full = studies["whole-pair"]
    for folder, method, _, _ in SOURCES:
        rows = studies[folder]
        roster_matches(rows, CASES, folder)
        for ident, row in rows.items():
            ref = full[ident]
            require_fields(
                row, dict(method=method, tile=ref["tile"], catalog_sha256=ref["catalog_sha256"])
            )
            field = "native_sha256" if folder == "whole-pair" else "origin_native_sha256"
            require_fields(row, {field: ref["native_sha256"], "mode": "matched-tile"})


def publish(out):
    studies, locks, figures = {}, {}, []
    for folder, method, key, label in SOURCES:
        source = ROOT / folder
        lock = seal(source, "prediction-lock.json", ("positions.jsonl.gz", "stages.json.gz"))
        require_fields(lock, dict(source_lock_sha256=sha(source / "source-lock.json")))
        studies[folder] = read_predictions(source / "positions.jsonl.gz")
        locks[folder] = dict(
            input_and_runtime=lock["source_lock_sha256"],
            predictions=sha(source / "prediction-lock.json"),
            stages=lock["files"]["stages.json.gz"],
        )
        figures.append(
            dict(
                key=key,
                label=label,
                value=method,
                file=folder + ".jsonl.gz",
                native_authority="ordinary",
                native_field="native_sha256" if folder == "whole-pair" else "origin_native_sha256",
                match=["tile", "catalog_sha256", "mode"],
            )
        )
    compare_sources(studies)
    for folder in studies:
        write(out / (folder + ".jsonl.gz"), (ROOT / folder / "positions.jsonl.gz").read_bytes())
    save_json(out / "comparisons.json", locks)
    names = ["comparisons.json", *(s["file"] for s in figures)]
    save_json(out / "figure-lock.json", dict(cases=CASES, files={n: sha(out / n) for n in names}))
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="whole-iq-three-frontends",
                    method="whole_fractional",
                    scope="roof",
                    title="Three detector choices from complete saved IQ to position",
                    caption="Same five-minute stored IQ, compact cavity, 512 MiB and zero swap. "
                    "One recording per roof panel. Original v5 used capture-era factors.",
                    cases=list(CASES),
                    seal="figure-lock.json",
                    provenance=["comparisons.json"],
                    series=figures,
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "whole-comparison")
    publish(local_output(parser.parse_args().out))
