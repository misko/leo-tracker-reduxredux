"""Exact owned-run comparison for numerical optimizations under matched requests.

This does not establish equivalence to historical production work admission or
qualify dataset-wide performance. It verifies scientific and published values
between two freshly completed owned CLI runs.
"""

import argparse
import hashlib
import json
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot
from check_algo07v3_scan_likelihood import fingerprint

from leo.contracts.digests import canonical_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store


def same(a, b, label):
    if a != b:
        raise ValueError(label + " differs")


def matched_requests(a, b):
    same(
        {k: v for k, v in a.items() if k != "output_root"},
        {k: v for k, v in b.items() if k != "output_root"},
        "Inference/presentation request",
    )
    if a["output_root"] == b["output_root"]:
        raise ValueError("Independent fresh output stores required")


def scientific_values(a, b):
    same(set(a), set(b), "Evidence fields")
    # These fields receive separate comparisons below. All others, including
    # preparation, catalogue, selected states, render settings and identity, are exact.
    separately = {"audit", "presentation", "provenance", "stage_timings"}
    same(
        fingerprint({k: v for k, v in a.items() if k not in separately}),
        fingerprint({k: v for k, v in b.items() if k not in separately}),
        "Scientific evidence",
    )
    stages = []
    for value in (a, b):
        if any(set(r) != {"stage", "seconds"} for r in value["stage_timings"]):
            raise ValueError("Unknown stage accounting fields")
        stages.append([r["stage"] for r in value["stage_timings"]])
    same(*stages, "Ordered stages")


def module_changes(a, b, expected_changed, expected_added):
    same(set(a) - set(b), set(), "Removed implementation modules")
    added = set(b) - set(a)
    same(added, set(expected_added), "Declared added modules")
    changed = {k for k in set(a) & set(b) if a[k] != b[k]}
    same(changed, set(expected_changed), "Declared source changes")
    return changed, added


def compare(args):
    requests = [json.loads(p.read_bytes()) for p in (args.baseline_request, args.candidate_request)]
    matched_requests(*requests)
    run_id = requests[0]["identity"]["run_id"]
    saved = [LocalizationV3Store(r["output_root"]).load(run_id) for r in requests]
    a, b = [r["evidence"] for r in saved]
    scientific_values(a, b)
    same(
        evidence_snapshot(a, saved[0]["pngs"]),
        evidence_snapshot(b, saved[1]["pngs"]),
        "Complete numerical audit and presentation snapshot",
    )
    same(saved[0]["pngs"], saved[1]["pngs"], "PNG bytes")
    for request, value in zip(requests, (a, b), strict=True):
        provenance = value["provenance"]
        same(
            set(provenance),
            {
                "request_sha256",
                "configuration",
                "configuration_sha256",
                "runtime",
                "implementation_sha256",
                "modules",
            },
            "Provenance fields",
        )
        same(provenance["request_sha256"], canonical_digest(request), "Request binding")
        same(provenance["configuration"]["request"], request, "Configuration request")
        same(
            provenance["configuration_sha256"],
            canonical_digest(provenance["configuration"]),
            "Configuration digest",
        )
        same(provenance["runtime"], request["runtime"], "Numerical environment")
        same(
            provenance["implementation_sha256"],
            canonical_digest({k: v["sha256"] for k, v in provenance["modules"].items()}),
            "Implementation binding",
        )
    configs = [
        {k: v for k, v in x["provenance"]["configuration"].items() if k != "request"}
        for x in (a, b)
    ]
    same(*configs, "Numerical configuration")
    modules = [x["provenance"]["modules"] for x in (a, b)]
    changes, added = module_changes(
        *modules,
        args.changed_module or ["leo.analysis.localization_v3.hierarchical"],
        args.added_module,
    )
    public = [FastStandardAnalysisStore(r["output_root"]) for r in requests]
    documents = []
    for store, result in zip(public, saved, strict=True):
        doc = store.detail(run_id)
        same(doc["state"], "complete", "Public state")
        same(doc["terminal_sha256"], result["sha256"], "Public scientific binding")
        same({r["name"] for r in doc["artifacts"]}, set(result["pngs"]), "Artifact inventory")
        for name, image in result["pngs"].items():
            same(store.artifact(run_id, name), image, "Published " + name)
        documents.append({k: v for k, v in doc.items() if k != "terminal_sha256"})
    same(*documents, "Published result")
    for method in ("position_grid", "position_path"):
        values = []
        for store, result in zip(public, saved, strict=True):
            value = getattr(store, method)(run_id)
            same(value["binding"]["terminal_sha256"], result["sha256"], method + " binding")
            values.append(
                {k: v for k, v in value.items() if k not in {"binding", "elapsed_seconds"}}
            )
        same(*values, method)
    clocks = [json.loads(p.read_bytes()) for p in (args.baseline_timing, args.candidate_timing)]
    for request, clock in zip(requests, clocks, strict=True):
        if (
            clock["status"] != "exited"
            or clock["returncode"] != 0
            or clock["worker"]["status"] != "complete"
            or clock["worker"]["resumed"]
        ):
            raise ValueError("Fresh completed executions required")
        same(clock["request_sha256"], canonical_digest(request), "Timing request binding")
    return dict(
        exact_owned_science_and_artifacts=True,
        source_changes=sorted(changes),
        added_modules=sorted(added),
        observed_process_seconds={
            s: r["process_seconds"] for s, r in zip(("baseline", "optimized"), clocks, strict=True)
        },
        observed_latency_ratio=clocks[0]["process_seconds"] / clocks[1]["process_seconds"],
        both_c_arms=True,
        full_historical_equivalence=False,
        dataset_wide_qualification=False,
        qualified_speedup=None,
        input_bindings={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                args.baseline_request,
                args.candidate_request,
                args.baseline_timing,
                args.candidate_timing,
                Path(__file__),
            )
        },
        scientific_receipts=[r["sha256"] for r in saved],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "baseline-request",
        "candidate-request",
        "baseline-timing",
        "candidate-timing",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--changed-module", action="append", default=None)
    parser.add_argument("--added-module", action="append", default=[])
    args = parser.parse_args()
    result = compare(args)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
