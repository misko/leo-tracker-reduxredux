"""Seal held Q10 detector comparisons and one authenticated partial-IQ v5 pair."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import median

from ..__main__ import THREAD_ENV, encoded, local_output, references, write
from ..scoring import distance_km, distribution, validate_result
from ..variants import anchor_receiver, v5_lean
from . import dense_q10_eval as detector
from . import spectral_position
from .full_v5_check import BULK, PRODUCERS, _load_case, _measure, _sha
from .recording_to_v5 import digest, save
from .sparse_epoch_position import counts

CASE = "DS26-0036"
METHOD = detector.METHOD
CONTROL = "dense_q10_capture_control"
MODES = ("control", METHOD)
FIELDS = ("coarse_cpu_s", "full_cpu_s", "full_wall_s")
BOUNDARY = "Held full-epoch Q10 IQ visits plus remaining archived factors to paired v5"
CONTROLS = {"adjacent", "empty", "faint_between", "faint_on", "noise", "plant"}


def read_blocks(case, report):
    sources = detector.frozen_sources()
    if detector.LOCK.read_bytes() != encoded(sources) + b"\n":
        raise ValueError("Scored source lock no longer matches the detector files")
    blocks, hashes = {}, {}
    for split, (segment, sequence) in detector.SCHEDULE.items():
        path = report / f"{case['id']}-{split}.json.gz"
        block = json.loads(gzip.decompress(path.read_bytes()))
        if (
            (block["case"], block["split"], block["segment"]) != (case["id"], split, segment)
            or block["source_sha256"] != sources
            or block["producer"]["run_id"] != case["run_id"]
            or block["cpus"] != [detector.CPUS[case["id"]]]
            or tuple(row["sequence"] for row in block["rows"]) != sequence
            or set(block["controls"]) != (CONTROLS if split == "development" else set())
            or any(
                block[field] != first[field]
                for first in blocks.values()
                for field in ("producer", "library_sha256", "numpy")
            )
        ):
            raise ValueError(f"Unmatched detector block {path.name}")
        blocks[split], hashes[split] = block, _sha(path)
    return blocks, hashes


def held(blocks):
    return [row for split in ("early", "late") for row in blocks[split]["rows"]]


def payload_parity(row):
    return (
        row["stable"]
        and row["equal_status"]
        and row["exact_payload"]
        and row["payload_sha256"]["control"] == row["payload_sha256"][METHOD]
    )


def summarize(rows):
    valid = [r for r in rows if r["policy_status"] == "processed"]
    measures = {
        mode: {f: [t[f] for r in valid for t in r["timings"][mode]] for f in FIELDS}
        for mode in MODES
    }
    pooled = {
        mode: {f: sum(values) for f, values in fields.items()} for mode, fields in measures.items()
    }
    records = {
        mode: [g for r in valid for t in r["timings"][mode] for g in t["grids"]] for mode in MODES
    }
    ratios = {
        f: 1 - pooled[METHOD][f] / pooled["control"][f] for f in ("coarse_cpu_s", "full_cpu_s")
    }
    return dict(
        scheduled_visits=len(rows),
        valid_visits=len(valid),
        exact_visits=sum(payload_parity(r) for r in rows),
        original_visits=sum(r["matches_original_control"] for r in rows),
        integer=counts(valid, "integer"),
        fractional=counts(valid, "fractional"),
        pooled_timing_s=pooled,
        median_timing_s={
            mode: {f: median(values) for f, values in fields.items()}
            for mode, fields in measures.items()
        },
        fractional_saving=ratios,
        speed_accepted=ratios["coarse_cpu_s"] >= 0.20 and ratios["full_cpu_s"] >= 0.10,
        grid_receipts={
            mode: dict(
                calls=len(group),
                fallback=sum(bool(r.get("fallback")) for r in group),
                max_error_bound=max((r.get("error_bound", 0) for r in group), default=0),
                median_repaired_cells=median(r.get("repaired_cells", 0) for r in group),
                dense_array_bytes=max(r.get("persistent_stage_array_bytes", 0) for r in group),
                extra_coefficient_bytes=max(
                    r.get("quantized_coefficients_bytes", 0) for r in group
                ),
                integer_prefix_bytes=max(r.get("quantized_integer_prefix_bytes", 0) for r in group),
            )
            for mode, group in records.items()
        },
    )


def _archive(case):
    archive = BULK / case["native"]["path"]
    if (
        _sha(archive) != case["native"]["sha256"]
        or _sha(BULK / case["catalog"]["path"]) != case["catalog"]["sha256"]
    ):
        raise ValueError("Archive or frozen causal catalogue changed")
    return archive


def prepare(report, work):
    case = _load_case(CASE)
    archive = json.loads(_archive(case).read_bytes())
    blocks, hashes = read_blocks(case, report)
    rows = held(blocks)
    if not all(payload_parity(row) and row["matches_original_control"] for row in rows):
        raise ValueError("Fresh Q10 outputs do not exactly preserve the public capture payload")
    if not all(payload_parity(row) for row in blocks["development"]["controls"].values()):
        raise ValueError("Fresh synthetic controls changed their public receiver payload")
    audit = _measure(case, rows, archive["source"]["sample_rate_hz"])
    if audit["different_probe_keys"] or not audit["archive_exclusions_equal"]:
        raise ValueError("Fresh DS26 accelerated control does not bind archived cases")
    block = blocks["early"]
    replay = dict(
        rows=rows,
        producer=block["producer"],
        source_sha256=digest(block["source_sha256"]),
        kernel_sha256=block["library_sha256"]["quantized"],
        archive_audit=audit,
    )
    composite, changed = anchor_receiver.splice_probes(archive, replay)
    if changed or archive["source"]["probes"] != composite["source"]["probes"]:
        raise ValueError("New IQ execution changed native tracking factors")
    composite["provenance"]["scope"] = BOUNDARY
    work.mkdir(parents=True, exist_ok=False)
    native_path = work / "partial-iq-native.json"
    save(native_path, composite)
    valid = sum(r["policy_status"] == "processed" for r in rows)
    save(
        work / "confirmation.json",
        dict(
            trial_input_sha256=_sha(native_path),
            source_archive_sha256=case["native"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            detector_receipts_sha256=hashes,
            scheduled_visits=len(rows),
            fresh_iq_visits=valid,
            archived_valid_visits=archive["provenance"]["processed_windows"] - valid,
            fresh_receiver_rows=audit["exact_probe_rows"],
            detector_cpu_s=sum(r["timings"][METHOD][0]["full_cpu_s"] for r in rows),
            detector_wall_s=sum(r["timings"][METHOD][0]["full_wall_s"] for r in rows),
        ),
    )


def fit(side, report, work):
    case = _load_case(CASE)
    archive = _archive(case)
    evidence = json.loads((work / "confirmation.json").read_bytes())
    match = side == METHOD
    native_path = work / "partial-iq-native.json" if match else archive
    expected = evidence["trial_input_sha256" if match else "source_archive_sha256"]
    if _sha(native_path) != expected:
        raise ValueError("Position worker received a different native input")
    row = spectral_position.fit(case, native_path, work / side, side)
    if row["input_sha256"] != f"sha256:{expected}":
        raise ValueError("The actual bound position input differs from the selected side")
    _, (site,) = references("ds26-common127", [CASE])
    row.update(
        source_archive_sha256=evidence["source_archive_sha256"],
        catalog_sha256=evidence["catalog_sha256"],
        position_error_km={
            arm: distance_km(row["result"]["arms"][arm]["latlon"], site["truth"])
            for arm in v5_lean.ARMS
        },
    )
    if match:
        row["result"]["boundary"] = BOUNDARY
        row["result"]["metrics"].update(
            {
                key: evidence[key]
                for key in (
                    "scheduled_visits",
                    "fresh_iq_visits",
                    "archived_valid_visits",
                    "fresh_receiver_rows",
                    "detector_cpu_s",
                    "detector_wall_s",
                )
            }
        )
        row["detector_receipts_sha256"] = evidence["detector_receipts_sha256"]
    validate_result(row["result"])
    save(report / f"{side}.json", row)


def package(report):
    trial_file, control_file = (report / f"{name}.json" for name in (METHOD, CONTROL))
    records = [json.loads(path.read_bytes()) for path in (trial_file, control_file)]
    trial, control = records
    case = _load_case(CASE)
    for row, method in zip(records, (METHOD, CONTROL), strict=True):
        if (
            (row["id"], row["method"]) != (CASE, method)
            or row["source_archive_sha256"] != case["native"]["sha256"]
            or row["catalog_sha256"] != case["catalog"]["sha256"]
        ):
            raise ValueError("Position receipt differs from its frozen archive authority")
        validate_result(row["result"])
    _, (site,) = references("ds26-common127", [CASE])
    for arm in v5_lean.ARMS:
        distance = distance_km(
            control["result"]["arms"][arm]["latlon"], site["reference"]["baseline"][arm]["latlon"]
        )
        if distance > 1e-6:
            raise ValueError("Fresh archive control differs from the frozen v5 result")
    spectral_position.verify_pair(control, trial)
    trials, synthetic, summaries = [], {}, {}
    for case_id in PRODUCERS:
        blocks, _ = read_blocks(_load_case(case_id), report)
        rows = held(blocks)
        trials.extend(rows)
        summaries[case_id] = summarize(rows)
        synthetic[case_id] = {
            name: dict(
                exact=payload_parity(row),
                integer=counts([row], "integer"),
                fractional=counts([row], "fractional"),
            )
            for name, row in blocks["development"]["controls"].items()
        }
    pooled = summarize(trials)
    exact = all(r["matches_original_control"] and payload_parity(r) for r in trials) and all(
        k["exact"] for group in synthetic.values() for k in group.values()
    )
    summary = dict(
        method=METHOD,
        held=pooled,
        cases=summaries,
        synthetic=synthetic,
        exact=exact,
        accepted=exact and pooled["speed_accepted"],
        position_errors_km={
            row["method"]: {
                arm: distribution([row["position_error_km"][arm]]) for arm in v5_lean.ARMS
            }
            for row in records
        },
    )
    write(report / "qualification.json", encoded(summary) + b"\n")
    for row, name in zip(
        records, ("positions.jsonl.gz", "control-positions.jsonl.gz"), strict=True
    ):
        write(report / name, gzip.compress(encoded(row) + b"\n", mtime=0))
    names = (
        "PROTOCOL.md",
        "qualification.json",
        "source-lock.json",
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        trial_file.name,
        control_file.name,
        *(f"{case}-{split}.json.gz" for case in PRODUCERS for split in detector.SCHEDULE),
    )
    lock = dict(cases=[CASE], files={name: _sha(report / name) for name in names})
    write(report / "prediction-lock.json", encoded(lock) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", METHOD, CONTROL, "package"))
    parser.add_argument("--report", type=Path, default=detector.REPORT)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    report = local_output(args.report)
    if args.action == "package":
        package(report)
        return
    if args.work is None:
        parser.error("supply a fresh work directory")
    work = local_output(args.work)
    if args.action == "prepare":
        prepare(report, work)
        return
    core = 2 if args.action == METHOD else 3
    if os.sched_getaffinity(0) != {core} or any(os.environ.get(k) != "1" for k in THREAD_ENV):
        parser.error("pin the paired worker and its numerical threads")
    fit(args.action, report, work)


if __name__ == "__main__":
    main()
