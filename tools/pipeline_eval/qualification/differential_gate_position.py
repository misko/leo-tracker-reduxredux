"""Seal the differential detector audit and a real partial-IQ position comparison."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import median

from ..__main__ import THREAD_ENV, encoded, local_output, references, write
from ..scoring import distance_km, distribution, validate_result
from ..variants import anchor_receiver, v5_lean
from . import differential_gate_eval as detector
from .dense_q10_position import _archive
from .full_v5_check import MARGIN_GATE, PRODUCERS, _load_case, _measure, _sha
from .recording_to_v5 import digest, save
from .sparse_epoch_position import counts
from .spectral_position import fit

CASE = "DS26-0036"
METHOD = detector.METHOD
CONTROL = "differential_gate_capture_control"
MODES = ("control", METHOD)
BOUNDARY = "Experimental differential acquisition on eight held raw visits with remaining archive"
TIMES = ("coarse_cpu_s", "full_cpu_s", "full_wall_s")


def read(case, report):
    files, blocks = {}, []
    lock = detector.frozen_sources()
    if detector.LOCK.read_bytes() != encoded(lock) + b"\n":
        raise ValueError("Qualification source differs from the predeclared lock")
    for split, (segment, sequences) in detector.SCHEDULE.items():
        path = report / f"{case['id']}-{split}.json.gz"
        block = json.loads(gzip.decompress(path.read_bytes()))
        if (
            (block["case"], block["segment"], block["split"]) != (case["id"], segment, split)
            or tuple(row["sequence"] for row in block["rows"]) != sequences
            or block["source_sha256"] != lock
            or block["producer"]["run_id"] != case["run_id"]
            or block["cpus"] != [detector.CPUS[case["id"]]]
            or any(block[k] != b[k] for b in blocks for k in ("producer", "library_sha256"))
            or any(
                not row["stable"] or not row["equal_status"] or not row["matches_original_control"]
                for row in block["rows"]
            )
        ):
            raise ValueError(f"Recorded panel failed capture and source binding: {path.name}")
        files[split] = _sha(path)
        blocks.append(block)
    return blocks, files


def prepare(report, work):
    case = _load_case(CASE)
    archive = json.loads(_archive(case).read_bytes())
    blocks, files = read(case, report)
    rows = [r for block in blocks for r in block["rows"]]
    audit = _measure(case, rows, archive["source"]["sample_rate_hz"])
    if audit["different_probe_keys"] or not audit["archive_exclusions_equal"]:
        raise ValueError("Matched dense control did not reproduce the archived native factors")
    block = blocks[0]
    replay = dict(
        rows=rows,
        producer=block["producer"],
        source_sha256=digest(block["source_sha256"]),
        kernel_sha256=block["library_sha256"]["spectral"],
        archive_audit=audit,
    )
    composite, changed = anchor_receiver.splice_probes(archive, replay)
    composite["provenance"]["scope"] = BOUNDARY
    valid = sum(row["policy_status"] == "processed" for row in rows)
    work.mkdir(parents=True, exist_ok=False)
    output = work / "partial-iq-native.json"
    save(output, composite)
    save(
        work / "prepared.json",
        dict(
            composite_sha256=_sha(output),
            detector_receipts_sha256=files,
            fresh_iq_visits=valid,
            scheduled_visits=len(rows),
            modified_receiver_rows=changed,
            archived_valid_visits=archive["provenance"]["processed_windows"] - valid,
        ),
    )


def position(side, report, work):
    case = _load_case(CASE)
    archive = _archive(case)
    prepared = json.loads((work / "prepared.json").read_bytes())
    trial = side == METHOD
    native = work / "partial-iq-native.json" if trial else archive
    expected = prepared["composite_sha256"] if trial else case["native"]["sha256"]
    if _sha(native) != expected:
        raise ValueError("Prepared native position input changed")
    row = fit(case, native, work / side, side)
    if row["input_sha256"] != f"sha256:{expected}":
        raise ValueError("The position worker consumed a different native input")
    _, (site,) = references("ds26-common127", [CASE])
    row.update(
        source_archive_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        position_error_km={
            arm: distance_km(row["result"]["arms"][arm]["latlon"], site["truth"])
            for arm in v5_lean.ARMS
        },
    )
    if trial:
        row["result"]["boundary"] = BOUNDARY
        row["result"]["metrics"].update(prepared)
    else:
        for arm in v5_lean.ARMS:
            actual = row["result"]["arms"][arm]["latlon"]
            frozen = site["reference"]["baseline"][arm]["latlon"]
            if distance_km(actual, frozen) > 1e-6:
                raise ValueError("Fresh capture control differs from the frozen reference")
    validate_result(row["result"])
    save(report / f"{side}.json", row)


def stats(rows):
    valid = [row for row in rows if row["policy_status"] == "processed"]
    timing = {
        mode: {key: [t[key] for r in valid for t in r["timings"][mode]] for key in TIMES}
        for mode in MODES
    }
    pooled = {mode: {f: sum(v) for f, v in fields.items()} for mode, fields in timing.items()}
    full_saving = 1 - pooled[METHOD]["full_cpu_s"] / pooled["control"]["full_cpu_s"]
    return dict(
        visits=len(rows),
        valid=len(valid),
        exact_payloads=sum(r["exact_payload"] for r in valid),
        integer=counts(valid, "integer"),
        fractional=counts(valid, "fractional"),
        pooled_s=pooled,
        medians_s={
            mode: {f: median(v) for f, v in fields.items()} for mode, fields in timing.items()
        },
        coarse_speedup=pooled["control"]["coarse_cpu_s"] / pooled[METHOD]["coarse_cpu_s"],
        fractional_full_cpu_saving=full_saving,
    )


def _truth_check(row):
    audit = row["audit"]["fractional"]

    def recovered(plant, candidates):
        limit = 1000 + 0.01 * abs(plant["drift_hz_s"])
        for c in candidates:
            delta = c["epoch"] + (c["offset"] or 0.0) - plant["epoch"] - plant["offset"]
            delta = (delta + 13333 / 2) % 13333 - 13333 / 2
            if (
                abs(delta) <= 2
                and abs(c["cfo"] - plant["cfo"]) <= limit
                and c["margin"] >= MARGIN_GATE
            ):
                return True
        return False

    return [
        dict(
            plant=plant,
            receivers={
                rx: {
                    mode: recovered(plant, entries[side])
                    for mode, side in zip(MODES, ("control", "trial"), strict=True)
                }
                for rx, entries in audit.items()
            },
        )
        for plant in row["truth"]
    ]


def package(report):
    raw, summaries, synthetic = [], {}, {}
    for ident in PRODUCERS:
        blocks, _ = read(_load_case(ident), report)
        held = [r for block in blocks for r in block["rows"]]
        raw.extend(held)
        summaries[ident] = stats(held)
        synthetic[ident] = {
            name: dict(
                integer=counts([row], "integer"),
                fractional=counts([row], "fractional"),
                truth_recovery=_truth_check(row),
            )
            for name, row in blocks[0]["controls"].items()
        }
    records = [json.loads((report / f"{method}.json").read_bytes()) for method in (METHOD, CONTROL)]
    trial, control = records
    if any(trial[k] != control[k] for k in ("id", "source_archive_sha256", "catalog_sha256")) or (
        trial["input_sha256"] == control["input_sha256"]
    ):
        raise ValueError("The archive and trial must share authority and use distinct inputs")
    pooled = stats(raw)
    field_counts = (pooled["fractional"], pooled["integer"])
    science = all(c["missed"] == c["added"] == c["winner_changes"] == 0 for c in field_counts)
    plants = [
        outcomes[METHOD]
        for controls in synthetic.values()
        for control in controls.values()
        for truth in control["truth_recovery"]
        for outcomes in truth["receivers"].values()
    ]
    quality = dict(
        method=METHOD,
        held=pooled,
        cases=summaries,
        synthetic=synthetic,
        science_accepted=science and all(plants),
        speed_accepted=pooled["coarse_speedup"] >= 10
        and pooled["fractional_full_cpu_saving"] >= 0.25,
        position_errors_km={
            row["method"]: {
                arm: distribution([row["position_error_km"][arm]]) for arm in v5_lean.ARMS
            }
            for row in records
        },
    )
    write(report / "qualification.json", encoded(quality) + b"\n")
    files = ["PROTOCOL.md", "source-lock.json", "qualification.json"]
    for row, filename in zip(
        records, ("positions.jsonl.gz", "control-positions.jsonl.gz"), strict=True
    ):
        write(report / filename, gzip.compress(encoded(row) + b"\n", mtime=0))
        files.extend((filename, f"{row['method']}.json"))
    files.extend(f"{case}-{split}.json.gz" for case in PRODUCERS for split in detector.SCHEDULE)
    lock = dict(cases=[CASE], files={name: _sha(report / name) for name in files})
    write(report / "prediction-lock.json", encoded(lock) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", METHOD, CONTROL, "package"))
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.action == "package":
        package(detector.REPORT)
        return
    if args.work is None:
        parser.error("provide a local work directory")
    work = local_output(args.work)
    if args.action == "prepare":
        prepare(detector.REPORT, work)
        return
    core = 1 if args.action == METHOD else 21
    if os.sched_getaffinity(0) != {core} or any(os.environ.get(k) != "1" for k in THREAD_ENV):
        parser.error("pin the paired worker and numerical threads")
    position(args.action, detector.REPORT, work)


if __name__ == "__main__":
    main()
