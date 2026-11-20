"""Fit actual stride-six replay factors on held visits and capture-era controls."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import median

from leo.contracts.fast_scan_native import FastScanWindowResultV2

from ..__main__ import THREAD_ENV, encoded, local_output, references, write
from ..scoring import distance_km, distribution, validate_result
from ..variants import anchor_receiver, v5_lean
from . import sparse_epoch_eval as detector
from . import spectral_position
from .full_v5_check import BULK, PRODUCERS, _load_case, _measure, _sha
from .recording_to_v5 import digest, save

METHOD = detector.METHOD
CONTROL = "sparse_epoch_capture_control"
BOUNDARY = "Eight scheduled stride-six IQ visits plus archived factors to paired v5 position"
TIMES = ("coarse_cpu_s", "full_cpu_s", "full_wall_s")


def read_blocks(case, report):
    blocks, hashes = {}, {}
    audit_script = Path(detector.__file__).name
    implementation = {k: v for k, v in detector.source_hashes().items() if k != audit_script}
    for split, (segment, sequences) in detector.SCHEDULE.items():
        path = report / f"{case['id']}-{split}.json.gz"
        block = json.loads(gzip.decompress(path.read_bytes()))
        if (
            (block["case"], block["split"], block["segment"]) != (case["id"], split, segment)
            or {k: v for k, v in block["source_sha256"].items() if k != audit_script} != implementation
            or block["producer"]["run_id"] != case["run_id"]
            or block["cpus"] != [detector.CASE_CPUS[case["id"]]]
            or tuple(row["sequence"] for row in block["rows"]) != sequences
            or any(not row["stable"] or not row["equal_status"] or not row["iq_sha256"]
                   or not row["matches_original_control"] for row in block["rows"])
            or any(block[key] != other[key] for other in blocks.values()
                   for key in ("producer", "library_sha256", "source_sha256", "numpy"))
        ):
            raise ValueError(f"Unmatched stride-six qualification block {path.name}")
        blocks[split], hashes[split] = block, _sha(path)
    return blocks, hashes


def held_rows(blocks):
    return [r for split in ("early", "late") for r in blocks[split]["rows"]]


def counts(rows, name):
    rx = [r for row in rows for r in row["audit"][name].values()]
    return dict(receivers=len(rx), control_positives=sum(r["control_positives"] for r in rx),
                trial_positives=sum(r["trial_positives"] for r in rx),
                missed=sum(len(r["missed_positive"]) for r in rx),
                added=sum(len(r["new_positive"]) for r in rx),
                winner_changes=sum(not r["winner_equal"] for r in rx),
                maximum_matched_margin_change=max(
                    (abs(d) for r in rx for d in r["matched_margin_delta"]), default=0.0))


def verified_audit(row):
    """Recompute one-to-one matching from the immutable timed public payloads."""
    payloads = [row["payloads"][mode] for mode in detector.MODES]
    if [detector._digest(encoded(p)) for p in payloads] != [
        row["payload_sha256"][mode] for mode in detector.MODES
    ]:
        raise ValueError("Stored public payload is inconsistent with the timed detector run")
    outputs = [FastScanWindowResultV2.model_validate(p) for p in payloads]
    return dict(row, audit=detector._audit(*outputs, epochs=13333))


def planted_recovery(row):
    truth = row["truth"]
    planted = [] if truth is None else truth.get("signals", [])
    if truth is not None and not planted:
        planted = [(truth["epoch"], truth["cfo"], None)]
    return [dict(epoch=epoch, cfo_hz=cfo, amplitude=amplitude, receivers={
        rx_id: {
            mode: any(c["margin"] >= detector.MARGIN_GATE and detector.matches(
                c, dict(epoch=epoch, offset=0, cfo=cfo), 13333) for c in rx[field])
            for mode, field in zip(detector.MODES, ("control", "trial"), strict=True)
        } for rx_id, rx in row["audit"]["fractional"].items()
    }) for epoch, cfo, amplitude in planted]


def summarize(rows):
    active = [r for r in rows if r["policy_status"] == "processed"]
    timings = {mode: {field: [t[field] for row in active for t in row["timings"][mode]]
                      for field in TIMES} for mode in detector.MODES}
    pooled = {mode: {key: sum(values) for key, values in measures.items()}
              for mode, measures in timings.items()}
    coarse_ratio = pooled["control"]["coarse_cpu_s"] / pooled[METHOD]["coarse_cpu_s"]
    full_saving = 1 - pooled[METHOD]["full_cpu_s"] / pooled["control"]["full_cpu_s"]
    return dict(scheduled_visits=len(rows), processed_visits=len(active),
                exact_payloads=sum(row["exact_payload"] for row in active),
                integer=counts(active, "integer"), fractional=counts(active, "fractional"),
                pooled_timing_s=pooled,
                median_timing_s={mode: {field: median(values) for field, values in data.items()}
                                 for mode, data in timings.items()},
                coarse_speedup=coarse_ratio, full_detector_cpu_saving=full_saving,
                passed_speed_gate=coarse_ratio >= 2 and full_saving >= .10)


def position(case_id, report, work):
    case = _load_case(case_id)
    archive_path, archive_sha = BULK / case["native"]["path"], case["native"]["sha256"]
    catalog_path, catalog_sha = BULK / case["catalog"]["path"], case["catalog"]["sha256"]
    if _sha(archive_path) != archive_sha or _sha(catalog_path) != catalog_sha:
        raise ValueError("Capture-era native or catalogue input changed")
    blocks, hashes = read_blocks(case, report)
    rows = held_rows(blocks)
    archive = json.loads(archive_path.read_bytes())
    audit = _measure(case, rows, archive["source"]["sample_rate_hz"])
    if not audit["archive_exclusions_equal"] or audit["different_probe_keys"]:
        raise ValueError("The held accelerated control differs from the capture archive")
    identity = dict(rows=rows, producer=blocks["early"]["producer"], archive_audit=audit,
                    source_sha256=digest(blocks["early"]["source_sha256"]),
                    kernel_sha256=blocks["early"]["library_sha256"]["sparse"])
    composite, changed_rows = anchor_receiver.splice_probes(archive, identity)
    composite["provenance"]["scope"] = BOUNDARY
    work.mkdir(parents=True, exist_ok=False)
    native_path = work / "partial-iq-native.json"
    save(native_path, composite)
    jobs = ((archive_path, CONTROL), (native_path, METHOD))
    if case_id == "DS29-0082":
        jobs = jobs[::-1]
    results = {method: spectral_position.fit(case, path, work / method, method)
               for path, method in jobs}
    trial, control = results[METHOD], results[CONTROL]
    if (trial["input_sha256"] != f"sha256:{_sha(native_path)}"
            or control["input_sha256"] != f"sha256:{archive_sha}"
            or trial["input_sha256"] == control["input_sha256"]):
        raise ValueError("Actual v5 input identities did not match the two armed runs")
    _, (site,) = references("ds26-common127" if case["panel"] == "DS26" else "roof16", [case_id])
    for arm in v5_lean.ARMS:
        if distance_km(control["result"]["arms"][arm]["latlon"],
                       site["reference"]["baseline"][arm]["latlon"]) > 1e-6:
            raise ValueError("Fresh archive control disagrees with frozen v5 coordinates")
    metrics, stock = (row["result"]["metrics"] for row in (trial, control))
    valid = sum(r["policy_status"] == "processed" for r in rows)
    trial["result"]["boundary"] = BOUNDARY
    metrics.update(scheduled_visits=len(rows), fresh_iq_visits=valid,
                   replayed_capture_exclusions=len(rows) - valid,
                   archived_valid_visits=archive["provenance"]["processed_windows"] - valid,
                   archived_receiver_rows=len(archive["source"]["probes"]) - audit["exact_probe_rows"],
                   modified_receiver_rows=changed_rows, fresh_receiver_rows=audit["exact_probe_rows"],
                   same_prepared_observations=metrics["observations_sha256"] == stock["observations_sha256"],
                   same_tracking_arcs=metrics["tracks_sha256"] == stock["tracks_sha256"],
                   same_final_owners=metrics["final_owners_sha256"] == stock["final_owners_sha256"],
                   detector_cpu_s=sum(r["timings"][METHOD][0]["full_cpu_s"] for r in rows),
                   detector_wall_s=sum(r["timings"][METHOD][0]["full_wall_s"] for r in rows),
                   control_input_sha256=control["input_sha256"])
    trial.update(variant="partial-iq-sparse-epoch", detector_receipts_sha256=hashes,
                 implementation_sha256=identity["source_sha256"])
    for row in (trial, control):
        row.update(source_archive_sha256=archive_sha, catalog_sha256=catalog_sha,
                   position_error_km={arm: distance_km(row["result"]["arms"][arm]["latlon"],
                                                     site["truth"]) for arm in v5_lean.ARMS})
        validate_result(row["result"])
        save(report / f"{case_id}-{row['method']}.json", row)


def package(report):
    records = {METHOD: [], CONTROL: []}
    details, complete, controls = {}, [], {}
    audits, mismatches = {}, []
    for case_id in PRODUCERS:
        blocks, _ = read_blocks(_load_case(case_id), report)
        raw = held_rows(blocks)
        active = [verified_audit(row) for row in raw]
        audits[case_id] = {row["visit"]: row["audit"] for row in active}
        mismatches.extend(dict(case=case_id, visit=actual["visit"])
                          for saved, actual in zip(raw, active, strict=True)
                          if encoded(saved["audit"]) != encoded(actual["audit"]))
        details[case_id] = summarize(active)
        plants = {name: verified_audit(row) for name, row in blocks["development"]["controls"].items()}
        controls[case_id] = {name: dict(plants=planted_recovery(row), **{
            field: counts([row], field) for field in ("integer", "fractional")
        }) for name, row in plants.items()}
        complete.extend(active)
        for method in records:
            row = json.loads((report / f"{case_id}-{method}.json").read_bytes())
            if (row["id"], row["method"]) != (case_id, method):
                raise ValueError("Unexpected position receipt identity")
            validate_result(row["result"])
            records[method].append(row)
    pooled = summarize(complete)
    science = [pooled, *(x for group in controls.values() for x in group.values())]
    accepted = pooled["passed_speed_gate"] and all(
        s[name]["missed"] == s[name]["added"] == s[name]["winner_changes"] == 0
        for s in science for name in ("integer", "fractional")
    )
    errors = {method: {arm: distribution(row["position_error_km"][arm] for row in rows)
                       for arm in v5_lean.ARMS} for method, rows in records.items()}
    write(report / "qualification.json", encoded(dict(method=METHOD, accepted=accepted,
          held=pooled, cases=details, synthetic=controls, position_errors_km=errors)) + b"\n")
    write(report / "score-audit.json.gz", gzip.compress(encoded(dict(
        held=audits, corrected_raw_audit_visits=mismatches,
        analysis_source_sha256={path.name: _sha(path) for path in (Path(__file__), Path(detector.__file__))},
    )), mtime=0))
    for method, name in ((METHOD, "positions.jsonl.gz"), (CONTROL, "control-positions.jsonl.gz")):
        write(report / name, gzip.compress(b"".join(encoded(r) + b"\n" for r in records[method]), mtime=0))
    names = ("PROTOCOL.md", "qualification.json", "score-audit.json.gz",
             "positions.jsonl.gz", "control-positions.jsonl.gz",
             *(f"{case}-{split}.json.gz" for case in PRODUCERS for split in detector.SCHEDULE),
             *(f"{case}-{method}.json" for case in PRODUCERS for method in records))
    lock = dict(cases=list(PRODUCERS), files={name: _sha(report / name) for name in names})
    write(report / "prediction-lock.json", encoded(lock) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--case", choices=PRODUCERS)
    actions.add_argument("--package", action="store_true")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    report = local_output(args.report)
    if args.package:
        package(report)
        return
    if args.work is None or os.sched_getaffinity(0) != {detector.CASE_CPUS[args.case]} or any(
        os.environ.get(name) != "1" for name in THREAD_ENV
    ):
        parser.error("pin the designated core, provide --work and set numerical threads to one")
    work = local_output(args.work)
    if work.is_relative_to(BULK / "leo") or report.is_relative_to(BULK / "leo"):
        parser.error("choose outputs outside the recording archive")
    position(args.case, report, work)


if __name__ == "__main__":
    main()
