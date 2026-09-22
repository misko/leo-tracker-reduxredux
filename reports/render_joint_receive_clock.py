"""Seal completed clock-fit inputs before evaluation-only position comparison."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def error_km(latitude, longitude, reference):
    a, b = np.deg2rad([latitude, reference["latitude_deg"]])
    dl = np.deg2rad(longitude - reference["longitude_deg"])
    haversine = np.sin((a-b)/2)**2 + np.cos(a)*np.cos(b)*np.sin(dl/2)**2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1))))


def seal_inputs(results, nominal, clock_audit, output):
    baseline = json.loads(nominal.read_text())
    if baseline.get("position_truth_used") is not False:
        raise ValueError("blind nominal fit required")
    documents = []
    bindings = {str(nominal): digest(nominal), str(clock_audit): digest(clock_audit)}
    for path in results:
        expected = path.with_name("result.sha256").read_text().strip()
        if digest(path).removeprefix("sha256:") != expected:
            raise ValueError("clock result checksum mismatch")
        document = json.loads(path.read_text())
        if (document.get("truth_accessed") is not False
                or document.get("known_position_used") is not False
                or not document.get("complete")):
            raise ValueError("completed truth-free result required")
        if document["refinement_digest"] != digest(nominal):
            raise ValueError("nominal fit binding mismatch")
        if document["clock_audit_digest"] != digest(clock_audit):
            raise ValueError("clock audit binding mismatch")
        bindings[str(path)] = digest(path)
        documents.append(document)
    output.mkdir(parents=True, exist_ok=False)
    (output / "inference-seal.json").write_text(json.dumps(bindings, indent=2) + "\n")
    return baseline, documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    for name in ("nominal", "clock-audit", "reference", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    baseline, documents = seal_inputs(args.results, args.nominal, args.clock_audit, args.output)
    reference = json.loads(args.reference.read_text())
    audit = json.loads(args.clock_audit.read_text())
    bounds = {
        s["session_id"]: s["allowed_clock_s_relative_to_reference"] for s in audit["sessions"]
    }
    baseline_error = error_km(baseline["latitude_deg"], baseline["longitude_deg"], reference)
    rows = []
    for index, document in enumerate(documents):
        fitted = document["fitted"]
        rows.append({
            "run": args.results[index].parent.name,
            "qualification": document["qualification"],
            "optimizer": document["optimizer"],
            "error_km": error_km(fitted["latitude_deg"], fitted["longitude_deg"], reference),
            "training_delta": fitted["training_score"] - document["nominal"]["training_score"],
            "heldout_delta": fitted["heldout_score"] - document["nominal"]["heldout_score"],
            "clock_s": fitted["clock_s"],
            "distance_to_nearest_clock_bound_s": {
                s: min(v-bounds[s][0], bounds[s][1]-v) for s, v in fitted["clock_s"].items()
            },
        })
        (args.output / f"run-{index+1}.json").write_bytes(args.results[index].read_bytes())
    summary = {"evaluation_only": True, "reference": reference,
               "nominal_error_km": baseline_error, "results": rows}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    latest = rows[-1]
    for i, (session, clock) in enumerate(latest["clock_s"].items()):
        axes[0].plot(bounds[session], [i, i], color="gray", lw=3)
        axes[0].plot(clock, i, "o", color="tab:blue")
    axes[0].axvline(0, color="black", ls=":", lw=1)
    axes[0].set_yticks(range(len(latest["clock_s"])),
                      [s.removeprefix("scan-fw-")[:8] for s in latest["clock_s"]])
    axes[0].set_xlabel("Receive-time offset (s); gray = recorded hard bounds")
    axes[0].set_title(f"Latest run: {latest['qualification']}")
    x = np.arange(len(rows))
    axes[1].bar(x, [r["error_km"] for r in rows], color="tab:blue")
    axes[1].axhline(baseline_error, color="tab:orange", label="Zero-clock baseline")
    axes[1].set_xticks(x, [f"Run {i+1}\n{r['qualification']}" for i, r in enumerate(rows)])
    axes[1].set_ylabel("Evaluation-only horizontal error (km)")
    axes[1].legend()
    fig.suptitle("One-basin Sacramento five-scan clock ablation · no global or precision claim")
    fig.tight_layout()
    fig.savefig(args.output / "clock-comparison.png", dpi=140)


if __name__ == "__main__":
    main()
