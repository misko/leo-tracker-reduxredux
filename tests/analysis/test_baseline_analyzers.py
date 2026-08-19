from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest
from pydantic import JsonValue

from leo.analysis.power import PowerAnalyzer, PowerReportV1
from leo.analysis.quality import QualityAnalyzer, QualityReportV1
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock
from leo.pipeline import (
    AnalysisContext,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    StageOutcome,
)


class _ArrayIqReader:
    def __init__(
        self,
        samples: np.ndarray,
        *,
        sample_count: int | None = None,
        sample_rate_hz: int = 2_500_000,
    ) -> None:
        self._samples = np.ascontiguousarray(samples, dtype="<i2")
        self._sample_count = len(samples) if sample_count is None else sample_count
        self._sample_rate_hz = sample_rate_hz
        self.requested_block_sizes: list[int] = []
        self.maximum_yielded_block = 0

    @property
    def sample_rate_hz(self) -> int:
        return self._sample_rate_hz

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return tuple(range(self._samples.shape[1]))

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        self.requested_block_sizes.append(block_samples)
        for start in range(0, len(self._samples), block_samples):
            values = self._samples[start : start + block_samples]
            self.maximum_yielded_block = max(self.maximum_yielded_block, len(values))
            interval = NanosecondIntervalV1(lower_ns=start, upper_ns=start)
            yield IqBlock(
                samples=values,
                metadata=IqBlockMetadataV1(
                    radio_id="fixture-radio",
                    receiver_ids=self.receiver_ids,
                    sample_count=len(values),
                    session_sample_start=start,
                    host_request_utc_ns=interval,
                    host_request_monotonic_ns=interval,
                ),
            )


class _NoProducts:
    def read_json(self, _requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        return None


class _MemorySink:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, JsonValue]] = {}

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        payload = canonical_json_bytes(document)
        self.documents[product.kind] = document
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}.json",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


def _context(**config: JsonValue) -> AnalysisContext:
    return AnalysisContext(
        session_id="session-1",
        run_id="run-1",
        pipeline_release="test-release",
        stage_config=config,
    )


def test_quality_detects_clipping_and_constant_iq() -> None:
    samples = np.array(
        [
            [[12, -4], [32_767, 0]],
            [[12, -4], [0, -32_768]],
            [[12, -4], [1, 2]],
            [[12, -4], [3, 4]],
        ],
        dtype="<i2",
    )
    reader = _ArrayIqReader(samples)
    sink = _MemorySink()

    result = QualityAnalyzer().analyze(_context(block_samples=2), reader, _NoProducts(), sink)
    report = QualityReportV1.model_validate(sink.documents["quality.summary"])

    assert result.outcome is StageOutcome.COMPLETE
    assert report.coverage_fraction == 1.0
    assert report.receivers[0].constant_iq is True
    assert report.receivers[0].clipped_complex_sample_count == 0
    assert report.receivers[1].constant_iq is False
    assert report.receivers[1].clipped_component_count == 2
    assert report.receivers[1].clipped_complex_sample_count == 2


def test_quality_streams_bounded_blocks_and_reports_partial_coverage() -> None:
    samples = np.arange(20, dtype="<i2").reshape(5, 2, 2)
    reader = _ArrayIqReader(samples, sample_count=8)

    result = QualityAnalyzer().analyze(
        _context(block_samples=2),
        reader,
        _NoProducts(),
        _MemorySink(),
    )

    assert result.outcome is StageOutcome.PARTIAL_COVERAGE
    assert result.summary["coverage_fraction"] == pytest.approx(5 / 8)
    assert reader.requested_block_sizes == [2]
    assert reader.maximum_yielded_block <= 2


def test_power_has_explicit_full_scale_units_and_coverage() -> None:
    samples = np.zeros((4, 2, 2), dtype="<i2")
    samples[:, 0, 0] = 32_767
    reader = _ArrayIqReader(samples)
    sink = _MemorySink()

    result = PowerAnalyzer().analyze(_context(block_samples=3), reader, _NoProducts(), sink)
    report = PowerReportV1.model_validate(sink.documents["power.summary"])

    assert result.outcome is StageOutcome.COMPLETE
    assert report.normalization == "E[I^2+Q^2]/32768^2"
    assert report.logarithmic_unit == "dBFS"
    assert report.coverage_fraction == 1.0
    assert report.receivers[0].mean_power_full_scale_squared == pytest.approx(
        (32_767 / 32_768) ** 2
    )
    assert report.receivers[0].mean_power_dbfs == pytest.approx(-0.00026507636)
    assert report.receivers[1].mean_power_full_scale_squared == 0.0
    assert report.receivers[1].mean_power_dbfs is None
    assert reader.maximum_yielded_block <= 3
    assert set(sink.documents["power.summary"]) == {
        "schema_version",
        "sample_rate_hz",
        "expected_sample_count",
        "observed_sample_count",
        "missing_sample_count",
        "coverage_fraction",
        "uncovered_region_count",
        "normalization",
        "logarithmic_unit",
        "receivers",
    }
    assert "timeline" not in sink.documents["power.summary"]


@pytest.mark.parametrize("analyzer", [QualityAnalyzer(), PowerAnalyzer()])
def test_empty_reader_is_insufficient_data_not_no_result(analyzer: object) -> None:
    reader = _ArrayIqReader(np.zeros((0, 1, 2), dtype="<i2"))
    result = analyzer.analyze(_context(block_samples=2), reader, _NoProducts(), _MemorySink())

    assert result.outcome is StageOutcome.INSUFFICIENT_DATA
    assert result.outcome is not StageOutcome.NO_RESULT
