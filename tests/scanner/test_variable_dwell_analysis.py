import numpy as np
import pytest
from pydantic import ValidationError

import leo.scanner.adaptive_hop_analysis as analysis_module
from leo.cli.firmware_adaptive_import import _receipt
from leo.scanner.adaptive_hop_analysis import (
    FourRateVariableDwellAnalysisConfigurationV6,
    FourRateVariableDwellAnalysisSourceV7,
    FourRateVariableDwellVisitAnalysisV6,
    VariableDwellAnalysisConfigurationV5,
    VariableDwellAnalysisSourceV6,
    VariableDwellVisitAnalysisV5,
    analyze_adaptive_hop_visit,
)
from leo.scanner.adaptive_hop_products import FourRateVariableDwellAnalysisBindingV9
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from tests.cli.test_firmware_adaptive_import import variable_dual_document
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


class VariableReader:
    input_manifest_sha256 = "sha256:" + "1" * 64

    def __init__(self, dwell_ms: int):
        self.receipt = _receipt(variable_dual_document(2_500_000, dwell_ms), "sha256:" + "2" * 64)
        self.session_id = self.receipt.session_id

    def read_visit_ci16(self, index: int):
        visit = self.receipt.visits[index]
        return visit, np.zeros((visit.valid_sample_count, 2, 2), dtype="<i2")


@pytest.mark.parametrize(
    ("dwell_ms", "probe_count", "last_start_ms"),
    [(120, 22, 100), (240, 46, 220), (360, 70, 340)],
)
def test_probe_layout_follows_the_authoritative_event_span(
    monkeypatch, dwell_ms, probe_count, last_start_ms
):
    source = VariableDwellAnalysisSourceV6(VariableReader(dwell_ms))
    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", _fake_fractional_dwell)

    product = analyze_adaptive_hop_visit(source, 0)

    assert isinstance(product, VariableDwellVisitAnalysisV5)
    assert product.valid_end_counter - product.valid_start_counter == 2_500 * dwell_ms
    assert len(product.probes) == probe_count
    assert product.probes[-1].probe_start_ms == last_start_ms
    assert product.configuration.allowed_valid_visit_ms == (120, 240, 360)
    assert not hasattr(product.configuration, "dwell_samples")


def test_variable_dwell_configuration_rejects_an_invented_duration_inventory():
    with pytest.raises(ValidationError, match="exact attested durations"):
        VariableDwellAnalysisConfigurationV5(
            sample_rate_hz=2_500_000,
            allowed_valid_visit_ms=(120, 360),
        )


@pytest.mark.parametrize("rate", [5_000_000, 7_500_000])
def test_four_rate_receipt_gets_a_new_analysis_contract(rate: int) -> None:
    document = variable_dual_document(rate, 120)
    document["evidence"]["radio_serial"] = "1040005e0b100007100010000bf33a5d4d"
    receipt = _receipt(document, "sha256:" + "2" * 64)

    binding = bind_actual_visit_analysis(
        receipt,
        input_manifest_sha256="sha256:" + "1" * 64,
        probe_stride_ms=120,
    )

    assert isinstance(binding, FourRateVariableDwellAnalysisBindingV9)
    assert isinstance(binding.configuration, FourRateVariableDwellAnalysisConfigurationV6)
    assert binding.configuration.sample_rate_hz == rate
    assert binding.configuration.allowed_valid_visit_ms == (120, 240, 360)


def test_four_rate_visit_checkpoints_under_the_new_contract(monkeypatch, tmp_path) -> None:
    class Reader:
        input_manifest_sha256 = "sha256:" + "1" * 64

        def __init__(self):
            document = variable_dual_document(7_500_000, 120)
            document["evidence"]["radio_serial"] = "1040005e0b100007100010000bf33a5d4d"
            self.receipt = _receipt(document, "sha256:" + "2" * 64)
            self.session_id = self.receipt.session_id

        def read_visit_ci16(self, index: int):
            visit = self.receipt.visits[index]
            return visit, np.zeros((visit.valid_sample_count, 2, 2), dtype="<i2")

    source = FourRateVariableDwellAnalysisSourceV7(Reader())
    binding = bind_actual_visit_analysis(
        source.receipt,
        input_manifest_sha256=source.input_manifest_sha256,
        probe_stride_ms=120,
    )
    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", _fake_fractional_dwell)
    product = analyze_adaptive_hop_visit(
        source,
        0,
        configuration=binding.configuration,
    )

    assert isinstance(product, FourRateVariableDwellVisitAnalysisV6)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        reference = job.write_visit(product)
        manifest = job.finalize_metrics()
        assert reference.schema_version == 9
        assert manifest.schema_version == 9
        assert job.status().schema_version == 9
    store.close()
