"""Verify the CLI experiment independently of its runtime process.

Run with PYTHONPATH=src:tools from the repository root. No oracle is supplied to
the native worker. This comparison runs only after run and resume have exited.
"""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from check_algo07v3_publication import evidence_snapshot

from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store

REFERENCE_SHA = "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"


def verify(root, tests):
    request = json.loads((root / "request.json").read_bytes())
    assert request["runtime"] == runtime_versions()
    attempt = json.loads((root / "run/attempt/supervisor.json").read_bytes())
    resume = json.loads((root / "resume/attempt/supervisor.json").read_bytes())
    for report in (attempt, resume):
        assert report["status"] == "exited" and report["returncode"] == 0
        assert report["request_sha256"] == canonical_digest(request)
        assert report["worker"]["status"] == "complete"
    assert attempt["worker"]["resumed"] is False
    assert resume["worker"]["resumed"] is True
    assert attempt["worker"]["publication"] == resume["worker"]["publication"]
    scientific = LocalizationV3Store(request["output_root"])
    run_id = request["identity"]["run_id"]
    saved = scientific.load(run_id)
    evidence, pngs = saved["evidence"], saved["pngs"]
    assert evidence["identity"] == request["identity"]
    assert evidence["provenance"]["request_sha256"] == canonical_digest(request)
    assert evidence["provenance"]["configuration"]["request"] == request
    source_files = evidence["provenance"]["modules"]
    for name, row in source_files.items():
        # Preserve historical evidence when later optimization changes the checkout.
        source = root / "source" / (name + ".py")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"]
    comparison = evidence_snapshot(evidence, pngs)
    raw = (json.dumps(comparison, sort_keys=True, allow_nan=False) + "\n").encode()
    assert hashlib.sha256(raw).hexdigest() == REFERENCE_SHA
    publication = FastStandardAnalysisStore(request["output_root"])
    manifest = publication.detail(run_id)
    assert manifest["state"] == "complete"
    for name, data in pngs.items():
        assert publication.artifact(run_id, name) == data
    for sidecar in (publication.position_grid(run_id), publication.position_path(run_id)):
        assert sidecar["binding"]["terminal_sha256"] == saved["sha256"]
    for action in ("run", "resume"):
        assert all(json.loads((root / action / "isolation.json").read_bytes())["checks"].values())
    live = json.loads((root / "live-isolation.json").read_bytes())
    assert len(live) == 1 and all(live[0]["checks"].values())
    suites = list(ET.parse(tests).getroot().iter("testsuite"))
    assert suites and all(
        int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped")
    )
    worker = attempt["worker"]
    return dict(
        scan="DS26-0002",
        request_sha256=canonical_digest(request),
        comparison_sha256=REFERENCE_SHA,
        scientific_receipt_sha256=saved["sha256"],
        exact_scientific_and_png_comparison=True,
        png_count=len(pngs),
        grid_points=comparison["presentation"]["grid_points"],
        grid_complete=comparison["presentation"]["grid_complete"],
        owned_source_files_verified=len(source_files),
        test_count=sum(int(s.attrib["tests"]) for s in suites),
        tests_sha256=hashlib.sha256(tests.read_bytes()).hexdigest(),
        timings=dict(
            native_to_render_seconds=worker["native_to_render_seconds"],
            evidence_save_seconds=worker["evidence_save_seconds"],
            publication_seconds=worker["publication_seconds"],
            native_to_publication_seconds=worker["seconds"],
            supervised_process_seconds=attempt["process_seconds"],
            resume_worker_seconds=resume["worker"]["seconds"],
            resume_process_seconds=resume["process_seconds"],
        ),
        full_dataset_equivalence=False,
        production_admission_equivalence=False,
        complete_path_matched_scans=0,
        complete_path_speedup=None,
        deployed=False,
    )


def chart(result, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    timings = result["timings"]
    keys = ("native_to_render_seconds", "evidence_save_seconds", "publication_seconds")
    labels = ("Native GLRT → figures", "Evidence projection/save", "UI publication")
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
    left = 0
    for key, label, color in zip(keys, labels, ("#385e9d", "#df9c39", "#4c9675"), strict=True):
        value = timings[key]
        axes[0].barh([0], [value], left=left, label=f"{label}: {value:.2f} s", color=color)
        left += value
    axes[0].set(xlabel="Seconds", yticks=[], title=f"Fresh native → publication: {left:.2f} s")
    axes[0].legend(loc="upper left", bbox_to_anchor=(0, -0.3), ncol=2)
    values = [timings["resume_worker_seconds"], timings["resume_process_seconds"]]
    axes[1].barh(["Saved-result publication", "Including process startup"], values, color="#4c9675")
    for i, value in enumerate(values):
        axes[1].text(value, i, f" {value:.2f} s", va="center")
    axes[1].set(
        xlabel="Seconds (separate scale)",
        xlim=(0, max(values) * 1.25),
        title="Resume with native input/configuration/TLE bundle inaccessible",
    )
    fig.suptitle(
        "ALGO07v3 · DS26-0002 · exact science and eight PNGs\n"
        "One shared-host observation; no matched baseline or speedup claim"
    )
    fig.savefig(output, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root, args.tests)
    output = Path(__file__).resolve().parent
    (output / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    chart(result, output / "runtime.png")
    print(json.dumps(result, indent=2))
