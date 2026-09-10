"""Paired real-SDK pending-age replays on saved schedules; no RF or ARM execution."""

import argparse
import json
import subprocess
from pathlib import Path

from tests.scanner.fair_admission_harness import ORIGIN, Geometry, build
from tools.evaluate_scanner_fair_sdk import digest, evaluate_case, inventory, profiles
from tools.native_presence import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--stress-shape", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_root
    out.mkdir()
    sdk, worker = build(out / "build")
    sources = [
        Path(__file__).resolve(),
        ROOT / "tools/evaluate_scanner_fair_sdk.py",
        ROOT / "tools/scanner_sampled_admission_model.py",
        ROOT / "tests/scanner/fair_admission_harness.py",
        *sorted((ROOT / "src/leo/scanner/native_presence").glob("*.[ch]")),
    ]
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in sources}
    cases = [(p.resolve(), inventory(p), None) for p in args.input]
    shape = args.stress_shape.resolve()
    base, rate, geometry, _, visits = inventory(shape)
    assert rate == 2500000, "stress shape must be the 2.5 MS/s uneven schedule"
    scaled = [
        Geometry(ORIGIN + 2 * (g.start - ORIGIN), ORIGIN + 2 * (g.end - ORIGIN), g.target)
        for g in geometry
    ]
    for path, inputs, _ in list(cases):
        if inputs[1] == 5000000:
            cases.append((shape, (base, 5000000, scaled, inputs[3], visits), path))
    summary = []
    for path, inputs, cost_source in cases:
        for age in (120, 240):
            for label, costs, jitter in profiles(inputs[3], len(inputs[2])):
                name = path.name.removesuffix(".json.gz")
                if cost_source:
                    name += "-rescaled-cost-" + cost_source.name.removesuffix(".json.gz")
                case = out / f"{name}-{label}-pending{age}"
                case.mkdir()
                result = evaluate_case(
                    sdk,
                    worker,
                    case,
                    path,
                    label,
                    costs,
                    jitter,
                    inputs,
                    maximum_pending_age_ms=age,
                )
                if cost_source:
                    result["scope"] = (
                        "Counterfactual 5 MS/s rate-rescaled uneven schedule; synthetic IQ"
                    )
                    result["cost_source_path"] = str(cost_source.relative_to(ROOT))
                    result["cost_source_sha256"] = digest(cost_source)
                    result["timing_source_sample_rate_hz"] = 2500000
                output = case / "result.json"
                with output.open("x") as stream:
                    json.dump(result, stream, indent=2, allow_nan=False)
                    stream.write("\n")
                summary.append(
                    {
                        "path": str(output.relative_to(out)),
                        "sha256": digest(output),
                        "rate": inputs[1],
                        "profile": label,
                        "maximum_pending_age_ms": age,
                        "shape": "rescaled-uneven" if cost_source else "original",
                        "timing_session": inputs[0]["session_id"],
                        "cost_session": cost_source.name.removesuffix(".json.gz")
                        if cost_source
                        else inputs[0]["session_id"],
                        "screening_percent": result["actual"]["screening_percent"],
                        "worst_source_gap_ms": max(
                            r["maximum_source_screen_gap_ms"]
                            for r in result["actual"]["per_target"]
                        ),
                        "maximum_dispatch_age_ms": result[
                            "maximum_dispatch_age_after_valid_end_ms"
                        ],
                    }
                )
                print(json.dumps(summary[-1]), flush=True)
    assert source_hashes == {name: digest(ROOT / name) for name in source_hashes}
    with (out / "receipt.json").open("x") as stream:
        json.dump(
            {
                "scope": "Paired actual SDK admission with synthetic IQ "
                "and controlled timing; no RF",
                "leo_revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "sources": source_hashes,
                "sdk_sha256": digest(sdk),
                "worker_sha256": digest(worker),
                "cases": summary,
                "completed": True,
            },
            stream,
            indent=2,
            allow_nan=False,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
