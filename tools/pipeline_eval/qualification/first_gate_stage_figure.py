"""Expose the measured ranked-stop stage through the standard chart contract."""

import csv
import gzip
import json
from io import StringIO
from pathlib import Path

from .. import whole_iq
from ..__main__ import save_json, write
from .first_gate_trial import REPORT
from .full_v5_check import _sha

QUALIFICATION_SHA = "235eee88a9cb7e803e3b02b517c1210bda594cfd86acec1e98f1c4b964898651"


def publish(folder=REPORT):
    source = whole_iq.checked(folder / "qualification-lock.json", QUALIFICATION_SHA)
    files = whole_iq.read(source)["files"]
    path = whole_iq.checked(folder / "input-lock.json", files["input-lock.json"])
    input_lock = whole_iq.read(path)
    table = []
    for case, plan in input_lock["cases"].items():
        name = f"{case}.json.gz"
        receipt = whole_iq.checked(folder / name, files[name])
        result = json.loads(gzip.decompress(receipt.read_bytes()))
        for row in result["rows"]:
            for sample in row["samples"]:
                attempts = row["attempts"][sample["mode"]]
                table.append(
                    dict(
                        case=case,
                        edge=plan["edge"],
                        cpu=result["cpu"],
                        visit=row["visit"],
                        fixture=row["kind"],
                        mode=sample["mode"],
                        repetition=sample["rep"],
                        order=sample["ordinal"],
                        cpu_ms=sample["cpu_ns"] / 1e6,
                        wall_ms=sample["wall_ns"] / 1e6,
                        physical_attempts=len(attempts),
                        retries=sum(r["retry"] for r in attempts),
                        available_fractional_anchors=sum(r["available"] for r in attempts),
                        scored_fractional_anchors=sum(r["scored"] for r in attempts),
                        coarse_grids=sample["coarse_grids"],
                        fine_calls=sample["fine_calls"],
                    )
                )
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(table[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(table)
    for name in ("stage.png", "stage.pdf"):
        whole_iq.checked(folder / name, files[name])
    write(folder / "stage.csv", stream.getvalue().encode())
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="ranked-fractional-stop-raw",
            title="Ranked fractional GLRT stop on saved I/Q",
            sample="16 dual-receiver visits across four recordings, five interleaved repeats",
            boundary="Saved I/Q in memory through the full detector and probe projection",
            note="Median and observed range per mode. Every mode scores all integer anchors.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    names = ("stage.png", "stage.pdf", "stage.csv", "stage-figure.json", source.name)
    save_json(
        folder / "stage-figure-lock.json",
        dict(
            files={name: _sha(folder / name) for name in names},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    publish()
