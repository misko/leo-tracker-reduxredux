"""Exact opened-long-arc evidence adapter for catalogue-association development.

The adapter is deliberately narrower than an experiment runner.  It verifies
the frozen protocol, registry, and report bytes; reconstructs the two reviewed
support-centred CFO episode graphs; and immediately derives the response-free
prediction-support port.  It does not read IQ, select catalogue objects,
propagate TLEs, rank candidates, or score an association.

Both registered arcs remain opened development data.  Building a graph is not
an identity result and does not satisfy the protocol's execution amendment.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from leo.analysis.research.long_arc_dataset import (
    LongArcBindingV1,
    PostFixLongArcCohortV1,
    load_post_fix_long_arc_cohort,
)
from leo.analysis.research.satellite_pnt_long_arc_protocol import (
    ArcObservationV1,
    SatellitePntLongArcProtocolV1,
    load_satellite_pnt_long_arc_protocol,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionSupportV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest

_ADAPTER_VERSION = "registered-post-fix-long-arc-graph-v1"
_NS_PER_S = 1_000_000_000
_FRAME_RATE_HZ = 750.0
_OFDM_SYMBOL_DURATION_S = 4.4e-6
_FIRST_SELECTED_SYMBOL = 2
_LAST_SELECTED_SYMBOL = 65
_DIRECT_CFO_SUPPORT_RULE = (
    "all symbols 2..65 must be complete; selection stops before the first incomplete "
    "selected-symbol frame"
)


class LongArcAdapterInputError(ValueError):
    """The frozen evidence or authority does not match the registered design."""


@dataclass(frozen=True, slots=True)
class RegisteredLongArcGraphBundle:
    """One exact response graph plus its narrow response-free projection."""

    arc_id: str
    protocol_digest: Sha256Digest
    cfo_evidence_digest: Sha256Digest
    timing_authority_digest: Sha256Digest
    graph: PhysicalEpisodeGraphV1
    prediction_support: CataloguePredictionSupportV1
    receipt_digest: Sha256Digest
    response_accessed_to_construct_graph: Literal[True] = field(default=True, init=False)
    response_exposed_to_prediction_port: Literal[False] = field(default=False, init=False)
    iq_accessed: Literal[False] = field(default=False, init=False)
    tle_propagation_run: Literal[False] = field(default=False, init=False)
    association_scored: Literal[False] = field(default=False, init=False)
    algorithm_version: Literal["registered-post-fix-long-arc-graph-v1"] = field(
        default="registered-post-fix-long-arc-graph-v1", init=False
    )


@dataclass(frozen=True, slots=True)
class _CfoRow:
    source_sample_start: int
    source_sample_end: int
    support_start_sample: int
    support_end_sample: int
    support_center_offset_ns_from_recording_start: int
    factorial_support_moments_s: tuple[float, float, float, float]
    measured_cfo_hz: float


def load_registered_long_arc_graph(
    protocol_path: Path,
    *,
    repository_root: Path,
    arc_id: str,
) -> RegisteredLongArcGraphBundle:
    """Load one exact registered graph without opening IQ or TLE bytes."""

    root = repository_root.resolve()
    protocol = load_satellite_pnt_long_arc_protocol(
        protocol_path,
        repository_root=root,
    )
    cohort = load_post_fix_long_arc_cohort(_resolve(root, protocol.registry.path))
    observation = _protocol_observation(protocol, arc_id)
    cfo_payload = _resolve(root, observation.cfo_evidence.path).read_bytes()
    if observation.timing_authority.path == observation.cfo_evidence.path:
        timing_payload = cfo_payload
    else:
        timing_payload = _resolve(root, observation.timing_authority.path).read_bytes()
    return build_registered_long_arc_graph(
        protocol,
        cohort,
        arc_id=arc_id,
        cfo_evidence_payload=cfo_payload,
        timing_authority_payload=timing_payload,
    )


def build_registered_long_arc_graph(
    protocol: SatellitePntLongArcProtocolV1,
    cohort: PostFixLongArcCohortV1,
    *,
    arc_id: str,
    cfo_evidence_payload: bytes,
    timing_authority_payload: bytes,
) -> RegisteredLongArcGraphBundle:
    """Construct one graph from already supplied, exact frozen evidence bytes."""

    protocol = _revalidate_protocol(protocol)
    cohort = _revalidate_cohort(cohort)
    observation_authority = _protocol_observation(protocol, arc_id)
    arc = cohort.arc(arc_id)
    _validate_arc_authority(protocol, cohort, observation_authority, arc)
    _validate_payload_digest(
        cfo_evidence_payload,
        observation_authority.cfo_evidence.sha256,
        "CFO evidence",
    )
    _validate_payload_digest(
        timing_authority_payload,
        observation_authority.timing_authority.sha256,
        "timing authority",
    )
    cfo_document = _load_json(cfo_evidence_payload, "CFO evidence")
    timing_document = (
        cfo_document
        if cfo_evidence_payload is timing_authority_payload
        or cfo_evidence_payload == timing_authority_payload
        else _load_json(timing_authority_payload, "timing authority")
    )
    period_ns = _sample_period_ns(arc.path.sample_rate_hz)
    if arc_id.startswith("long-arc-9981"):
        rows = _rows_9981(cfo_document, observation_authority, arc, period_ns)
    elif arc_id.startswith("long-arc-150802"):
        rows = _rows_150802(
            cfo_document,
            timing_document,
            observation_authority,
            arc,
            period_ns,
        )
    else:
        raise LongArcAdapterInputError("arc is not supported by the frozen adapter")

    graph = _build_graph(protocol, observation_authority, arc, rows, period_ns)
    support = CataloguePredictionSupportV1.from_graph(graph)
    receipt_payload = {
        "algorithm_version": _ADAPTER_VERSION,
        "arc_id": arc_id,
        "protocol_digest": protocol.protocol_digest,
        "cfo_evidence_digest": observation_authority.cfo_evidence.sha256,
        "timing_authority_digest": observation_authority.timing_authority.sha256,
        "graph_content_digest": graph.content_digest,
        "prediction_support_content_digest": support.content_digest,
        "response_accessed_to_construct_graph": True,
        "response_exposed_to_prediction_port": False,
        "iq_accessed": False,
        "tle_propagation_run": False,
        "association_scored": False,
    }
    return RegisteredLongArcGraphBundle(
        arc_id=arc_id,
        protocol_digest=protocol.protocol_digest,
        cfo_evidence_digest=observation_authority.cfo_evidence.sha256,
        timing_authority_digest=observation_authority.timing_authority.sha256,
        graph=graph,
        prediction_support=support,
        receipt_digest=canonical_digest(receipt_payload),
    )


def _rows_9981(
    document: Mapping[str, Any],
    authority: ArcObservationV1,
    arc: LongArcBindingV1,
    period_ns: int,
) -> tuple[_CfoRow, ...]:
    glrt = _mapping(document.get("glrt"), "9981 GLRT evidence")
    if (
        glrt.get("window_duration_ms") != 20.0
        or glrt.get("probe_start_cadence_ms") != 25.0
        or glrt.get("selected_alias_index") != arc.source_binding.alias_index
    ):
        raise LongArcAdapterInputError("9981 GLRT geometry disagrees with the frozen source")
    raw_rows = _sequence(glrt.get("unique_observations"), "9981 unique observations")
    if len(raw_rows) != authority.expected_observation_count:
        raise LongArcAdapterInputError("9981 observation count disagrees with protocol")
    window_samples = authority.window_sample_count
    center_offset_ns = ((window_samples - 1) * period_ns) // 2
    if (window_samples - 1) * period_ns % 2:
        raise LongArcAdapterInputError("9981 uniform support centre is not UTC-ns exact")
    period_s = period_ns / _NS_PER_S
    variance_s2 = period_s**2 * (window_samples**2 - 1) / 12.0
    moments = (1.0, 0.0, variance_s2 / 2.0, 0.0)
    rows: list[_CfoRow] = []
    previous_start = -1
    for raw_row in raw_rows:
        values = _sequence(raw_row, "9981 observation row")
        if len(values) != 2:
            raise LongArcAdapterInputError("9981 observation rows must contain time and CFO")
        time_s = _finite_float(values[0], "9981 probe time")
        cfo_hz = _finite_float(values[1], "9981 CFO")
        source_start = round(time_s * arc.path.sample_rate_hz)
        if not math.isclose(
            source_start / arc.path.sample_rate_hz,
            time_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise LongArcAdapterInputError("9981 probe time is not on the source sample grid")
        if source_start <= previous_start:
            raise LongArcAdapterInputError("9981 observations must be strictly time ordered")
        previous_start = source_start
        rows.append(
            _CfoRow(
                source_sample_start=source_start,
                source_sample_end=source_start + window_samples,
                support_start_sample=source_start,
                support_end_sample=source_start + window_samples,
                support_center_offset_ns_from_recording_start=(
                    source_start * period_ns + center_offset_ns
                ),
                factorial_support_moments_s=moments,
                measured_cfo_hz=cfo_hz,
            )
        )
    _validate_rows_inside_arc(rows, arc)
    return tuple(rows)


def _rows_150802(
    document: Mapping[str, Any],
    timing_document: Mapping[str, Any],
    authority: ArcObservationV1,
    arc: LongArcBindingV1,
    period_ns: int,
) -> tuple[_CfoRow, ...]:
    if document.get("schema") != "org.leo.research.detailed-epoch-doppler-curvature/v1":
        raise LongArcAdapterInputError("150802 CFO evidence schema is not frozen")
    if document.get("sample_rate_hz") != float(arc.path.sample_rate_hz):
        raise LongArcAdapterInputError("150802 evidence sample rate disagrees")
    direct = _mapping(
        _mapping(timing_document.get("measurement_time_support"), "timing support").get(
            "direct_cfo"
        ),
        "direct-CFO timing support",
    )
    if (
        direct.get("absolute_time_rule")
        != "(detection_sample_start+mean(all supported symbol centers))/sample_rate_hz"
        or direct.get("selected_symbols_inclusive") != [2, 65]
        or direct.get("window_sample_count") != authority.window_sample_count
        or direct.get("support_rule") != _DIRECT_CFO_SUPPORT_RULE
    ):
        raise LongArcAdapterInputError("150802 direct-CFO support semantics are not frozen")
    raw_rows = _sequence(document.get("detections"), "150802 detections")
    if len(raw_rows) != authority.expected_observation_count:
        raise LongArcAdapterInputError("150802 observation count disagrees with protocol")
    rows: list[_CfoRow] = []
    previous_start = -1
    for raw_row in raw_rows:
        item = _mapping(raw_row, "150802 detection")
        source_start = _integer(item.get("detection_sample_start"), "detection sample start")
        local_epoch = _integer(item.get("local_epoch_sample"), "local epoch sample")
        absolute_epoch = _integer(item.get("absolute_epoch_sample"), "absolute epoch sample")
        if source_start + local_epoch != absolute_epoch:
            raise LongArcAdapterInputError("150802 local and absolute epoch samples disagree")
        probe_time_s = _finite_float(item.get("probe_time_s"), "150802 probe time")
        if not math.isclose(
            source_start / arc.path.sample_rate_hz,
            probe_time_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise LongArcAdapterInputError("150802 probe time is not on the source sample grid")
        if source_start <= previous_start:
            raise LongArcAdapterInputError("150802 observations must be strictly time ordered")
        previous_start = source_start
        support = _glrt64_symbol_support(
            local_epoch,
            window_sample_count=authority.window_sample_count,
            sample_rate_hz=arc.path.sample_rate_hz,
            period_ns=period_ns,
        )
        rows.append(
            _CfoRow(
                source_sample_start=source_start,
                source_sample_end=source_start + authority.window_sample_count,
                support_start_sample=source_start + support[0],
                support_end_sample=source_start + support[1],
                support_center_offset_ns_from_recording_start=(
                    source_start * period_ns + support[2]
                ),
                factorial_support_moments_s=support[3],
                measured_cfo_hz=_finite_float(item.get("tracking_cfo_hz"), "150802 tracking CFO"),
            )
        )
    _validate_rows_inside_arc(rows, arc)
    return tuple(rows)


def _glrt64_symbol_support(
    local_epoch_sample: int,
    *,
    window_sample_count: int,
    sample_rate_hz: int,
    period_ns: int,
) -> tuple[int, int, int, tuple[float, float, float, float]]:
    if local_epoch_sample < 0:
        raise LongArcAdapterInputError("GLRT64 local epoch must be nonnegative")
    frame_period_samples = sample_rate_hz / _FRAME_RATE_HZ
    symbol_period_samples = sample_rate_hz * _OFDM_SYMBOL_DURATION_S
    starts: list[int] = []
    stops: list[int] = []
    centers_ns: list[int] = []
    frame_index = 0
    while True:
        frame_start = local_epoch_sample + round(frame_index * frame_period_samples)
        first_start = frame_start + round(_FIRST_SELECTED_SYMBOL * symbol_period_samples)
        if frame_start >= window_sample_count or first_start >= window_sample_count:
            break
        frame_starts: list[int] = []
        frame_stops: list[int] = []
        for symbol in range(_FIRST_SELECTED_SYMBOL, _LAST_SELECTED_SYMBOL + 1):
            start = frame_start + round(symbol * symbol_period_samples)
            stop = frame_start + round((symbol + 1) * symbol_period_samples)
            if start < 0 or stop > window_sample_count or stop <= start:
                frame_starts = []
                break
            frame_starts.append(start)
            frame_stops.append(stop)
        if not frame_starts:
            break
        starts.extend(frame_starts)
        stops.extend(frame_stops)
        centers_ns.extend(
            ((2 * start + (stop - start - 1)) * period_ns) // 2
            for start, stop in zip(frame_starts, frame_stops, strict=True)
        )
        frame_index += 1
    if not centers_ns or frame_index not in (14, 15):
        raise LongArcAdapterInputError("GLRT64 support must contain 14 or 15 complete frames")
    center_ns = round(sum(centers_ns) / len(centers_ns))
    offsets_s = tuple((item - center_ns) / _NS_PER_S for item in centers_ns)
    moments = tuple(
        sum(offset**degree for offset in offsets_s) / len(offsets_s) / math.factorial(degree)
        for degree in range(4)
    )
    return min(starts), max(stops), center_ns, moments  # type: ignore[return-value]


def _build_graph(
    protocol: SatellitePntLongArcProtocolV1,
    authority: ArcObservationV1,
    arc: LongArcBindingV1,
    rows: tuple[_CfoRow, ...],
    period_ns: int,
) -> PhysicalEpisodeGraphV1:
    episode_id = canonical_digest(
        {
            "algorithm_version": _ADAPTER_VERSION,
            "protocol_digest": protocol.protocol_digest,
            "arc_id": arc.arc_id,
            "source_binding": arc.source_binding.model_dump(mode="json"),
        }
    )
    dwell_id = canonical_digest(
        {
            "session_id": arc.provenance.session_id,
            "recording_manifest_digest": arc.provenance.recording_manifest_sha256,
        }
    )
    lane_id = canonical_digest(
        {
            "radio_serial": arc.path.radio_serial,
            "stream_id": arc.path.stream_id,
            "receiver_id": arc.path.receiver_id,
            "edge": arc.path.edge,
        }
    )
    receiver_path_id = canonical_digest(arc.path.model_dump(mode="json"))
    raw_authority = canonical_digest(
        {
            "recording_manifest_uri": arc.provenance.recording_manifest_uri,
            "recording_manifest_digest": arc.provenance.recording_manifest_sha256,
            "validated_stream_generation": arc.continuity.validated_stream_generation,
            "timeline_digest": arc.continuity.timeline_sha256,
            "gap_map_digest": arc.continuity.gap_map_sha256,
        }
    )
    hardware_epoch_id = (
        f"{arc.path.radio_id.replace('_', '-')}-{arc.continuity.validated_stream_generation}"
    )
    observations: list[SupportIntegratedCfoObservationV1] = []
    first_utc_ns = arc.span.first_sample_estimate_utc_ns
    for index, row in enumerate(rows):
        source_binding_digest = canonical_digest(
            {
                "arc_source_binding": arc.source_binding.model_dump(mode="json"),
                "source_sample_start": row.source_sample_start,
                "source_sample_end": row.source_sample_end,
            }
        )
        source_group_id = canonical_digest(
            {
                "raw_recording_authority_digest": raw_authority,
                "stream_id": arc.path.stream_id,
                "source_sample_start": row.source_sample_start,
                "source_sample_end": row.source_sample_end,
            }
        )
        observation_id = canonical_digest(
            {
                "algorithm_version": _ADAPTER_VERSION,
                "episode_id": episode_id,
                "source_group_id": source_group_id,
                "ordinal": index,
                "support_start_sample": row.support_start_sample,
                "support_end_sample": row.support_end_sample,
                "support_center_offset_ns": row.support_center_offset_ns_from_recording_start,
            }
        )
        observations.append(
            SupportIntegratedCfoObservationV1(
                observation_id=observation_id,
                source_group_id=source_group_id,
                episode_id=episode_id,
                receiver_path_id=receiver_path_id,
                hardware_epoch_id=hardware_epoch_id,
                raw_recording_authority_digest=raw_authority,
                recording_manifest_digest=arc.provenance.recording_manifest_sha256,
                stream_id=arc.path.stream_id,
                source_binding_digest=source_binding_digest,
                source_sample_start=row.source_sample_start,
                source_sample_end=row.source_sample_end,
                support_start_utc_ns=(first_utc_ns + row.support_start_sample * period_ns),
                support_center_utc_ns=(
                    first_utc_ns + row.support_center_offset_ns_from_recording_start
                ),
                support_end_utc_ns=(first_utc_ns + row.support_end_sample * period_ns),
                measured_cfo_hz=row.measured_cfo_hz,
                standard_uncertainty_hz=protocol.models.observation_sigma_hz,
                factorial_support_moments_s=row.factorial_support_moments_s,
            )
        )
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=dwell_id,
        lane_id=lane_id,
        order_index=0,
        continuity_component_id=source_binding_digest_for_episode(arc),
        observation_ids=tuple(item.observation_id for item in observations),
    )
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=(episode,),
    )


def source_binding_digest_for_episode(arc: LongArcBindingV1) -> Sha256Digest:
    """Return the frozen continuity-component identity for one registered arc."""

    return canonical_digest(
        {
            "algorithm_version": "registered-long-arc-continuity-component-v1",
            "recording_manifest_digest": arc.provenance.recording_manifest_sha256,
            "stream_id": arc.path.stream_id,
            "validated_stream_generation": arc.continuity.validated_stream_generation,
            "arc_sample_start": arc.span.sample_start,
            "arc_sample_stop_exclusive": arc.span.sample_stop_exclusive,
            "source_binding": arc.source_binding.model_dump(mode="json"),
        }
    )


def _validate_arc_authority(
    protocol: SatellitePntLongArcProtocolV1,
    cohort: PostFixLongArcCohortV1,
    authority: ArcObservationV1,
    arc: LongArcBindingV1,
) -> None:
    if cohort.authority.arc_ids != protocol.expected_arc_ids:
        raise LongArcAdapterInputError("protocol and registry arc inventories disagree")
    if authority.arc_id != arc.arc_id or authority.sample_rate_hz != arc.path.sample_rate_hz:
        raise LongArcAdapterInputError("protocol observation authority disagrees with registry")
    evidence = {item.path: item.sha256 for item in arc.evidence}
    for binding in (authority.cfo_evidence, authority.timing_authority):
        if evidence.get(binding.path) != binding.sha256:
            raise LongArcAdapterInputError("protocol evidence is absent from the arc registry")
    if arc.research_status.holdout_authority or arc.research_status.secure_identity_authority:
        raise LongArcAdapterInputError("registered arcs must remain opened development only")


def _validate_rows_inside_arc(rows: Sequence[_CfoRow], arc: LongArcBindingV1) -> None:
    if any(
        row.source_sample_start < arc.span.sample_start
        or row.source_sample_end > arc.span.sample_stop_exclusive
        or row.support_start_sample < row.source_sample_start
        or row.support_end_sample > row.source_sample_end
        for row in rows
    ):
        raise LongArcAdapterInputError("observation support escapes the exact registered span")
    if any(
        right.source_sample_start < left.source_sample_end
        for left, right in zip(rows, rows[1:], strict=False)
    ):
        raise LongArcAdapterInputError("diagonal observation model rejects overlapping windows")


def _protocol_observation(
    protocol: SatellitePntLongArcProtocolV1,
    arc_id: str,
) -> ArcObservationV1:
    for observation in protocol.observations:
        if observation.arc_id == arc_id:
            return observation
    raise LongArcAdapterInputError("arc is absent from the frozen protocol")


def _revalidate_protocol(
    protocol: SatellitePntLongArcProtocolV1,
) -> SatellitePntLongArcProtocolV1:
    try:
        return SatellitePntLongArcProtocolV1.model_validate(
            protocol.model_dump(mode="json", by_alias=True)
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcAdapterInputError("protocol document is invalid") from error


def _revalidate_cohort(cohort: PostFixLongArcCohortV1) -> PostFixLongArcCohortV1:
    try:
        return PostFixLongArcCohortV1.model_validate(cohort.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcAdapterInputError("long-arc registry document is invalid") from error


def _load_json(payload: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise LongArcAdapterInputError(f"{label} is not canonical JSON") from error
    return _mapping(value, label)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LongArcAdapterInputError(f"{label} must be a JSON object")
    return value


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise LongArcAdapterInputError(f"{label} must be a JSON array")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise LongArcAdapterInputError(f"{label} must be an integer")
    return value


def _finite_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise LongArcAdapterInputError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise LongArcAdapterInputError(f"{label} must be finite")
    return result


def _sample_period_ns(sample_rate_hz: int) -> int:
    if sample_rate_hz <= 0 or _NS_PER_S % sample_rate_hz:
        raise LongArcAdapterInputError("sample rate must have an exact integer UTC-ns period")
    return _NS_PER_S // sample_rate_hz


def _validate_payload_digest(payload: bytes, expected: str, label: str) -> None:
    if sha256_digest(payload) != expected:
        raise LongArcAdapterInputError(f"{label} digest does not match protocol")


def _resolve(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise LongArcAdapterInputError(
            "registered evidence path does not resolve inside repository"
        )
    return candidate


__all__ = [
    "LongArcAdapterInputError",
    "RegisteredLongArcGraphBundle",
    "build_registered_long_arc_graph",
    "load_registered_long_arc_graph",
    "source_binding_digest_for_episode",
]
