"""Compile one explicit target-centered Qin pilot search coordinate."""

from __future__ import annotations

import math
from dataclasses import dataclass

from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration
from leo.analysis.starlink.seeded_acquisition import canonicalize_cfo_alias
from leo.analysis.starlink.templates import edge_frequencies_hz
from leo.contracts.digests import canonical_digest
from leo.contracts.starlink_frequency import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_rf_center_frequency_hz,
)
from leo.contracts.states import StarlinkEdge


class PilotSearchGeometryError(ValueError):
    """The requested pilot search cannot be observed by the bound capture."""


@dataclass(frozen=True, slots=True)
class PilotSearchGeometry:
    """Closed baseband frequency geometry for one receiver-path pilot search."""

    receiver_id: str
    starlink_channel: int
    edge: StarlinkEdge
    tuned_center_frequency_hz: int
    pilot_if_center_frequency_hz: int
    nominal_pilot_baseband_hz: float
    sample_rate_hz: int
    rf_bandwidth_hz: int
    usable_baseband_min_hz: float
    usable_baseband_max_hz: float
    template_min_offset_hz: float
    template_max_offset_hz: float
    residual_cfo_min_hz: float
    residual_cfo_max_hz: float
    search_baseband_min_hz: float
    search_baseband_max_hz: float
    frequency_reference: ReceiverFrequencyCalibration


@dataclass(frozen=True, slots=True)
class CanonicalPilotCfo:
    """One raw baseband CFO expressed in the pilot-relative alias coordinate."""

    nominal_pilot_baseband_hz: float
    raw_baseband_cfo_hz: float
    raw_residual_cfo_hz: float
    canonical_residual_cfo_hz: float
    alias_lift: int


def canonicalize_pilot_cfo(
    raw_baseband_cfo_hz: float,
    *,
    starlink_channel: int,
    edge: StarlinkEdge | str,
    tuned_center_frequency_hz: int,
    lnb_lo_hz: int = STARLINK_LNB_LO_HZ,
) -> CanonicalPilotCfo:
    """Remove capture tuning and choose a deterministic OFDM CFO alias.

    Detector CFOs remain raw tuner-baseband coordinates because that is the
    frequency needed to derotate source IQ.  Presentation and association must
    instead compare the offset from the selected pilot's nominal baseband
    position.  Canonicalizing only after that subtraction makes the result
    independent of capture-center displacement and of the GLRT alias branch.
    """

    raw = float(raw_baseband_cfo_hz)
    if not math.isfinite(raw):
        raise ValueError("pilot CFO must be finite")
    if (
        isinstance(starlink_channel, bool)
        or not isinstance(starlink_channel, int)
        or isinstance(tuned_center_frequency_hz, bool)
        or not isinstance(tuned_center_frequency_hz, int)
        or isinstance(lnb_lo_hz, bool)
        or not isinstance(lnb_lo_hz, int)
        or min(tuned_center_frequency_hz, lnb_lo_hz) <= 0
    ):
        raise ValueError("pilot CFO requires positive integer capture geometry")
    selected_edge = StarlinkEdge(edge)
    pilot_if_hz = (
        starlink_edge_rf_center_frequency_hz(starlink_channel, selected_edge) - lnb_lo_hz
    )
    nominal = float(pilot_if_hz - tuned_center_frequency_hz)
    residual = raw - nominal
    canonical, lift = canonicalize_cfo_alias(residual)
    return CanonicalPilotCfo(
        nominal_pilot_baseband_hz=nominal,
        raw_baseband_cfo_hz=raw,
        raw_residual_cfo_hz=residual,
        canonical_residual_cfo_hz=canonical,
        alias_lift=lift,
    )


