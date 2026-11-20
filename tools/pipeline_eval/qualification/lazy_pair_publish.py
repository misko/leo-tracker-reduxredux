"""Verify the gate-selected compact pair and build normalized position archives."""

import csv
import gzip
import json
import sys
from pathlib import Path

from .. import corpus
from ..__main__ import ROOT, encoded, read_predictions, save_json, write
from . import lazy_pair_trial as trial

HISTORICAL = ROOT / "reports/2026_11_19_receiver_streaming/finish"
FILES = ("positions.jsonl.gz", "control-positions.jsonl.gz")


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return trial.digest(path.read_bytes())


def publish(output):
    selection = read(output / "selection.json")
    gate_file = output / "archived-gates.csv"
    if digest(gate_file) != selection["archive_gate_csv_sha256"]:
        raise ValueError("gate roster differs from its predeclared input")
    with gate_file.open(newline="") as stream:
        gates = {row["recording"]: row for row in csv.DictReader(stream)}
    roster = selection["primary"] + selection["additional"]
    ids = [row["id"] for row in roster]
    for pick in selection["additional"]:
        fitted = str(pick["archived_fitted_pass"])
        selected = min(
            k
            for k, gate in gates.items()
            if gate["c0_passes"] == "False" and gate["fitted_c_passes"] == fitted
        )
        if pick["id"] != selected:
            raise ValueError("gate-only extension case changed")
    if not trial.score(output, ids):
        raise ValueError("paired qualification did not meet exact parity")
    raw_lock = read(output / "prediction-lock.json")
    control, candidate = (read_predictions(output / name) for name in reversed(FILES))
    comparisons = read(output / "comparison.json")
    _, frozen_files = corpus._selection("roof16")
    frozen = corpus._index(corpus._read_frozen("inputs.jsonl", frozen_files))
    baseline = {}
    source = None
    frozen_harness = gzip.decompress((output / "sealed-measurement-harness.py.gz").read_bytes())
    for pick, comparison in zip(roster, comparisons, strict=True):
        ident = pick["id"]
        source_plan = read(output / "cases" / ident / "plan.json")
        intended = (
            (trial.CONTROL, trial.CANDIDATE)
            if pick["first"] == "eager"
            else (trial.CANDIDATE, trial.CONTROL)
        )
        gate = gates[ident]
        if (
            pick["cpu"] != source_plan["cpu"]
            or list(intended) != source_plan["order"]
            or pick["archived_c0_pass"] != (gate["c0_passes"] == "True")
            or pick["archived_fitted_pass"] != (gate["fitted_c_passes"] == "True")
            or comparison["c0_passed"] != pick["archived_c0_pass"]
            or comparison["pair_accepted"] != (gate["original_paired_accepts"] == "True")
        ):
            raise ValueError("fresh and archived fit schedules or decisions differ")
        case = trial._public(ident)
        native = frozen[ident]["native"]["sha256"]
        catalog = frozen[ident]["catalog"]["sha256"]
        if (
            trial.digest(encoded(case)) != source_plan["input_sha256"]
            or case["native_sha256"].removeprefix("sha256:") != native
            or digest(Path(case["catalog_path"])) != catalog
            or digest(Path(case["request_path"])) != source_plan["frozen_request_sha256"]
        ):
            raise ValueError("public packet differs from the frozen case authority")
        source = source if source is not None else source_plan["sources"]
        if source != source_plan["sources"] or source["harness_sha256"] != trial.digest(
            frozen_harness
        ):
            raise ValueError("frozen worker source differs across paired cases")
        per_case = dict(
            native_sha256=native,
            catalog_sha256=catalog,
            frozen_request_sha256=source_plan["frozen_request_sha256"],
        )
        for series in (control, candidate):
            series[ident].update(per_case)
        historic = HISTORICAL / f"{ident}-compact_finish.json"
        if historic.is_file():
            record = read(historic)
            ref = record["result"]
            fresh = control[ident]["result"]

            def scientific(result):
                return {
                    k: v
                    for k, v in result["metrics"].items()
                    if k not in {"predictive_pair", "stage_s", "candidate_s"}
                }

            if (
                record["input_sha256"] != source_plan["input_sha256"]
                or encoded(ref["arms"]) != encoded(fresh["arms"])
                or encoded(scientific(ref)) != encoded(scientific(fresh))
            ):
                raise ValueError("fresh eager path changed the archived unmodified compact result")
            baseline[ident] = dict(
                sha256=digest(historic),
                file=str(historic.relative_to(ROOT)),
                matched_unchanged_compact=True,
            )
    save_json(output / "source-lock.json", source)
    for name, rows in zip(FILES, (candidate, control), strict=True):
        payload = b"".join(encoded(rows[ident]) + b"\n" for ident in ids)
        write(output / name, gzip.compress(payload, mtime=0))
    files = (
        *FILES,
        "comparison.json",
        "selection.json",
        "source-lock.json",
        "archived-gates.csv",
        "archived-gates.json",
        "PROTOCOL.md",
        "sealed-measurement-harness.py.gz",
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=ids,
            files={fn: digest(output / fn) for fn in files},
            case_seals=raw_lock["cases"],
            historical_controls=baseline,
            publication_source_sha256=digest(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    publish(Path(sys.argv[1]) if len(sys.argv) > 1 else trial.OUTPUT)
