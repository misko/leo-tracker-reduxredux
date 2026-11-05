"""Bind the paired observations and render their explicitly incomplete gate."""

import argparse
import hashlib
import json
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot

from leo.storage.localization_v3 import LocalizationV3Store


def run(root, tests):
    out = Path(__file__).resolve().parent
    request = json.loads((root / "v3-request.json").read_bytes())
    candidate = json.loads((root / "v3-run/attempt/supervisor.json").read_bytes())
    reference = json.loads((root / "attempt002/reference-timing/summary.json").read_bytes())
    comparison = json.loads((root / "comparison.json").read_bytes())
    assert candidate["status"] == "exited" and candidate["returncode"] == 0
    assert reference["state"] == "completed_unqualified"
    assert (
        comparison["all_checked_values_exact"] and not comparison["full_intermediate_equivalence"]
    )
    saved = LocalizationV3Store(request["output_root"]).load(request["identity"]["run_id"])
    previous = Path("/srv/bulk/leo-dev/algo07v3-publication-20261105/result.json").read_bytes()
    assert (
        hashlib.sha256(previous).hexdigest()
        == "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    )
    expected = json.loads(previous)
    observed = evidence_snapshot(saved["evidence"], saved["pngs"])
    # This run intentionally uses the actual title and confirmed evaluation site.
    # Compare fresh presentation to the fresh baseline, and prior science to prior science.
    assert {k: v for k, v in observed.items() if k != "presentation"} == {
        k: v for k, v in expected.items() if k != "presentation"
    }
    for name, binding in saved["evidence"]["provenance"]["modules"].items():
        source = root / "source" / (name + ".py")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == binding["sha256"]
    suites = list(ET.parse(tests).getroot().iter("testsuite"))
    assert suites and all(
        int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped")
    )
    baseline = reference["completed_path_seconds"]
    native = candidate["process_seconds"]
    stages = json.loads(Path(reference["final_inference_receipt"]).read_bytes())["stages"]
    probe = json.loads((root / "assembly-probe.json").read_bytes())
    _, old_code, new_code = runpy.run_path(str(out / "probe_assembly.py"))["candidate_function"]()
    assert hashlib.sha256(old_code.encode()).hexdigest() == probe["reference_sha256"]
    assert hashlib.sha256(new_code.encode()).hexdigest() == probe["candidate_sha256"]
    assert probe["exact"] and not probe["enabled_in_runtime"]
    summary = dict(
        scan="DS26-0002",
        reference_seconds=baseline,
        native_v3_seconds=native,
        observed_latency_ratio=baseline / native,
        observed_time_reduction_percent=100 * (1 - native / baseline),
        qualified_speedup=None,
        full_intermediate_equivalence=False,
        public_artifacts_exact=True,
        mapped_scientific_sections=len(comparison["mapped_policies"]),
        unmapped_scientific_sections=comparison["missing_audit_mappings"],
        full_native_science_matches_prior_qualification=True,
        test_count=sum(int(s.attrib["tests"]) for s in suites),
        tests_sha256=hashlib.sha256(tests.read_bytes()).hexdigest(),
        reference_stages=[
            dict(algorithm=r["algorithm"], seconds=r["wall_seconds"]) for r in stages
        ],
        reference_inference_seconds=reference["inference"]["wall_seconds"],
        reference_publication_seconds=reference["publication"]["wall_seconds"],
        native_timings={k: v for k, v in candidate["worker"].items() if k.endswith("seconds")},
        baseline_load_start=reference["load_average_start"],
        baseline_load_end=reference["load_average_end"],
        candidate_load_observation=json.loads(
            (root / "candidate-load-observation.json").read_bytes()
        ),
        production_modified=False,
        assembly_probe_mean_sums={
            side: sum(sum(row["seconds"][side]) / 2 for row in probe["rows"])
            for side in ("reference", "scatter")
        },
    )
    for name, source in {
        "comparison.json": root / "comparison.json",
        "baseline-timing.json": root / "attempt002/reference-timing/summary.json",
        "candidate-timing.json": root / "v3-run/attempt/supervisor.json",
        "protocol.json": root / "protocol-002.json",
        "first-attempt.json": root / "reference-timing/summary.json",
        "historical-bindings.json": root / "reference-source.json",
        "assembly-probe.json": root / "assembly-probe.json",
    }.items():
        (out / name).write_bytes(source.read_bytes())
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.subplots_adjust(left=0.20, right=0.98, top=0.84, bottom=0.25)
    ax.barh(
        ["Frozen ALGO07 chain", "Standalone ALGO07v3"],
        [baseline, native],
        color=["#777777", "#3465a4"],
    )
    for i, value in enumerate([baseline, native]):
        ax.text(value, i, f"  {value:.2f} s ({value / 60:.2f} min)", va="center")
    ax.set(xlabel="Native GLRT ready → all standard artifacts (seconds)", xlim=(0, baseline * 1.36))
    ax.invert_yaxis()
    ax.set_title(
        "DS26-0002 · fresh sequential observations\n"
        "Both arms, eight PNGs and all 179 grid points agree"
    )
    fig.text(
        0.5,
        0.025,
        "Shared host; load changed. Nine audit mappings remain open.\n"
        "Observed latency reduction is not a qualified full-equivalence speedup.",
        ha="center",
        fontsize=10,
    )
    fig.savefig(out / "paired-runtime.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.tests)
