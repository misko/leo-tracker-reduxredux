"""Confirm exact reused GLRT inputs through an authenticated partial-IQ v5 fit."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import median

from ..__main__ import THREAD_ENV, encoded, local_output, references, write
from ..scoring import distance_km, distribution, validate_result
from ..variants import anchor_receiver, v5_lean
from . import certified_glrt_eval as detector
from . import spectral_position
from .dense_q10_eval import REPORT as Q10_REPORT
from .dense_q10_position import _archive
from .full_v5_check import PRODUCERS, _load_case, _measure, _sha
from .recording_to_v5 import digest, save
from .sparse_epoch_position import counts

CASE = "DS26-0036"
METHOD = detector.METHOD
CONTROL = "certified_glrt_capture_control"
MODES = ("control", METHOD)
TIMES = ("coarse_cpu_s", "full_cpu_s", "full_wall_s")
BOUNDARY = "Eight held IQ visits through exact guarded-acquisition reuse plus archived factors"


def read(ident):
    path = detector.REPORT / f"{ident}-replay.json.gz"
    doc = json.loads(gzip.decompress(path.read_bytes()))
    if (
        doc["case"] != ident
        or doc["source_sha256"] != detector.sources()
        or detector.LOCK.read_bytes() != encoded(doc["source_sha256"]) + b"\n"
        or doc["producer"]["run_id"] != _load_case(ident)["run_id"]
        or set(doc["panels"]) != set(detector.SCHEDULE)
        or set(doc["controls"]) != {"empty", "faint", "noise"}
    ):
        raise ValueError(f"Invalid qualified capture identity for {ident}")
    for split, (segment, sequences) in detector.SCHEDULE.items():
        panel = doc["panels"][split]
        if (
            panel["segment"] != segment
            or tuple(r["sequence"] for r in panel["rows"]) != sequences
            or len(panel["bounds"]) != 2
        ):
            raise ValueError(f"Invalid held roster for {ident}/{split}")
    return doc, _sha(path)


def held(doc):
    return [r for split in detector.SCHEDULE for r in doc["panels"][split]["rows"]]


def exact(row):
    return (
        row["stable"]
        and row["equal_status"]
        and row["exact_payload"]
        and row["payload_sha256"]["control"] == row["payload_sha256"][METHOD]
    )


def fit(work):
    case = _load_case(CASE)
    source_path = _archive(case)
    archive = json.loads(source_path.read_bytes())
    doc, stage_sha = read(CASE)
    rows = held(doc)
    if not all(exact(r) and r["matches_original_control"] for r in rows):
        raise ValueError("Fresh receiver payload differs from the capture-era detector")
    audit = _measure(case, rows, archive["source"]["sample_rate_hz"])
    if audit["different_probe_keys"] or not audit["archive_exclusions_equal"]:
        raise ValueError("Fresh controls differ from the authorized archived factors")
    replay = dict(
        rows=rows,
        producer=doc["producer"],
        archive_audit=audit,
        source_sha256=digest(doc["source_sha256"]),
        kernel_sha256=doc["library_sha256"]["dense"],
    )
    composite, changed = anchor_receiver.splice_probes(archive, replay)
    if changed or composite["source"]["probes"] != archive["source"]["probes"]:
        raise ValueError("The actual detector replay changed originally qualified tracking factors")
    composite["provenance"]["scope"] = BOUNDARY
    work.mkdir(parents=True, exist_ok=False)
    trial_path = work / "partial-iq-native.json"
    save(trial_path, composite)
    stock_path = Q10_REPORT / "control-positions.jsonl.gz"
    lock = json.loads((Q10_REPORT / "prediction-lock.json").read_bytes())
    if lock["files"][stock_path.name] != _sha(stock_path):
        raise ValueError("Matched prior archive control differs from its frozen seal")
    stock = json.loads(gzip.decompress(stock_path.read_bytes()))
    fields = dict(
        source_archive_sha256=case["native"]["sha256"], catalog_sha256=case["catalog"]["sha256"]
    )
    if (
        (stock["id"], stock["method"]) != (CASE, "dense_q10_capture_control")
        or stock["input_sha256"] != "sha256:" + _sha(source_path)
        or any(stock[k] != v for k, v in fields.items())
    ):
        raise ValueError("Matched prior archive control uses another recording or catalogue")
    trial = spectral_position.fit(case, trial_path, work / "fit", METHOD)
    if trial["input_sha256"] != "sha256:" + _sha(trial_path):
        raise ValueError("The actual position worker consumed another native document")
    spectral_position.verify_pair(stock, trial)
    _, (site,) = references("ds26-common127", [CASE])
    valid = sum(r["policy_status"] == "processed" for r in rows)
    trial["result"]["boundary"] = BOUNDARY
    trial["result"]["metrics"].update(
        fresh_iq_visits=valid,
        scheduled_visits=len(rows),
        fresh_receiver_rows=audit["exact_probe_rows"],
        archived_valid_visits=archive["provenance"]["processed_windows"] - valid,
    )
    trial.update(
        **fields,
        detector_receipt_sha256=stage_sha,
        paired_control_receipt_sha256=_sha(stock_path),
        position_error_km={
            arm: distance_km(trial["result"]["arms"][arm]["latlon"], site["truth"])
            for arm in v5_lean.ARMS
        },
    )
    stock["method"] = CONTROL
    for row in (trial, stock):
        validate_result(row["result"])
        save(detector.REPORT / f"{row['method']}.json", row)


def summarize(rows):
    valid = [r for r in rows if r["policy_status"] == "processed"]
    timing = {m: [t for r in valid for t in r["timings"][m]] for m in MODES}
    clocks = {m: {k: sum(t[k] for t in group) for k in TIMES} for m, group in timing.items()}
    memo = [entry for t in timing[METHOD] for entry in t["reuse"]]
    return dict(
        visits=len(rows),
        valid=len(valid),
        exact=sum(exact(r) for r in rows),
        original=sum(r["matches_original_control"] for r in rows),
        integer=counts(valid, "integer"),
        fractional=counts(valid, "fractional"),
        total_s=clocks,
        medians_s={
            m: {k: median(t[k] for t in group) for k in TIMES} for m, group in timing.items()
        },
        savings={k: 1 - clocks[METHOD][k] / clocks["control"][k] for k in TIMES},
        coarse_hits=sum(r["coarse_hits"] for r in memo),
        fine_hits=sum(r["fine_hits"] for r in memo),
        max_memo_array_bytes=max(
            g.get("reuse_cache_bytes", 0) for t in timing[METHOD] for g in t["grids"]
        ),
    )


def package():
    report = detector.REPORT
    blocks = {c: read(c)[0] for c in PRODUCERS}
    all_rows = [r for doc in blocks.values() for r in held(doc)]
    bounds = [b for doc in blocks.values() for p in doc["panels"].values() for b in p["bounds"]]
    bound_counts = {
        tap: sum(row["prunable_by_prefix"][tap] for row in bounds)
        for tap in bounds[0]["prunable_by_prefix"]
    }
    records = [json.loads((report / f"{m}.json").read_bytes()) for m in (METHOD, CONTROL)]
    spectral_position.verify_pair(records[1], records[0])
    result = dict(
        method=METHOD,
        held=summarize(all_rows),
        cases={key: summarize(held(value)) for key, value in blocks.items()},
        bounds=dict(cells=sum(b["cells"] for b in bounds), prunable=bound_counts, grids=bounds),
        controls={
            case: {
                name: dict(exact=exact(r), fractional=counts([r], "fractional"))
                for name, r in value["controls"].items()
            }
            for case, value in blocks.items()
        },
        position_errors_km={
            row["method"]: {a: distribution([row["position_error_km"][a]]) for a in v5_lean.ARMS}
            for row in records
        },
    )
    write(report / "qualification.json", encoded(result) + b"\n")
    files = ["PROTOCOL.md", "source-lock.json", "qualification.json"]
    names = ("positions.jsonl.gz", "control-positions.jsonl.gz")
    for row, name in zip(records, names, strict=True):
        write(report / name, gzip.compress(encoded(row) + b"\n", mtime=0))
        files.extend((name, f"{row['method']}.json"))
    files.extend(f"{case}-replay.json.gz" for case in PRODUCERS)
    lock = dict(cases=[CASE], files={name: _sha(report / name) for name in files})
    write(report / "prediction-lock.json", encoded(lock) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fit", "package"))
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.action == "package":
        package()
        return
    if (
        args.work is None
        or os.sched_getaffinity(0) != {detector.CPU}
        or any(os.environ.get(k) != "1" for k in THREAD_ENV)
    ):
        parser.error("provide local work output and pin the CPU and numerical pools")
    fit(local_output(args.work))


if __name__ == "__main__":
    main()
