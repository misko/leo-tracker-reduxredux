"""Long saved-schedule replay against the actual opt-in SDK, without RF/IQ reads.

Uses component-owned test timing gates and synthetic zero detector input. This
is admission qualification, not new ARM latency, RF recall or capture duty.
"""

import argparse
import gzip
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from tests.scanner.fair_admission_harness import ORIGIN, Geometry, build, run
from tools.evaluate_scanner_admission import Visit, evaluate, simulate, summarize
from tools.native_presence import ROOT
from tools.scanner_sampled_admission_model import simulate as sampled_simulate


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    snapshot = json.loads(gzip.decompress(path.read_bytes()))
    baseline = evaluate(snapshot)  # Existing strict public binding/geometry checks.
    publication = snapshot["responses"]["glrt"]["body"]
    rate = baseline["sample_rate_hz"]
    rows = publication["evidence"]["results"]
    origin = int(rows[0]["valid_start"])
    geometry = [
        Geometry(
            ORIGIN + int(row["valid_start"]) - origin,
            ORIGIN + int(row["valid_end"]) - origin,
            row["channel"] - 1 + 4 * (row["edge"] == "upper"),
        )
        for row in rows
    ]
    costs = [row["wall_ms"] for row in rows if row["search_window_mask"] == 63]
    visits = [Visit(i, g.target, (g.end - ORIGIN) * 1000 / rate) for i, g in enumerate(geometry)]
    return baseline, rate, geometry, np.asarray(costs), visits


def profiles(costs, count):
    rng = np.random.default_rng(20260910)
    yield "median", np.full(count, np.median(costs)), (0,)
    yield "p99", np.full(count, np.percentile(costs, 99)), (0,)
    yield "resampled_jitter", rng.choice(costs, count, replace=True), (0, 3, 8, 1, 9, 5)


def evaluate_case(sdk, worker, output, path, label, costs, jitter, inputs):
    baseline, rate, geometry, _, visits = inputs
    before = time.monotonic()
    result = run(
        sdk, worker, output / "working", rate, geometry, costs.tolist(), owner_jitter_ms=jitter
    )
    elapsed = time.monotonic() - before
    actual = summarize(visits, [row["visit"] for row in result["checks"]])
    assert not actual["starved_targets"]
    # A fixed-cost instantaneous-completion baseline, not an exact model of
    # resampled costs or polled admission. Keep that distinction in the data.
    model_cost = float(np.median(costs))
    modeled = simulate(visits, model_cost, "freshness_guard_one_pending")
    model = summarize(visits, [row.visit for row in modeled])
    sampled = sampled_simulate(geometry, rate, costs.tolist(), owner_jitter_ms=jitter)
    actual_dispatches = [(r["visit"], r["started_ms"]) for r in result["checks"]]
    expected_dispatches = [(r["visit"], r["started_ms"]) for r in sampled["checks"]]
    assert actual_dispatches == expected_dispatches, "SDK and sampled model diverged"
    for reason in ("expired", "freshness_skips", "replacements"):
        assert result["admission"][reason] == sampled["dropped"][reason]
    assert result["protection"]["backlog_skips"] == sum(sampled["dropped"].values())
    checks = result["checks"]
    bound = max(jitter) - min(jitter) + 20
    assert all(-1e-6 <= c["harvested_ms"] - c["completed_ms"] <= bound + 1e-6 for c in checks)
    return {
        "scope": "Actual SDK with synthetic IQ and controlled completion timing; no RF",
        "session_id": baseline["session_id"],
        "sample_rate_hz": rate,
        "snapshot_path": str(path.relative_to(ROOT)),
        "snapshot_sha256": digest(path),
        "input_manifest_sha256": baseline["input_manifest_sha256"],
        "profile": label,
        "cost_assignment": "constant"
        if label != "resampled_jitter"
        else "seeded resampling from measured checked-dwell wall times, not missing-dwell truth",
        "worker_cost_ms": costs.tolist(),
        "owner_delivery_jitter_ms": list(jitter),
        "model": {
            "scope": "Instantaneous-completion, fixed-cost counterfactual baseline",
            "worker_cost_ms": model_cost,
            **model,
        },
        "sampled_model": {
            "exact_dispatch_agreement": True,
            "dropped": sampled["dropped"],
            **summarize(visits, [r["visit"] for r in sampled["checks"]]),
        },
        "actual": {**actual, **result},
        "maximum_dispatch_age_after_valid_end_ms": max(
            c["started_ms"] - c["ready_ms"] for c in checks
        ),
        "maximum_completion_poll_lag_ms": max(
            c["harvested_ms"] - c["completed_ms"] for c in checks
        ),
        "host_test_elapsed_seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    args.output_root.mkdir()
    sdk, worker = build(args.output_root / "build")
    source_paths = [
        Path(__file__).resolve(),
        ROOT / "tests/scanner/fair_admission_harness.py",
        ROOT / "tools/scanner_sampled_admission_model.py",
        *(
            ROOT / "tests/scanner/native" / name
            for name in ("protection_clock.c", "fair_dispatch_trace.c", "fair_worker_gate.c")
        ),
    ]
    sources = {str(p.relative_to(ROOT)): digest(p) for p in source_paths}
    results = []
    for path in args.input:
        path = path.resolve()
        inputs = inventory(path)
        baseline, _, geometry, measured, _ = inputs
        for label, costs, jitter in profiles(measured, len(geometry)):
            case = args.output_root / (baseline["session_id"] + "-" + label)
            case.mkdir()
            result = evaluate_case(sdk, worker, case, path, label, costs, jitter, inputs)
            with (case / "result.json").open("x") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
                stream.write("\n")
            results.append(
                {
                    "path": str((case / "result.json").relative_to(args.output_root)),
                    "sha256": digest(case / "result.json"),
                    "session_id": baseline["session_id"],
                    "rate": inputs[1],
                    "profile": label,
                    "screening_percent": result["actual"]["screening_percent"],
                    "modeled_percent": result["model"]["screening_percent"],
                    "worst_source_gap_ms": max(
                        r["maximum_source_screen_gap_ms"] for r in result["actual"]["per_target"]
                    ),
                }
            )
            print(json.dumps(results[-1]), flush=True)
    assert sources == {name: digest(ROOT / name) for name in sources}
    receipt = {
        "scope": "Controlled virtual-time SDK admission; not ARM/live qualification",
        "leo_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "sources": sources,
        "sdk_sha256": digest(sdk),
        "worker_sha256": digest(worker),
        "cases": results,
        "completed": True,
    }
    with (args.output_root / "receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
