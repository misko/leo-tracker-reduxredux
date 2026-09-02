from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.standard.native_pss import (
    StandardNativePssConfig,
    StandardNativePssRunner,
    _continuity_blocks,
    build_empty_standard_native_pss,
    standard_native_pss_configuration_digest,
    starlink_pss_channel_reference_hz,
)
from leo.analysis.starlink import PssBankSearchConfig, compile_pss_projection
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.standard_native_pss import StandardNativePssFrameTimingV1
from leo.contracts.standard_pipeline import StandardPathInputBindV5
from leo.pipeline.validity import DeviceIqSpan
from tests.analysis.test_standard_native_observability import (
    _fast_glrt_runner,
    _inventory,
    _Reader,
)
from tests.contracts.test_standard_path_input_bind_v4 import _values


def _binding(sample_rate_hz: int = 2_500_000) -> StandardPathInputBindV5:
    values = _values(sample_rate_hz)
    values.update(
        schema_version=5,
        algorithm_version="standard-path-input-bind-v5",
    )
    return StandardPathInputBindV5.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )


def test_channel_reference_is_edge_dependent_and_matches_reviewed_replays() -> None:
    assert starlink_pss_channel_reference_hz(1, "lower") == 1_074_882_812.5
    assert starlink_pss_channel_reference_hz(1, "upper") == 1_075_117_187.5
    assert starlink_pss_channel_reference_hz(4, "lower") == 1_824_882_812.5


def test_standard_pss_defaults_to_native_125ms_windows_with_half_overlap() -> None:
    config = StandardNativePssConfig()

    assert config.maximum_block_duration_s == 0.125
    assert config.block_overlap_duration_s == 0.0625
    assert config.blind_anchor_stride_s == 0.5
    assert config.tracking_frequency_half_width_hz == 100_000.0
    assert config.maximum_parallel_searches == 8
    assert config.maximum_refined_tracks == 1
    assert config.canonical_projection_sample_rate_hz == 25_000_000
    assert config.maximum_input_block_samples >= 3_125_000
    with pytest.raises(ValueError, match="block overlap"):
        StandardNativePssConfig(block_overlap_duration_s=0.125)


@pytest.mark.parametrize(
    "sample_rate_hz",
    (2_500_000, 3_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000),
)
def test_empty_standard_product_closes_all_reviewed_rate_geometry(sample_rate_hz: int) -> None:
    binding = _binding(sample_rate_hz)

    result = build_empty_standard_native_pss(binding)

    assert result.source == StandardNativeSourceV2.from_path_binding(binding)
    assert result.accounting.blind_block_count == 0
    assert result.accounting.retained_mode_count == 0
    assert result.blocks == result.modes == result.tracks == ()
    assert result.candidate_only
    assert not result.payload_decoded
    assert result.science_configuration_digest == standard_native_pss_configuration_digest(
        StandardNativePssConfig()
    )
    projection = result.projections[0]
    assert projection.output_sample_rate_hz == sample_rate_hz
    assert projection.input_sample_rate_hz == sample_rate_hz
    assert projection.decimation_factor == 1
    assert projection.edge_trim_output_samples == 0


def test_standard_pss_contract_rejects_digest_tampering() -> None:
    result = build_empty_standard_native_pss(_binding())
    document = result.model_dump(mode="json")
    document["channel_reference_hz"] += 1.0

    with pytest.raises(ValidationError, match="result digest"):
        StandardNativePssFrameTimingV1.model_validate(document)


def test_continuity_blocking_uses_complete_half_overlapping_windows() -> None:
    assert _continuity_blocks(
        segment_index=4,
        device_sample_start=100,
        sample_count=2_050,
        maximum_samples=1_000,
        stride_samples=500,
        minimum_samples=100,
    ) == (
        (4, 100, 1_000),
        (4, 600, 1_000),
        (4, 1_100, 1_000),
    )


@pytest.mark.parametrize("sample_rate_hz", (10_000_000, 15_000_000, 20_000_000, 25_000_000))
def test_pss_block_policy_preserves_native_125ms_geometry(sample_rate_hz: int) -> None:
    config = StandardNativePssConfig()
    maximum_samples = min(
        config.maximum_input_block_samples,
        round(config.maximum_block_duration_s * sample_rate_hz),
    )

    blocks = _continuity_blocks(
        segment_index=0,
        device_sample_start=0,
        sample_count=sample_rate_hz,
        maximum_samples=maximum_samples,
        stride_samples=round(
            (config.maximum_block_duration_s - config.block_overlap_duration_s) * sample_rate_hz
        ),
        minimum_samples=100_000,
    )

    assert blocks
    assert blocks[0][1] == 0
    assert blocks[-1][1] + blocks[-1][2] <= sample_rate_hz
    assert all(count == maximum_samples for _, _, count in blocks)
    assert maximum_samples > 1_048_576
    assert all(
        right_start - left_start
        == round(
            (config.maximum_block_duration_s - config.block_overlap_duration_s) * sample_rate_hz
        )
        for (_, left_start, left_count), (_, right_start, _) in zip(
            blocks[:-1],
            blocks[1:],
            strict=True,
        )
    )


