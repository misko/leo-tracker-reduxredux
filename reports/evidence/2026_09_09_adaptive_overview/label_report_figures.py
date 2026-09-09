"""Regenerate report figures with explicit test provenance; do not edit PNG pixels."""

import json
from pathlib import Path

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.presentation.adaptive_hop_analysis import render_adaptive_hop_overview
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from tests.presentation.adaptive_overview_fixtures import full_overview_fixture

ROOT = Path(__file__).resolve().parents[3]
RAW = Path("/tmp/leo-adaptive-overview.HLsKuK")
FIGURES = ROOT / "reports/figures/2026_09_09_adaptive_overview"


def render(root, binding, prefix, context):
    store = AdaptiveHopAnalysisStore(root, read_only=True)
    try:
        with store.job(binding) as job:
            metrics = job.manifest()
            assert metrics is not None
            result = render_adaptive_hop_overview(
                binding, metrics, job.published_visits(), test_data=context
            )
            original = job.overview()
            assert original is not None
            assert result.association_count == original.association_count
            assert result.selected_observation_count == original.selected_observation_count
            assert (
                result.trajectory_configuration_sha256 == original.trajectory_configuration_sha256
            )
    finally:
        store.close()
    images = []
    for name, payload in result.artifacts.items():
        path = FIGURES / f"labeled-{prefix}-{name}.png"
        with path.open("xb") as stream:
            stream.write(payload)
        images.append({"path": str(path.relative_to(ROOT)), "sha256": sha256_digest(payload)})
    return {
        "context": context,
        "binding_sha256": binding.sha256,
        "metrics_manifest_sha256": original.metrics_manifest_sha256,
        "selected_observation_count": result.selected_observation_count,
        "association_count": result.association_count,
        "images": images,
    }


def main():
    summary = json.loads((RAW / "saved-overviews-corrected/summary.json").read_text())
    rows = []
    for case in summary["rows"]:
        root = Path(case["root"])
        captures = AdaptiveHopIqStore(root, read_only=True)
        try:
            capture = captures.inspect(case["session_id"])
            binding = AdaptiveHopAnalysisBindingV1(
                receipt=capture.manifest.receipt,
                input_manifest_sha256=capture.manifest_sha256,
                configuration=AdaptiveHopAnalysisConfigurationV1(
                    sample_rate_hz=capture.manifest.receipt.plan.geometry.sample_rate_hz
                ),
            )
        finally:
            captures.close()
        rows.append(render(root, binding, case["case"], "saved-rx1"))
    binding, _, _ = full_overview_fixture(rate=5_000_000, mode="shadow", candidate_count=16)
    rows.append(
        render(
            RAW / "full-overview-corrected/synthetic-store", binding, "synthetic-full", "synthetic"
        )
    )
    result = {
        "base_commit": "47f092f2",
        "report_only": True,
        "unchanged_metrics_and_association_results": True,
        "rows": rows,
        "sources": {
            p: sha256_digest((ROOT / p).read_bytes())
            for p in (
                "src/leo/presentation/adaptive_hop_analysis.py",
                "tests/presentation/test_adaptive_hop_overview.py",
                "reports/evidence/2026_09_09_adaptive_overview/label_report_figures.py",
            )
        },
    }
    with (Path(__file__).parent / "annotation-index.json").open("xb") as stream:
        stream.write(canonical_json_bytes(result))
    print(json.dumps({"contexts": len(rows), "labeled_pngs": sum(len(r["images"]) for r in rows)}))


if __name__ == "__main__":
    main()
