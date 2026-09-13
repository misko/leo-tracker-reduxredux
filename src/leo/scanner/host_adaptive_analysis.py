"""Native-10M actual-visit analysis using the existing fractional GLRT primitives.

The host's decimated online decision is separate evidence. Offline probes use
the retained native stream, its physical receiver and exact source counters.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Annotated, ClassVar, Literal

from pydantic import Field, field_validator

from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopAnalysisSource,
    AdaptiveHopProbeAnalysisV1,
    AdaptiveHopVisitAnalysisV1,
    _analyze_loaded_visit,
    _compare_source_fields,
)
from leo.scanner.host_adaptive import HostAdaptiveHopReceiptV2


class HostAdaptiveAnalysisConfigurationV2(AdaptiveHopAnalysisConfigurationV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    analyzer_id: Literal["host-adaptive-native-10m-fractional-glrt64-cfo-v2"] = (  # type: ignore[assignment]
        "host-adaptive-native-10m-fractional-glrt64-cfo-v2"  # type: ignore[assignment]
    )
    sample_rate_hz: Literal[10_000_000] = 10_000_000  # type: ignore[assignment]
    receiver_ids: tuple[Literal[0]] | tuple[Literal[1]] = Field(...)  # type: ignore[assignment]

    @field_validator("receiver_ids", mode="before")
    @classmethod
    def _exact_receivers(cls, value: object) -> object:
        if (
            not isinstance(value, (tuple, list))
            or len(value) != 1
            or type(value[0]) is not int
            or value[0] not in (0, 1)
        ):
            raise ValueError("host adaptive analysis requires one exact physical RX")
        return value


class HostAdaptiveVisitAnalysisV2(AdaptiveHopVisitAnalysisV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    configuration: HostAdaptiveAnalysisConfigurationV2
    probes: Annotated[tuple[AdaptiveHopProbeAnalysisV1, ...], Field(min_length=1, max_length=11)]


@dataclass(frozen=True, slots=True)
class HostAdaptiveAnalysisSource(AdaptiveHopAnalysisSource):
    _receipt_model: ClassVar[type[HostAdaptiveHopReceiptV2]] = HostAdaptiveHopReceiptV2
    receipt: HostAdaptiveHopReceiptV2 = field(init=False)


def _configuration(
    source: HostAdaptiveAnalysisSource, value: HostAdaptiveAnalysisConfigurationV2 | None
) -> HostAdaptiveAnalysisConfigurationV2:
    cfg = value or HostAdaptiveAnalysisConfigurationV2(
        receiver_ids=source.receipt.plan.geometry.receiver_ids
    )
    cfg = HostAdaptiveAnalysisConfigurationV2.model_validate(cfg.model_dump())
    if cfg.receiver_ids != source.receipt.plan.geometry.receiver_ids:
        raise ValueError("host adaptive analysis changed the physical source receiver")
    return cfg


def analyze_host_adaptive_visit(
    source: HostAdaptiveAnalysisSource,
    visit_index: int,
    *,
    configuration: HostAdaptiveAnalysisConfigurationV2 | None = None,
) -> HostAdaptiveVisitAnalysisV2:
    cfg = _configuration(source, configuration)
    result = _analyze_loaded_visit(
        source, visit_index, source.read_visit(visit_index), cfg, HostAdaptiveVisitAnalysisV2
    )
    assert isinstance(result, HostAdaptiveVisitAnalysisV2)
    return result


def analyze_host_adaptive_visit_batch(
    source: HostAdaptiveAnalysisSource,
    visit_indexes: tuple[int, ...],
    *,
    configuration: HostAdaptiveAnalysisConfigurationV2,
) -> Iterator[HostAdaptiveVisitAnalysisV2]:
    """At most four visits; only the owner reads IQ, and results retain order."""
    if not 1 <= len(visit_indexes) <= 4 or len(set(visit_indexes)) != len(visit_indexes):
        raise ValueError("host adaptive analysis batch requires one to four distinct visits")
    cfg = _configuration(source, configuration)
    samples = tuple(source.read_visit(index) for index in visit_indexes)
    with ThreadPoolExecutor(
        max_workers=len(visit_indexes), thread_name_prefix="leo-host-native"
    ) as pool:
        futures = [
            pool.submit(
                _analyze_loaded_visit, source, index, values, cfg, HostAdaptiveVisitAnalysisV2
            )
            for index, values in zip(visit_indexes, samples, strict=True)
        ]
        for future in futures:
            result = future.result()
            assert isinstance(result, HostAdaptiveVisitAnalysisV2)
            yield result


def validate_host_adaptive_analysis_binding(
    product: HostAdaptiveVisitAnalysisV2,
    receipt: HostAdaptiveHopReceiptV2,
    *,
    input_manifest_sha256: str,
) -> None:
    product = HostAdaptiveVisitAnalysisV2.model_validate(product.model_dump())
    receipt = HostAdaptiveHopReceiptV2.model_validate(receipt.model_dump())
    _compare_source_fields(product, receipt, input_manifest_sha256)