def test_native_pss_chunks_device_reads_and_reuses_the_half_window_overlap() -> None:
    sample_rate_hz = 10_000_000
    binding = _binding(sample_rate_hz)

    class _BoundedReader:
        center_frequency_hz = binding.tuned_center_frequency_hz
        sample_rate_hz = binding.sample_rate_hz
        sample_count = binding.logical_sample_count
        observed_sample_count = binding.observed_sample_count
        missing_sample_count = binding.missing_sample_count
        receiver_ids = (binding.receiver_id,)
        validity_inventory = binding.validity_inventory

        def __init__(self) -> None:
            self.read_sizes: list[int] = []

        def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
            assert sample_count <= 1_048_576
            self.read_sizes.append(sample_count)
            return DeviceIqSpan(
                samples=np.ones((sample_count, 1, 2), dtype="<i2"),
                valid_samples=np.ones(sample_count, dtype=np.bool_),
                continuity_segment_ids=np.full(sample_count, 1, dtype=np.int32),
                device_sample_start=device_sample_start,
                receiver_ids=self.receiver_ids,
            )

    projection = compile_pss_projection(
        input_sample_rate_hz=sample_rate_hz,
        input_center_frequency_hz=float(binding.tuned_center_frequency_hz),
        rf_bandwidth_hz=binding.rf_bandwidth_hz,
        target_center_frequency_hz=float(binding.tuned_center_frequency_hz),
        channel_reference_hz=starlink_pss_channel_reference_hz(
            binding.starlink_channel,
            binding.starlink_edge,
        ),
        canonical_output_sample_rate_hz=25_000_000,
        edge_trim_output_samples=64,
    )
    reader = _BoundedReader()
    runner = StandardNativePssRunner()
    block_count = round(0.125 * sample_rate_hz)
    stride = round(0.0625 * sample_rate_hz)
    first = runner._read_projected_continuation(  # noqa: SLF001 - bounded-read seam
        reader,  # type: ignore[arg-type]
        binding,
        projection,
        segment_index=1,
        start=6,
        count=block_count,
        previous=None,
    )
    second = runner._read_projected_continuation(  # noqa: SLF001 - overlap-cache seam
        reader,  # type: ignore[arg-type]
        binding,
        projection,
        segment_index=1,
        start=6 + stride,
        count=block_count,
        previous=first,
    )

    assert first.samples.size == second.samples.size == block_count
    assert reader.read_sizes == [1_048_576, block_count - 1_048_576, stride]


def test_continuity_blocking_rejects_a_minimum_larger_than_the_reader_cap() -> None:
    with pytest.raises(ValueError, match="block bounds"):
        _continuity_blocks(
            segment_index=0,
            device_sample_start=0,
            sample_count=2_000,
            maximum_samples=999,
            stride_samples=500,
            minimum_samples=1_000,
        )


def test_standard_runner_searches_only_observed_continuity_blocks() -> None:
    sample_rate_hz = 2_500_000
    inventory = _inventory()
    values = _values(sample_rate_hz)
    values.update(
        schema_version=5,
        algorithm_version="standard-path-input-bind-v5",
        observed_sample_count=inventory.observed_sample_count,
        missing_sample_count=inventory.missing_sample_count,
        timeline_sha256=inventory.timeline_sha256,
        gap_map_content_digest=inventory.gap_map_content_digest,
        validity_inventory_sha256=inventory.inventory_digest,
        validity_inventory=inventory.model_dump(mode="json"),
    )
    binding = StandardPathInputBindV5.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
    reader = _Reader(inventory)
    glrt = _fast_glrt_runner(production_receiver_standard_config()).run(
        reader,
        binding,
        edge=binding.starlink_edge,
    )
    config = StandardNativePssConfig(
        blind_bank=PssBankSearchConfig(
            coarse_frequency_offsets_hz=(0.0,),
            fine_frequency_radius_hz=0.0,
            fine_frequency_step_hz=25_000.0,
        ),
        blind_anchor_stride_s=0.0625,
    )

    result = StandardNativePssRunner(config).run(
        reader,
        binding,
        full_capture_glrt=glrt,
    )

    assert result.accounting.blind_block_count == 14
    assert result.accounting.conditioned_block_count == 0
    assert result.accounting.retained_mode_count == 0
    assert all(
        block.input_device_sample_stop <= inventory.segments[0].device_sample_stop
        or block.input_device_sample_start >= inventory.segments[1].device_sample_start
        for block in result.blocks
    )
    assert all(
        block.input_device_sample_stop - block.input_device_sample_start
        == round(config.maximum_block_duration_s * sample_rate_hz)
        for block in result.blocks
    )
    expected_stride = round(
        (config.maximum_block_duration_s - config.block_overlap_duration_s) * sample_rate_hz
    )
    assert all(
        right.input_device_sample_start - left.input_device_sample_start == expected_stride
        for left, right in zip(result.blocks, result.blocks[1:], strict=False)
        if left.continuity_segment_index == right.continuity_segment_index
    )
    assert (
        _continuity_blocks(
            segment_index=5,
            device_sample_start=9_000,
            sample_count=99,
            maximum_samples=1_000,
            stride_samples=500,
            minimum_samples=100,
        )
        == ()
    )
