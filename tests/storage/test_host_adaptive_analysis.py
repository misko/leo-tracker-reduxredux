import io

import pytest
from PIL import Image
from pydantic import ValidationError

import leo.scanner.adaptive_hop_analysis as detector
from leo.presentation.adaptive_hop_analysis import (
    project_host_adaptive_overview,
    render_host_adaptive_hop_overview,
)
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
)
from leo.scanner.host_adaptive_analysis import (
    HostAdaptiveAnalysisSource,
    analyze_host_adaptive_visit,
)
from leo.scanner.host_adaptive_presentation import HostAdaptiveOverviewManifestV2
from leo.scanner.host_adaptive_products import (
    HostAdaptiveAnalysisBindingV2,
    bind_actual_visit_analysis,
)
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.errors import BundleCorruptionError
from tests.scanner.test_host_adaptive_analysis import Reader
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


def fixture(monkeypatch, receiver=0):
    reader = Reader(receiver=receiver, count=3)
    source = HostAdaptiveAnalysisSource(reader)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    binding = bind_actual_visit_analysis(
        reader.receipt, input_manifest_sha256=reader.input_manifest_sha256
    )
    products = tuple(analyze_host_adaptive_visit(source, i) for i in range(2))
    return binding, products


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_metrics_and_all_pngs_are_bound_to_the_selected_rx(tmp_path, monkeypatch, receiver):
    binding, products = fixture(monkeypatch, receiver)
    store = AdaptiveHopAnalysisStore(tmp_path)
    try:
        with store.job(binding, writable=True) as job:
            for product in products:
                reference = job.write_visit(product)
                assert reference.schema_version == 2 and reference.probe_count == 11
            metrics = job.finalize_metrics()
            with pytest.raises(ValidationError):
                AdaptiveHopMetricsManifestV1.model_validate_json(metrics.model_dump_json())
            projection = project_host_adaptive_overview(binding, metrics, job.published_visits())
            assert set(projection.winners[:, 1]) == {receiver}
            assert all(rx == receiver for _, rx in projection.observations)
            rendered = render_host_adaptive_hop_overview(
                binding,
                metrics,
                job.published_visits(),
                test_data="synthetic",
            )
            overview = job.publish_overview(rendered)
            assert isinstance(overview, HostAdaptiveOverviewManifestV2)
            assert job.status().state == "figures_ready"
            assert job.publish_overview(rendered) == overview
            for artifact in overview.artifacts:
                payload = job.read_artifact(artifact.name, expected_sha256=artifact.sha256)
                with Image.open(io.BytesIO(payload)) as image:
                    image.load()
                    assert image.width > 1000 and image.height > 500
                    assert image.info["PhysicalReceiver"] == str(receiver)
                    assert image.info["CaptureRateHz"] == "10000000"
                    assert image.info["DecisionRateHz"] == "2500000"
                    assert image.info["DecisionExecution"] == "host"
                    assert image.info["Binding"] == binding.sha256
                    assert (
                        image.info["DecisionConfiguration"]
                        == binding.receipt.plan.decision.configuration_sha256
                    )
                    assert image.info["TestData"].startswith("SYNTHETIC TEST DATA")
    finally:
        store.close()


def test_native_checkpoint_refuses_a_different_major_or_rewrite(tmp_path, monkeypatch):
    binding, products = fixture(monkeypatch)
    with pytest.raises(ValidationError):
        AdaptiveHopAnalysisBindingV1.model_validate_json(binding.model_dump_json())
    store = AdaptiveHopAnalysisStore(tmp_path)
    try:
        with store.job(binding, writable=True) as job:
            reference = job.write_visit(products[0])
            assert job.write_visit(products[0]) == reference
            with pytest.raises(ValidationError):
                job.write_visit(products[0].model_copy(update={"schema_version": 1}))
        directory = tmp_path / "scanner-adaptive-analysis" / binding.session_id / binding.sha256[7:]
        (directory / reference.relative_path).rename(
            directory / reference.relative_path.replace(".v2.", ".v1.")
        )
        with store.job(binding) as job, pytest.raises(BundleCorruptionError, match="schema major"):
            job.completed_visits()
    finally:
        store.close()


def test_native_binding_refuses_a_relabelled_receiver(monkeypatch):
    binding, _ = fixture(monkeypatch)
    payload = binding.model_dump()
    payload["configuration"]["receiver_ids"] = (1,)
    with pytest.raises(ValidationError, match="receiver"):
        HostAdaptiveAnalysisBindingV2.model_validate(payload)
