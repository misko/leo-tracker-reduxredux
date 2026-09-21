"""Prepare causal per-scan positioning evidence and its bounded presentation."""

import time
from dataclasses import asdict
from io import BytesIO

import numpy as np

from leo.analysis.persistent_hop_trajectory import persistent_hop_tracklet_graph
from leo.analysis.sparse_scan_position import (
    DEFAULT_REGION,
    SparseScanPositionConfig,
    SparseScanPositionObservation,
    infer_sparse_scan_position,
)
from leo.application.scanner_trajectory import timing_is_qualified_for_tle
from leo.contracts.digests import canonical_digest
from leo.contracts.scanner_position import RegionPositionPriorV1, SparseScanPositionDiagnosticV1
from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets


def position_policy() -> dict:
    return {
        "algorithm": "scanner-conditional-position-v1",
        "region": asdict(DEFAULT_REGION),
        "numerics": asdict(SparseScanPositionConfig()),
        "identities": "non-abstaining-site-assisted-deduplicated-v1",
        "states": "nominal-causal-tle-support-centre-v1",
        "partition": "observation-id-hash-60-percent-v1",
    }


def build_scan_position_diagnostic(*, source, trajectory, product, catalogue_payload=None):
    """Never use ``product.observer_site`` as position evidence or a prior."""
    started = time.monotonic()
    reasons = []
    observations = []
    if not timing_is_qualified_for_tle(source.timing):
        reasons.append("utc-unqualified")
    if trajectory is None or not catalogue_payload or product.original_tle_snapshot is None:
        reasons.append("no-causal-associated-trajectory-evidence")
    if not reasons:
        start = source.capture_start_utc_ns or source.timing.first_sample_estimate_utc_ns
        if product.original_tle_snapshot.collected_utc_ns >= start:
            reasons.append("catalogue-not-strictly-before-capture")
        else:
            catalogue = parse_element_sets(catalogue_payload)
            by_number = dict(zip(catalogue.satellite_numbers, range(len(catalogue)), strict=True))
            epochs = catalogue.element_epoch_utc_ns()
            hypotheses = {h.hypothesis_id: h for h in trajectory.hypotheses}
            seen = set()
            for candidate in sorted(product.tle_candidates, key=lambda c: c.hypothesis_rank):
                if candidate.abstention_recommended or candidate.leading_catalog_number is None:
                    continue
                index = by_number.get(candidate.leading_catalog_number)
                if index is None or epochs[index] >= start:
                    reasons.append("selected-element-unavailable-or-future-epoch")
                    continue
                graph = persistent_hop_tracklet_graph(
                    hypotheses[candidate.hypothesis_id], candidate.representative_tracklet_id
                )
                rows = sorted(graph.observations, key=lambda r: r.support_center_utc_ns)
                if any(r.observation_id in seen for r in rows):
                    continue
                seen.update(r.observation_id for r in rows)
                utc = np.asarray([r.support_center_utc_ns for r in rows], dtype=np.int64)
                jd, fr = julian_day_from_utc_ns(utc)
                errors, p, v = catalogue.satellites[index].sgp4_array(jd, fr)
                if np.any(errors):
                    reasons.append("selected-element-propagation-failed")
                    continue
                p, v = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fr))
                for row, position, velocity in zip(rows, p, v, strict=True):
                    partition = int(canonical_digest(row.observation_id).split(":")[1][:8], 16)
                    observations.append(
                        SparseScanPositionObservation(
                            observation_id=row.observation_id,
                            support_utc_ns=row.support_center_utc_ns,
                            measured_cfo_hz=row.measured_cfo_hz,
                            source_id=str(candidate.leading_catalog_number),
                            segment_id=candidate.representative_tracklet_id,
                            training=partition % 10 < 6,
                            satellite_position_ecef_km=tuple(position),
                            satellite_velocity_ecef_km_s=tuple(velocity),
                        )
                    )
    result = infer_sparse_scan_position(tuple(observations))
    ids = result.selected_training_observation_ids + result.evaluation_observation_ids
    success = result.state == "complete"
    diagnostic = SparseScanPositionDiagnosticV1(
        state=(
            "diagnostic"
            if success
            else "failed"
            if result.state == "numerical-failure"
            else "insufficient"
        ),
        position_prior=RegionPositionPriorV1(
            center_latitude_deg=DEFAULT_REGION.latitude_deg,
            center_longitude_deg=DEFAULT_REGION.longitude_deg,
            width_km=DEFAULT_REGION.width_km,
            height_km=DEFAULT_REGION.height_km,
            altitude_m=0.0,
        ),
        source_count=result.source_count,
        track_count=len({r.segment_id for r in observations if r.observation_id in ids}),
        fit_observation_count=result.training_point_count,
        evaluation_observation_count=result.evaluation_point_count,
        selected_observation_ids=ids,
        selected_observations_digest=canonical_digest(
            [asdict(r) for r in observations if r.observation_id in ids]
        ),
        configuration_digest=canonical_digest(position_policy()),
        candidate_latitude_deg=result.latitude_deg if success else None,
        candidate_longitude_deg=result.longitude_deg if success else None,
        training_rms_hz=result.training_rms_hz if success else None,
        evaluation_rms_hz=result.evaluation_rms_hz if success else None,
        jacobian_rank=result.information_rank if success else None,
        condition_number=result.information_condition if success else None,
        boundary_hit=result.boundary_hit if success else None,
        reasons=tuple(dict.fromkeys((*reasons, *result.reasons))),
        runtime_ms=(time.monotonic() - started) * 1000,
    )
    return diagnostic, render_scan_position(diagnostic, result)


def render_scan_position(diagnostic, result) -> bytes:
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    figure = Figure(figsize=(11, 5), layout="constrained")
    left, right = figure.subplots(1, 2)
    figure.suptitle("Conditional scan positioning · site-assisted identities · no position fix")
    if result.map_east_km:
        points = left.scatter(
            result.map_east_km,
            result.map_north_km,
            c=result.map_training_rms_hz,
            s=8,
            rasterized=True,
        )
        figure.colorbar(points, ax=left, label="Profiled fit RMS (Hz)")
        if diagnostic.candidate_latitude_deg is not None:
            left.plot(result.east_km, result.north_km, "r+", markersize=12)
    left.set(xlabel="East of prior centre (km)", ylabel="North of prior centre (km)")
    left.xaxis.set_major_locator(MaxNLocator(5))
    left.yaxis.set_major_locator(MaxNLocator(5))
    right.axis("off")
    lines = [
        f"State: {diagnostic.state}",
        f"Sources: {diagnostic.source_count} · Tracks: {diagnostic.track_count}",
        f"Fit points: {diagnostic.fit_observation_count}",
        f"Evaluation points: {diagnostic.evaluation_observation_count}",
        "Prior: Denver-centred 9,000-mile square",
        "Fixed altitude: 0 m; nominal causal orbits",
        "No receiver truth used in position fit",
        "Not a calibrated uncertainty or blind location fix",
        *diagnostic.reasons,
    ]
    if diagnostic.state == "diagnostic":
        lines.extend(
            [
                "",
                f"Candidate: {diagnostic.candidate_latitude_deg:.5f}°, "
                f"{diagnostic.candidate_longitude_deg:.5f}°",
                f"Fit RMS: {diagnostic.training_rms_hz:.1f} Hz",
                f"Evaluation RMS: {diagnostic.evaluation_rms_hz:.1f} Hz",
            ]
        )
    right.text(0, 1, "\n".join(lines), va="top", fontsize=9, wrap=True)
    stream = BytesIO()
    figure.savefig(stream, format="png", dpi=120)
    return stream.getvalue()
