"""Bounded saved-IQ density experiment using the pinned production detector."""

import argparse
import hashlib
import json
import resource
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SID = "scan-fw-2fab8e56185dc020"
RELEASE = Path("/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def partition(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["target_index"], row["valid_samples"])].append(row["visit_index"])
    held = set()
    for ids in groups.values():
        ranked = sorted(ids, key=lambda i: sha(f"density-v1:{SID}:{i}".encode()))
        held.update(ranked[:round(len(ids) * 0.2)])
    return held


def freeze():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis

    if (ROOT / "spec.json").exists():
        raise RuntimeError("Experiment already frozen")
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        capture = store.inspect(SID)
        receipt = capture.manifest.receipt
        rate = receipt.plan.geometry.sample_rate_hz
        origin = receipt.terminal.first_counter
        rows = [dict(visit_index=v.visit_index, target_index=v.target_index,
                     start_counter=v.valid_start_counter, end_counter=v.valid_end_counter_exclusive,
                     valid_samples=v.valid_end_counter_exclusive-v.valid_start_counter,
                     start_s=(v.valid_start_counter-origin)/rate,
                     end_s=(v.valid_end_counter_exclusive-origin)/rate)
                for v in receipt.events
                if v.valid_start_counter >= origin
                and v.valid_end_counter_exclusive <= origin + 60*rate]
        held = partition(rows)
        for row in rows:
            row["partition"] = "evaluation" if row["visit_index"] in held else "training"
        binding = bind_actual_visit_analysis(receipt,
            input_manifest_sha256=capture.manifest_sha256, probe_stride_ms=120)
        with AdaptiveHopAnalysisStore(Path("/srv/bulk/leo"), read_only=True).job(binding) as job:
            metrics = job.manifest()
            assert metrics is not None
            for row in rows:
                product = job.read_visit(row["visit_index"])
                data = product.model_dump(mode="json")
                write(ROOT / "local/baseline" / f"{row['visit_index']:04}.json", data)
                row["baseline_sha256"] = sha((ROOT / "local/baseline" / f"{row['visit_index']:04}.json").read_bytes())
        write(ROOT / "spec.json", dict(schema="glrt-density-experiment/v1", session_id=SID,
            frozen_utc=datetime.now(UTC).isoformat(), source_manifest_sha256=capture.manifest_sha256,
            release=str(RELEASE), excerpt_seconds=60, probe_ms=20, strides_ms=[120,10,20],
            rows=rows, baseline_binding=binding.sha256, configuration=binding.configuration.model_dump(mode="json"),
            code_hashes={name: sha((RELEASE/"src/leo"/name).read_bytes()) for name in (
                "scanner/detector.py", "scanner/adaptive_hop_analysis.py",
                "analysis/starlink/acquisition.py", "analysis/starlink/pilot_methods.py")},
            reference_policy="Held-out complete visits; same start-of-visit reference for all arms; no held-out refit",
            compute_budget_seconds=1200))
        print(json.dumps(dict(visits=len(rows), heldout=len(held), raw_sha=capture.manifest_sha256)))
    finally:
        store.close()


def run(limit, seconds):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit_batch

    spec = json.loads((ROOT / "spec.json").read_bytes())
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    started = time.monotonic()
    processed = 0
    try:
        capture = store.inspect(SID)
        assert capture.manifest_sha256 == spec["source_manifest_sha256"]
        cfg = bind_actual_visit_analysis(capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256, probe_stride_ms=10).configuration
        with AdaptiveHopAnalysisInputStore(store).source(SID) as source:
            ordinals = {v.event.visit_index:i for i,v in enumerate(source.visits)}
            pending = [r for r in spec["rows"] if r["end_s"] <= 30
                       and not (ROOT / "local/dense" / f"{r['visit_index']:04}.json").exists()]
            for offset in range(0, len(pending), 2):
                if time.monotonic()-started > seconds or processed >= limit:
                    break
                rows = pending[offset:offset+min(2,limit-processed)]
                wall, cpu = time.monotonic(), time.process_time()
                results = list(analyze_adaptive_hop_visit_batch(source,
                    tuple(ordinals[r["visit_index"]] for r in rows), configuration=cfg))
                receipt = dict(visit_indexes=[r["visit_index"] for r in rows], wall_seconds=time.monotonic()-wall,
                    cpu_seconds=time.process_time()-cpu,
                    max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                receipt["products"] = []
                for row,result in zip(rows,results,strict=True):
                    index = row["visit_index"]
                    path = ROOT / "local/dense" / f"{index:04}.json"
                    write(path,result.model_dump(mode="json"))
                    receipt["products"].append(dict(visit_index=index,sha256=sha(path.read_bytes())))
                write(ROOT / "local/timing" / f"batch-{rows[0]['visit_index']:04}.json", receipt)
                processed += len(rows)
                print(json.dumps(receipt), flush=True)
    finally:
        store.close()
    print(json.dumps(dict(batch_wall_seconds=time.monotonic()-started,processed=processed)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=240)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    else:
        run(args.limit, args.seconds)
