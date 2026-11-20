"""Fit both arms from physically replayed center-cell factors and package evidence."""

import argparse
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from ..variants import iq_stream
from . import glrt_center_cell_eval as run
from . import ordinary_front_position, short_receiver_figures
from .full_v5_check import _load_case, _sha
from .pilot_kernel_eval import _digest

POSITION = "glrt_center_cell_position"
CONTROL = "glrt_center_cell_fractional_parent"
BOUNDARY = "Fresh center-cell GLRT factors on twelve visits plus archived ordinary factors"
REPORT = run.REPORT


def bind_measurement(case, work):
    lock = json.loads((REPORT / "source-holdout-lock.json").read_bytes())
    path = REPORT / f"{case}-host.json.gz"
    data = run.base.unpack(path)
    candidate = work / f"host-{run.METHOD}" / run.NATIVE_LIBRARY.name
    if (
        data["source_holdout_lock_sha256"] != _digest(encoded(lock))
        or data["cohort"] != lock["cases"][case]["visits"]
        or data["executable_sha256"][run.METHOD] != _sha(candidate)
    ):
        raise ValueError("the measured payloads differ from the frozen cohort or built candidate")
    source = {str(Path(__file__)): _sha(Path(__file__)), str(path): _sha(path)}
    return data, lock, source


def position(case, work, cpu):
    data, _, source = bind_measurement(case, work)
    for row in [*data["rows"], *data["controls"].values()]:
        if "calls" in row and (
            not row["exact"]
            or any(_digest(encoded(row["payloads"][m])) != row["digest"] for m in run.MODES)
        ):
            raise ValueError(
                "the physically replayed candidate factors changed their parent fields"
            )
    schedule = run.base.ordinary_prepared_eval.archive.SCHEDULE
    seam = SimpleNamespace(SCHEDULE=schedule, sources=lambda: source)
    with (
        patch.multiple(
            ordinary_front_position,
            REPORT=REPORT,
            METHOD=run.METHOD,
            CONTROL=CONTROL,
            BOUNDARY=BOUNDARY,
            ordinary_front_eval=seam,
        ),
        patch.object(
            iq_stream, "MAX_CHUNK_PREFIX", run.base.ordinary_prepared_eval.archive.CHUNK_PREFIX
        ),
    ):
        ordinary_front_position.position(case, work, cpu)
    receipt_path = work / f"{case}-position.json"
    receipt = json.loads(receipt_path.read_bytes())
    prior = run.sealed(run.base.REPORT / "position-receipts.json")
    stock = json.loads(prior.read_bytes())[case]["trial"]
    trial = dict(receipt["trial"], method=POSITION)
    for key in ("source_ordinary_sha256", "catalog_sha256", "observation_sha256", "tile"):
        if trial[key] != stock[key]:
            raise ValueError(f"the archive-assisted replay changed its parent's {key}")
    for key in ("status", "reason", "arms"):
        if trial["result"][key] != stock["result"][key]:
            raise ValueError(f"the fresh replay changed the calibrated parent's {key}")
    receipt.update(
        trial=trial,
        stock=dict(stock, method=CONTROL),
        parent_position_receipts_sha256=_sha(prior),
        evidence_sources=source,
    )
    save_json(receipt_path, receipt)


def by_cohort(data, cohort, mode):
    include = {row["visit"] for row in data["cohort"] if row["cohort"] == cohort}
    return [
        r
        for row in data["rows"]
        if row["visit"] in include
        for r in row["calls"]
        if r["mode"] == mode
    ]


def package(work):
    authority = short_receiver_figures.ORDINARY / "recording-receipts.json"
    native = json.loads(authority.read_bytes())["recordings"]
    streams = {case: bind_measurement(case, work)[0] for case in run.CASES}
    summarize = run.base.ordinary_prepared_eval.timing_summary
    result = {}
    stage_rows = []
    for cohort in ("held", "companion"):
        result[cohort] = {
            mode: summarize([row for d in streams.values() for row in by_cohort(d, cohort, mode)])
            for mode in run.MODES
        }
    qualification = dict(
        timing=result,
        meets_20_ms_median=result["held"][run.METHOD]["full_wall_median_ms"] <= 20,
        cases={},
    )
    for case, data in streams.items():
        included = [r for r in data["rows"] if "calls" in r]
        qualification["cases"][case] = dict(
            roster=data["cohort"],
            exact_visits=sum(r["exact"] for r in included),
            admitted=len(included),
            ignored=len(data["rows"]) - len(included),
            controls={
                k: dict(exact=v["exact"], positives=v["positives"])
                for k, v in data["controls"].items()
            },
            paired_runner_peak_kib=data["runner_peak_rss_kib"],
            executable_sha256=data["executable_sha256"],
        )
        for mode in run.MODES:
            stage_rows.append(
                dict(
                    id=case,
                    method=run.METHOD if mode == run.METHOD else "glrt_center_cell_stage_parent",
                    catalog_sha256=_load_case(case)["catalog"]["sha256"],
                    source_ordinary_sha256=native[case]["native_sha256"],
                    visit_receipt_sha256=_sha(REPORT / f"{case}-host.json.gz"),
                    result=dict(
                        status="withheld",
                        boundary="Warm authenticated CI16 to native candidates",
                        reason="native detector timing stage only",
                        metrics=dict(
                            position_attempted=False,
                            timing=summarize(by_cohort(data, "held", mode)),
                        ),
                    ),
                )
            )
    save_json(REPORT / "qualification.json", qualification)
    save_json(
        REPORT / "build-receipt.json",
        json.loads((work / f"host-{run.METHOD}" / "build-receipt.json").read_bytes()),
    )
    positions = {
        case: json.loads((work / f"{case}-position.json").read_bytes()) for case in run.CASES
    }
    save_json(REPORT / "position-receipts.json", positions)
    for name, rows in (
        ("stage-results.jsonl.gz", stage_rows),
        ("positions.jsonl.gz", [p["trial"] for p in positions.values()]),
        ("control-positions.jsonl.gz", [p["stock"] for p in positions.values()]),
    ):
        write(REPORT / name, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    files = (
        "figures.json",
        "PROTOCOL.md",
        "source-holdout-lock.json",
        "build-receipt.json",
        "qualification.json",
        "position-receipts.json",
        "stage-results.jsonl.gz",
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        *(f"{c}-host.json.gz" for c in run.CASES),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(run.CASES),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=local_output, required=True)
    cli.add_argument("--case", choices=run.CASES)
    cli.add_argument("--cpu", default=12, type=int)
    args = cli.parse_args()
    if args.case:
        position(args.case, args.work, args.cpu)
    else:
        package(args.work)
