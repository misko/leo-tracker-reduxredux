"""Select numerical results before applying evaluation-only reference metadata."""

import math

from leo.analysis.regional_position_score import coordinates
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.contracts.regional_position_products import RegionalPositionDocumentV1
from leo.contracts.regional_position_v2 import RegionalPositionDocumentV2
from leo.contracts.regional_position_v3 import RegionalPositionDocumentV3


def regional_position_document(
    result,
    *,
    session_id,
    input_digest,
    analysis_digest,
    evidence_digest,
    configuration,
    windows,
    reference,
    reference_evidence,
    diagnostics=None,
):
    prior = RegionalPrior()
    b7 = configuration.get("protocol") == "sacramento-hard60-b7-v1"
    hard60 = b7 or configuration.get("protocol") == "sacramento-hard60-v1"
    methods = []
    for name in ("V16",) if hard60 else ("T1AT", "V16"):
        search = result["searches"][name]
        points = []
        for row in search["evaluations"]:
            key = f"point:{row['east_km']:g}:{row['north_km']:g}"
            receipt = result["points"][key]
            point = receipt["result"]
            fit = point["fits"][name]["fit"] if point else None
            reason = point["fits"][name]["reason"] if point else receipt["reason"]
            points.append(
                dict(
                    east_km=row["east_km"],
                    north_km=row["north_km"],
                    spacing_km=row["spacing_km"],
                    objective=fit["objective"] if fit else None,
                    converged=fit["converged"] if fit else False,
                    reason=reason,
                )
            )
        arms = []
        for arm in ("fitted-c", "zero-c"):
            starts = [
                row for row in result["finals"] if row["method"] == name and row["arm"] == arm
            ]
            completed = [row for row in starts if row["fit"] is not None]
            eligible = (
                [row for row in completed if row["fit"]["converged"]] if hard60 else completed
            )
            selected = None
            if eligible:
                # Reference is deliberately absent from this ordering.
                best = min(
                    eligible,
                    key=lambda row: (
                        row["fit"]["objective"] + row["calibration_penalty"],
                        row["basin"],
                        row["start"],
                    ),
                )
                fit = best["fit"]
                vector = fit["vector"]
                latitude, longitude = coordinates(prior, vector[:2])
                lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *reference))
                haversine = (
                    math.sin((lat - ref_lat) / 2) ** 2
                    + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
                )
                error_m = 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, haversine))))
                selected = dict(
                    latitude_deg=latitude,
                    longitude_deg=longitude,
                    east_km=vector[0],
                    north_km=vector[1],
                    objective=fit["objective"],
                    calibration_penalty=best["calibration_penalty"],
                    selection_score=fit["objective"] + best["calibration_penalty"],
                    posterior_rms_hz=fit["posterior_rms_hz"],
                    signal_windows=fit["signal_windows"],
                    stationarity=fit["stationarity"],
                    converged=fit["converged"],
                    boundary=fit["boundary"],
                    coefficient_hz_per_ghz=vector[6],
                    horizontal_error_m=error_m,
                    satellites=best["satellites"],
                    associated_windows=best["association"]["final"]["assigned"],
                    source_basin=best["basin"],
                    stop_reason=fit["stop_reason"],
                )
                if b7:
                    selected.update(
                        accepted_stage=best.get("accepted_stage", "B1"),
                        joint_state=fit.get("joint_state"),
                    )
            reasons = [row["reason"] for row in starts if row["reason"]]
            if hard60:
                reasons.extend(
                    f"nonstationary:{row['basin']}:{row['start']}"
                    for row in completed
                    if not row["fit"]["converged"]
                )
            reasons.extend(row["reason"] for row in result["failures"])
            if selected is None and not reasons:
                reasons = ["no-supported-regional-basin"]
            arms.append(
                dict(
                    name=arm,
                    selected=selected,
                    completed_starts=len(completed),
                    reasons=sorted(set(reasons)),
                )
            )
        methods.append(
            dict(
                name=name,
                state="diagnostic" if any(a["selected"] for a in arms) else "insufficient",
                points=points,
                search_stop_reason=search["stop_reason"],
                deferred_cells=search["deferred_cells"],
                arms=arms,
            )
        )
    receipt = dict(diagnostics or {})
    receipt["regional_failures"] = result["failures"]
    if b7:
        receipt["b7"] = result.get("b7", {})
    if hard60:
        receipt["calibrations"] = result.get("calibrations", {})
        receipt["retained_basins"] = result.get("basins", [])
        if "recovery" in result:
            receipt["recovery"] = result["recovery"]
        receipt["coarse_optimizer_mismatches"] = {
            key: p["result"]["fits"]["V16"]["optimizer"]
            for key, p in result["points"].items()
            if p["result"]
            and p["result"]["fits"]["V16"].get("optimizer", {}).get("solver_success")
            and not p["result"]["fits"]["V16"]["fit"]["converged"]
        }
    receipt["final_starts"] = [
        dict(
            method=row["method"],
            arm=row["arm"],
            basin=row["basin"],
            start=row["start"],
            fit=row["fit"],
            reason=row["reason"],
            calibration_penalty=row["calibration_penalty"],
        )
        for row in result["finals"]
    ]
    model = (
        RegionalPositionDocumentV3
        if b7
        else RegionalPositionDocumentV2
        if hard60
        else RegionalPositionDocumentV1
    )
    return model.model_validate(
        dict(
            session_id=session_id,
            input_manifest_sha256=input_digest,
            analysis_manifest_sha256=analysis_digest,
            evidence_sha256=evidence_digest,
            configuration=configuration,
            configuration_sha256=canonical_digest(configuration),
            windows=windows,
            methods=methods,
            reference_latitude_deg=reference[0],
            reference_longitude_deg=reference[1],
            reference_evidence=reference_evidence,
            diagnostics=receipt,
        )
    )
