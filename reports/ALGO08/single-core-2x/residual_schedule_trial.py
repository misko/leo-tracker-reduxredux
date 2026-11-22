"""Replay residual-only scheduling from the frozen pre-continuation factor ledger."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
import traceback
from unittest.mock import patch

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from receiver_factor_ledger import DETECTOR_SHA256
from solver_trial import measure
from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery
from tools.pipeline_eval.variants.experimental.residual_schedule import MODES, Replay


def read(path, saved_path):
    packed = path.read_bytes()
    ledger = json.loads(gzip.decompress(packed))
    saved = saved_path.read_bytes()
    if ledger["schema_version"] != 1 or ledger["detector_sha256"] != DETECTOR_SHA256:
        raise ValueError("Expected the frozen two-scan factor ledger")
    if sha256(saved).hexdigest() != ledger["saved_detections_sha256"]:
        raise ValueError("Saved detection bytes differ from the matched ledger")
    native = json.loads(saved)
    source, provenance = native["source"], native["provenance"]
    if (
        source["sample_rate_hz"] != 10_000_000
        or source["session_id"] != ledger["session_id"]
        or source["input_manifest_sha256"] != ledger["input_manifest_sha256"]
        or source["raw_recording_authority_digest"] != ledger["raw_authority"]
        or canonical_digest(source["probes"]) != ledger["ordered_selected_sha256"]
        or provenance["detector_sha256"] != "sha256:" + DETECTOR_SHA256
        or provenance["window_count"] != ledger["window_count"]
        or provenance["excluded_windows"] != ledger["excluded_windows"]
        or len(ledger["rows"]) != len(source["probes"])
        or len(ledger["rows"]) != len(ledger["native_cpu_ns"])
    ):
        raise ValueError("Factor ledger and saved detection authority differ")
    for row, original, cpu in zip(ledger["rows"], source["probes"], ledger["native_cpu_ns"], strict=True):
        if (
            {k: v for k, v in row.items() if k != "candidates"}
            != {k: v for k, v in original.items() if k != "candidates"}
            or not all(f["passed_fractional_margin_gate"] is True for f in row["candidates"])
            or type(cpu) is not int or cpu < 0
        ):
            raise ValueError("Expected matching visits, verified factors and native CPU")
    return sha256(packed).hexdigest(), ledger, native


def replay(ledger, mode):
    policy = Replay(mode)
    counts, selected, skipped_cpu = Counter(), [], 0
    start = process_time()
    for row, cpu in zip(ledger["rows"], ledger["native_cpu_ns"], strict=True):
        metadata = {k: v for k, v in row.items() if k != "candidates"}
        factors = row["candidates"]

        def measure_factors(residual_enabled):
            return factors if residual_enabled else [f for f in factors if f["candidate_rank"] == 0]

        residual, observed, admitted = policy.visit(metadata, measure_factors)
        selected.append(dict(metadata, candidates=admitted))
        if residual:
            counts["residual_requests"] += 1
        else:
            counts["skipped_residual_requests"] += 1
            counts["skips_with_confirmed_original_residual_work"] += bool(factors)
            skipped_cpu += cpu
        for f in observed:
            counts[f"observed_rank_{f['candidate_rank']}"] += 1
        for f in admitted:
            counts[f"selected_rank_{f['candidate_rank']}"] += 1
    summary = dict(counts=counts, schedule_reasons=policy.reasons,
                   summed_native_cpu_upper_bound_on_savings_s=skipped_cpu / 1e9,
                   replay_cpu_s=process_time() - start, ordered_selected_sha256=canonical_digest(selected))
    return selected, summary


def changes(original, scheduled):
    rows, counts = [], Counter()
    for before, after in zip(original, scheduled, strict=True):
        a, b = before["candidates"], after["candidates"]
        if a == b:
            continue
        old = None if not a else a[0]["candidate_rank"]
        new = None if not b else b[0]["candidate_rank"]
        change = "changed_selection" if a and b else "lost_selection" if a else "gained_selection"
        counts[change] += 1
        counts[f"rank_{old}_to_{new}"] += 1
        rows.append(dict(visit=before["visit_index"], receiver=before["receiver_id"], old=old, new=new))
    return counts, rows


def solve_variants(native, selected, ledger_digest, archive, assets, offer):
    solved_by_selection = {}
    comparison = {}
    original_rank = v5_core.ranked_initial_nodes

    def rank(scan):
        with dense_discovery(scan, reuse_associations=True):
            return original_rank(scan)

    with patch.object(v5_core, "ranked_initial_nodes", rank):
        for mode in MODES:
            probes = selected[mode]
            key = canonical_digest(probes)
            if key in solved_by_selection:
                comparison[mode] = dict(same_input_as=solved_by_selection[key])
                continue
            doc = native
            if probes != native["source"]["probes"]:
                digest = canonical_digest(["residual-schedule-ledger-replay", ledger_digest, mode, probes])
                doc = dict(native,
                           source=dict(native["source"], probes=probes, analysis_manifest_sha256=digest),
                           provenance=dict(native["provenance"], scope="offline-residual-schedule",
                                           run_id=f"residual-replay-{digest[7:39]}"))
            began = process_time()
            try:
                comparison[mode] = measure("combined", doc, archive, assets, offer)
            except (ValueError, AssertionError) as error:
                comparison[mode] = dict(
                    cpu_s=process_time() - began,
                    decision=dict(status="failed", reason=str(error),
                                  frame=traceback.extract_tb(error.__traceback__)[-1].name),
                )
            solved_by_selection[key] = mode
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("detections", type=Path)
    for name in ("archive", "assets", "region"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.archive is not None and (args.assets is None or args.region is None):
        parser.error("A solver comparison needs --archive, --assets and --region")
    ledger_digest, ledger, native = read(args.ledger, args.detections)
    selected, summary = {}, {}
    for mode in MODES:
        selected[mode], summary[mode] = replay(ledger, mode)
    original = selected["always-two"]
    if original != native["source"]["probes"]:
        raise ValueError("The full replay failed to reproduce every saved selection")
    for mode in MODES[1:]:
        summary[mode]["selection_changes"], summary[mode]["changed_rows"] = changes(original, selected[mode])
    result = dict(ledger_sha256=ledger_digest, detector_sha256=DETECTOR_SHA256,
                  saved_detections_sha256=ledger["saved_detections_sha256"],
                  raw_authority=ledger["raw_authority"], recorded_native_cpu_s=sum(ledger["native_cpu_ns"]) / 1e9,
                  native_rank_histogram=Counter(str(tuple(f["candidate_rank"] for f in row["candidates"]))
                                                for row in ledger["rows"]),
                  probes=len(original), modes=summary)
    if args.archive is not None:
        offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
        result["region"] = offer.document()
        if all(selected[mode] == original for mode in MODES):
            result["solver"] = dict(same_saved_selection_in_all_modes=True)
        else:
            result["solver"] = solve_variants(native, selected, ledger_digest, TleArchiveReader(args.archive),
                                              args.assets, offer)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
