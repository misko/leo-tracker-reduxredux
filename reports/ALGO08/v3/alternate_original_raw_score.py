"""Verify the sealed original raw comparison before scoring against the survey."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from alternate_original_raw_trial import (MEMBERS_PIN, SAVED, SAVED_NATIVE_PIN, SAVED_RESULT_PIN, SAVED_SEAL_PIN,
                                          checked, read, sources)


ARMS = ("c0", "fitted_c")
REF_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
FULL_NATIVE_PIN = "4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"


def factor_delta(before, after):
    key = lambda row: (row["visit_index"], row["receiver_id"])
    if [key(row) for row in before] != [key(row) for row in after]:
        raise ValueError("Measured raw factors changed the ordered signed receiver slots")
    delta = dict(lost=[], added=[], changed=[])
    witnesses = []
    for a, b in zip(before, after, strict=True):
        av, bv = (row["candidates"] for row in (a, b))
        if {k: v for k, v in a.items() if k != "candidates"} != {k: v for k, v in b.items() if k != "candidates"}:
            raise ValueError("Raw measured slot differs from the saved signed metadata")
        if av != bv:
            kind = "lost" if not bv else "added" if not av else "changed"
            delta[kind].append(key(a))
            witnesses.append(dict(slot=key(a), before=av, after=bv))
    return dict(slots=len(before), factor_counts=[sum(len(row["candidates"]) for row in rows) for rows in (before, after)],
                differences=delta, witnesses=witnesses)


def reference():
    base = Path(__file__).resolve().parents[3]
    body = subprocess.check_output(["git", "-c", f"safe.directory={base}", "-C", str(base), "show",
                                   "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if sha256(body).hexdigest() != REF_PIN:
        raise ValueError("The archived DS30 survey changed")
    (row,) = (r["reference"] for r in json.loads(body)["cases"] if r["dataset_label"] == "DS30-0016"
              and r["authority_eligible"] and r["sealed_metadata_digests_verified"])
    return [row["latitude_deg"], row["longitude_deg"]]


def published(root, mode):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence, verify_v3_publication

    clock = read(root / (mode + "-clock.json"))["clock"]
    product = root / mode
    receipt = json.loads((root / (mode + ".stdout")).read_text().splitlines()[-1])
    if mode == "stock":
        verify_v3_publication(product, receipt)
    science = evidence(product, receipt, clock["started_unix_ns"], read_only=True)
    (native_path,) = product.glob("fast-scan-automatic-work/*/detections.json")
    native = read(native_path)
    terminal = read(product / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    if canonical_digest(native) != terminal["native_sha256"]:
        raise ValueError("Published terminal does not bind the actual raw acquisition")
    media, replay, grid_summary = artifacts(product, receipt), None, None
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(product)
        grid = store.position_grid(receipt["run_id"])
        if not grid["complete"] or grid["evaluated_points"] != grid["planned_points"] or grid["evaluated_points"] != 179:
            raise ValueError("The complete fix lacks its standard 179-point grid")
        replay = store.detail(receipt["run_id"])["objective_replay"]
        scores = {(row["east_km"], row["north_km"]): row["scores"] for row in grid["points"]}
        grid_summary = {arm: scores[tuple(grid["endpoints"][arm])][arm] for arm in ARMS}
    return (dict(clock=clock, terminal=terminal, science=science, media=media, objective_replay=replay,
                 grid_endpoint_scores=grid_summary), native)


def failed_candidate(root, complete, result):
    from leo.contracts.digests import canonical_digest

    product = root / "candidate"
    workspace = product / "fast-scan-automatic-work"
    (path,) = workspace.glob("*/detections.json")
    if any(workspace.glob("*/terminal.json")) or any(product.rglob("*.png")):
        raise ValueError("Expected a sealed acquisition without a terminal or figure")
    native = read(path)
    saved = json.loads(checked(SAVED / "restricted-native.json", SAVED_NATIVE_PIN))
    members = json.loads(checked(SAVED / "members.json", MEMBERS_PIN))
    p = native["provenance"]
    saved_p = saved["provenance"]
    raw, before, installed = (r["source"] for r in (native, saved, complete))
    selection = p["research_sampling"]
    skipped = saved_p["research_sampling"]["skipped_acquisition_windows"]
    if (selection["skipped_acquisition_windows"] != skipped
            or p["processed_windows"] != saved_p["processed_windows"]
            or p["excluded_windows"] != saved_p["excluded_windows"]
            or selection["members_sha256"] != canonical_digest(members)
            or selection["omitted_payload_verification"] != "signed manifest and index attestations only"
            or canonical_digest(complete) != "sha256:" + FULL_NATIVE_PIN
            or any(not raw[key] == before[key] == installed[key] for key in (
                "session_id", "probe_ms", "input_manifest_sha256", "raw_recording_authority_digest"))
            or any(not native[k] == saved[k] == complete[k] for k in (
                "clock_anchor", "delivery_clocks", "last_sample_counter"))):
        raise ValueError("The failed worker must still reproduce the original signed acquisition ledger")
    result.update(qualified=False, reason="solver_failed_before_terminal", raw_native_sha256=canonical_digest(native),
                  saved_mask_seal_sha256=SAVED_SEAL_PIN, saved_mask_result_sha256=SAVED_RESULT_PIN,
                  ledger_verified=True, terminal_published=False, factor_comparison=factor_delta(before["probes"], raw["probes"]),
                  acquisition=dict(processed=p["processed_windows"], invalid=p["invalid_capture"], skipped=len(skipped),
                      verified_payload_members=sum(m["retained"] for m in members), index_members=len(members),
                      retained_bytes=sum(m["compressed_bytes"] for m in members if m["retained"]),
                      omitted_bytes=sum(m["compressed_bytes"] for m in members if not m["retained"]),
                      omitted_payloads="manifest and index attestations only"))


def score(root, stock_root=None, destination=None):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from history_risk_0016_raw import roster
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta
    from raw_0016_best_score import STOCK_OWNERS, STOCK_OWNERS_SHA
    from tools.pipeline_eval.scoring import distance_km

    book = read(root / "admission.json")
    seal = root / "prediction-seal.json"
    if (book["case"] != "DS30-0016" or book["sources"] != sources() or read(seal) != output_seal(root)):
        raise ValueError("The frozen raw job has changed since publication")
    stock_root = root if stock_root is None else stock_root
    destination = root / "result.json" if destination is None else destination
    clocks = {mode: read(home / (mode + "-clock.json"))["clock"]
              for mode, home in (("candidate", root), ("stock", stock_root))
              if (home / (mode + "-clock.json")).exists()}
    result = dict(schema="leo.research.alternate-original-raw.v1", case=book["case"], clocks=clocks, admission=book,
                  prediction_seal_sha256=sha256(seal.read_bytes()).hexdigest(), qualified=False)
    if len(clocks) != 2 or clocks["stock"]["exit_code"]:
        write(destination, result)
        return
    if stock_root != root:
        stock_book = read(stock_root / "admission.json")
        control = stock_root / "prediction-seal.json"
        context = stock_root / "process-context.json"
        current = roster(stock_root) | {context.name: sha256(context.read_bytes()).hexdigest()}
        if (read(control) != current or stock_book["request"] != book["request"]
                or stock_book["machine"] != book["machine"] or stock_book["custody"] != book["source_custody"]):
            raise ValueError("Fresh installed raw control differs from the sealed candidate input")
        result["stock_seal_sha256"] = sha256(control.read_bytes()).hexdigest()
    stock, complete = published(stock_root, "stock")
    parent = json.loads(checked(SAVED / "result.json", SAVED_RESULT_PIN))
    parity = {key: stock["science"][key] == parent["installed"][key]
              for key in ("arms", "artifacts", "owners", "scientific_digests")}
    parity["decoded_images"] = (canonical_digest(stock["media"]["images"])
                                == canonical_digest(parent["installed_figures"]))
    if not all(parity.values()):
        raise ValueError("The fresh installed benchmark changed the archived standard publication")
    result["stock_archive_parity"] = parity
    if clocks["candidate"]["exit_code"]:
        failed_candidate(root, complete, result)
        truth = reference()
        result["stock_publication"] = stock
        result["installed_horizontal_error_m"] = {
            arm: 1000 * distance_km(truth, stock["science"]["arms"][arm]["latlon"]) for arm in ARMS}
        write(destination, result)
        return
    candidate, native = published(root, "candidate")
    saved = json.loads(checked(SAVED / "restricted-native.json", SAVED_NATIVE_PIN))
    raw_receipt = read(root / "candidate/member-receipt.json")
    sampling = native["provenance"]["research_sampling"]
    ledger = raw_receipt["acquisition"]
    omitted = [m for m in ledger["members"] if not m["retained"]]
    retained = [m for m in ledger["members"] if m["retained"]]
    truth = reference()
    geography = {mode: {arm: dict(latlon=row["latlon"], error_m=1000 * distance_km(truth, row["latlon"]),
                                  rf_rms_hz=row["rf_rms_hz"]) if row["latlon"] is not None else None
                        for arm, row in publication["science"]["arms"].items()}
                 for mode, publication in (("candidate", candidate), ("stock", stock))}
    full_owners = json.loads(checked(STOCK_OWNERS, STOCK_OWNERS_SHA))
    if full_owners["receipt"]["terminal_sha256"] != stock["science"]["receipt"]["terminal_sha256"]:
        raise ValueError("The fresh installed control differs from its archived full terminal")
    baseline_rows = full_owners["selected_rows"]
    owners = {mode: {arm: owner_delta(rows[arm], raw_receipt["selected_rows"].get(arm, [])) for arm in ARMS}
              for mode, rows in (("stock", baseline_rows), ("saved_mask", parent["candidate"]["selected_rows"]))}
    error_delta = {arm: geography["candidate"][arm]["error_m"] - geography["stock"][arm]["error_m"]
                   if geography["candidate"][arm] is not None else None for arm in ARMS}
    checks = dict(
        same_original=canonical_digest(complete) == "sha256:" + FULL_NATIVE_PIN
        and native["clock_anchor"] == saved["clock_anchor"] == complete["clock_anchor"]
        and native["delivery_clocks"] == saved["delivery_clocks"] == complete["delivery_clocks"]
        and native["last_sample_counter"] == saved["last_sample_counter"] == complete["last_sample_counter"]
        and all(native["source"][key] == complete["source"][key] for key in (
            "session_id", "raw_recording_authority_digest", "input_manifest_sha256", "probe_ms")),
        saved_mask=sampling["members_sha256"] == parent["admission"]["members_sha256"]
        and sampling["skipped_acquisition_windows"] == saved["provenance"]["research_sampling"]["skipped_acquisition_windows"]
        and native["provenance"]["excluded_windows"] == saved["provenance"]["excluded_windows"],
        verified_indices_and_retained=all(m["index_verified"] for m in ledger["members"])
        and all(m["compressed_verified"] and m["decoded_chunk_verified"] and m["per_window_iq_verified"] for m in retained)
        and all(not m["payload_opened"] and not m["compressed_verified"] and not m["per_window_iq_verified"] for m in omitted),
        standard_products=candidate["science"]["receipt"]["decision"] == "complete"
        and len(candidate["media"]["images"]) == 8
        and all(candidate["objective_replay"][arm] == 0 for arm in ARMS),
        accuracy=all(delta is not None and delta <= 250 for delta in error_delta.values()),
    )
    result.update(qualified=all(checks.values()), checks=checks, survey_sha256=REF_PIN, raw_receipt=raw_receipt,
                  saved_mask_seal_sha256=SAVED_SEAL_PIN, saved_mask_result_sha256=SAVED_RESULT_PIN,
                  timing_speedup=clocks["stock"]["elapsed_s"] / clocks["candidate"]["elapsed_s"],
                  geography=geography, horizontal_error_delta_m=error_delta, owners=owners,
                  factor_comparison=factor_delta(saved["source"]["probes"], native["source"]["probes"]),
                  publications=dict(candidate=candidate, stock=stock))
    write(destination, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--stock-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    score(args.root, args.stock_root, args.output)