def compile_pilot_search_geometry(
    *,
    receiver_id: str | int,
    starlink_channel: int,
    edge: StarlinkEdge | str,
    tuned_center_frequency_hz: int,
    sample_rate_hz: int,
    rf_bandwidth_hz: int,
    residual_cfo_min_hz: float,
    residual_cfo_max_hz: float,
    lnb_lo_hz: int = STARLINK_LNB_LO_HZ,
) -> PilotSearchGeometry:
    """Bind a residual CFO policy to the planned Qin pilot center.

    The acquisition kernel synthesizes its template at the source sample rate,
    so no resampling or IQ translation is needed.  Its frequency reference is
    simply the nominal pilot center expressed relative to tuner DC.
    """

    receiver = str(receiver_id)
    selected_edge = StarlinkEdge(edge)
    integer_values = (
        starlink_channel,
        tuned_center_frequency_hz,
        sample_rate_hz,
        rf_bandwidth_hz,
        lnb_lo_hz,
    )
    if (
        not receiver
        or any(isinstance(value, bool) or not isinstance(value, int) for value in integer_values)
        or min(tuned_center_frequency_hz, sample_rate_hz, rf_bandwidth_hz, lnb_lo_hz) <= 0
    ):
        raise ValueError("pilot search requires a receiver and positive integer capture geometry")
    residuals = (float(residual_cfo_min_hz), float(residual_cfo_max_hz))
    if not all(math.isfinite(value) for value in residuals) or residuals[0] >= residuals[1]:
        raise ValueError("pilot residual CFO bounds must be finite and increasing")

    pilot_if_hz = starlink_edge_rf_center_frequency_hz(starlink_channel, selected_edge) - lnb_lo_hz
    nominal_baseband_hz = float(pilot_if_hz - tuned_center_frequency_hz)
    half_usable_hz = min(sample_rate_hz, rf_bandwidth_hz) / 2.0
    usable_min_hz = -half_usable_hz
    usable_max_hz = half_usable_hz
    template_offsets = edge_frequencies_hz(selected_edge)
    template_min_hz = float(template_offsets.min())
    template_max_hz = float(template_offsets.max())
    search_min_hz = nominal_baseband_hz + residuals[0]
    search_max_hz = nominal_baseband_hz + residuals[1]
    occupied_search_min_hz = search_min_hz + template_min_hz
    occupied_search_max_hz = search_max_hz + template_max_hz
    if occupied_search_min_hz < usable_min_hz or occupied_search_max_hz > usable_max_hz:
        raise PilotSearchGeometryError(
            "complete pilot search band is outside the capture's usable baseband: "
            f"needed [{occupied_search_min_hz:g}, {occupied_search_max_hz:g}] Hz, "
            f"available [{usable_min_hz:g}, {usable_max_hz:g}] Hz"
        )

    digest_document = {
        "kind": "qin-pilot-search-frequency-reference-v1",
        "receiver_id": receiver,
        "starlink_channel": starlink_channel,
        "starlink_edge": selected_edge.value,
        "tuned_center_frequency_hz": tuned_center_frequency_hz,
        "pilot_if_center_frequency_hz": pilot_if_hz,
        "nominal_pilot_baseband_hz": nominal_baseband_hz,
        "sample_rate_hz": sample_rate_hz,
        "rf_bandwidth_hz": rf_bandwidth_hz,
        "usable_baseband_min_hz": usable_min_hz,
        "usable_baseband_max_hz": usable_max_hz,
        "template_min_offset_hz": template_min_hz,
        "template_max_offset_hz": template_max_hz,
        "residual_cfo_min_hz": residuals[0],
        "residual_cfo_max_hz": residuals[1],
        "search_baseband_min_hz": search_min_hz,
        "search_baseband_max_hz": search_max_hz,
    }
    if lnb_lo_hz != STARLINK_LNB_LO_HZ:
        digest_document["lnb_lo_hz"] = lnb_lo_hz
    frequency_reference = ReceiverFrequencyCalibration(
        receiver_id=receiver,
        center_hz=nominal_baseband_hz,
        calibration_sha256=canonical_digest(digest_document).removeprefix("sha256:"),
    )
    return PilotSearchGeometry(
        receiver_id=receiver,
        starlink_channel=starlink_channel,
        edge=selected_edge,
        tuned_center_frequency_hz=tuned_center_frequency_hz,
        pilot_if_center_frequency_hz=pilot_if_hz,
        nominal_pilot_baseband_hz=nominal_baseband_hz,
        sample_rate_hz=sample_rate_hz,
        rf_bandwidth_hz=rf_bandwidth_hz,
        usable_baseband_min_hz=usable_min_hz,
        usable_baseband_max_hz=usable_max_hz,
        template_min_offset_hz=template_min_hz,
        template_max_offset_hz=template_max_hz,
        residual_cfo_min_hz=residuals[0],
        residual_cfo_max_hz=residuals[1],
        search_baseband_min_hz=search_min_hz,
        search_baseband_max_hz=search_max_hz,
        frequency_reference=frequency_reference,
    )
