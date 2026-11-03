"""Reference-side evaluation for sealed Gaussian-sum prediction receipts.

Inference never imports this module.  The roof coordinate and all distance
calculations live on this side of the experiment boundary.
"""

from __future__ import annotations

import hashlib
import json
from math import asin, atan2, cos, exp, log, pi, radians, sin, sqrt
from pathlib import Path
from typing import Any, Iterable

import numpy as np


EARTH_RADIUS_KM = 6371.0088
CHI2_2D_95 = 5.991464547107979


def canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _latlon_from_enu(center: tuple[float, float], east_km: float, north_km: float) -> tuple[float, float]:
    lat1, lon1 = map(radians, center)
    distance = sqrt(east_km**2 + north_km**2)
    if distance == 0:
        return center
    bearing = atan2(east_km, north_km)
    angular = distance / EARTH_RADIUS_KM
    lat2 = asin(sin(lat1) * cos(angular) + cos(lat1) * sin(angular) * cos(bearing))
    lon2 = lon1 + atan2(sin(bearing) * sin(angular) * cos(lat1), cos(angular) - sin(lat1) * sin(lat2))
    return np.degrees(lat2), ((np.degrees(lon2) + 180) % 360) - 180


def great_circle_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(min(1.0, sqrt(h)))


def _enu_from_latlon(center: tuple[float, float], point: tuple[float, float]) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(radians, (*center, *point))
    distance = great_circle_km(center, point)
    bearing = atan2(sin(lon2 - lon1) * cos(lat2),
                    cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1))
    return np.array([distance * sin(bearing), distance * cos(bearing)])


def _location_components(receipt: dict[str, Any]) -> list[tuple[float, np.ndarray, np.ndarray, tuple[str, ...]]]:
    result = []
    for item in receipt.get("components", []):
        mean = np.asarray(item["mean"], dtype=float)
        covariance = np.asarray(item["covariance"], dtype=float)
        if mean.size < 2 or covariance.shape[0] < 2 or covariance.shape[1] < 2:
            raise ValueError("component does not contain east/north location dimensions")
        location_covariance = covariance[:2, :2]
        weight = float(item["weight"])
        if not np.isfinite(weight) or weight <= 0:
            raise ValueError("component weight must be finite and positive")
        if not np.all(np.isfinite(mean[:2])) or not np.all(np.isfinite(location_covariance)):
            raise ValueError("location marginal must be finite")
        np.linalg.cholesky(location_covariance)
        result.append((weight, mean[:2], location_covariance, tuple(item.get("identity_history", ()))))
    if not result:
        raise ValueError("successful receipt contains no posterior components")
    total = sum(item[0] for item in result)
    if not np.isclose(total, 1.0, rtol=1e-9, atol=1e-12):
        raise ValueError("component weights must sum to one")
    return result


def mixture_density(points: np.ndarray, components: Iterable[tuple[float, np.ndarray, np.ndarray, tuple[str, ...]]]) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    density = np.zeros(points.shape[:-1], dtype=float)
    for weight, mean, covariance, _ in components:
        delta = points - mean
        solved = np.linalg.solve(covariance, delta.reshape(-1, 2).T).T.reshape(delta.shape)
        exponent = np.einsum("...i,...i->...", delta, solved)
        density += weight * np.exp(-.5 * exponent) / (2 * pi * sqrt(float(np.linalg.det(covariance))))
    return density


def hpd_grid(components, probability: float = .9, resolution: int = 241) -> dict[str, float]:
    """Approximate full-mixture HPD region, including disconnected modes."""
    if not 0 < probability < 1 or resolution < 31:
        raise ValueError("invalid HPD probability or resolution")
    means = np.stack([item[1] for item in components])
    sigmas = np.stack([np.sqrt(np.diag(item[2])) for item in components])
    lower, upper = (means - 6 * sigmas).min(axis=0), (means + 6 * sigmas).max(axis=0)
    east = np.linspace(lower[0], upper[0], resolution)
    north = np.linspace(lower[1], upper[1], resolution)
    ee, nn = np.meshgrid(east, north, indexing="xy")
    density = mixture_density(np.stack([ee, nn], axis=-1), components)
    cell_area = float((east[1] - east[0]) * (north[1] - north[0]))
    flat = density.ravel()
    order = np.argsort(flat)[::-1]
    total_grid_mass = float(flat.sum() * cell_area)
    if not np.isfinite(total_grid_mass) or total_grid_mass <= 0:
        raise ValueError("grid does not resolve positive finite mixture mass")
    cumulative = np.cumsum(flat[order] * cell_area / total_grid_mass)
    selected = int(np.searchsorted(cumulative, probability, side="left") + 1)
    threshold = float(flat[order[min(selected - 1, len(order) - 1)]])
    return {"probability": probability, "area_km2": selected * cell_area, "density_threshold_per_km2": threshold,
            "captured_mass": float(cumulative[min(selected - 1, len(order) - 1)]),
            "total_grid_mass": total_grid_mass, "grid_mass_error": abs(total_grid_mass - 1.),
            "resolution": resolution, "cell_area_km2": cell_area}


def evaluate_receipt(receipt: dict[str, Any], *, reference_latlon: tuple[float, float],
                     prior_center_latlon: tuple[float, float], grid_resolution: int = 241) -> dict[str, Any]:
    """Evaluate one already-sealed receipt without modifying prediction content."""
    identity = {key: receipt.get(key) for key in ("dataset", "unit_id", "session_id", "arm", "prior_name", "status", "flags")}
    result: dict[str, Any] = {**identity, "prediction_digest": canonical_digest(receipt)}
    accepted = receipt.get("status") in {"ok", "updated", "complete"}
    if not accepted and not receipt.get("components"):
        result.update({"attempted": True, "scored": False, "failure_status": receipt.get("status", "missing")})
        return result
    components = _location_components(receipt)
    top = min(enumerate(components), key=lambda pair: (-pair[1][0], pair[0]))[1]
    predicted_latlon = _latlon_from_enu(prior_center_latlon, *top[1])
    mixture_mean = sum(weight * mean for weight, mean, _, _ in components)
    mixture_mean_latlon = _latlon_from_enu(prior_center_latlon, *mixture_mean)
    reference_enu = _enu_from_latlon(prior_center_latlon, reference_latlon)
    delta = reference_enu - top[1]
    conditional_d2 = float(delta @ np.linalg.solve(top[2], delta))
    hpd = hpd_grid(components, resolution=grid_resolution)
    finer = hpd_grid(components, resolution=2 * grid_resolution - 1)
    ref_density = float(mixture_density(reference_enu[None, :], components)[0])
    result.update({
        "attempted": True, "scored": accepted, "diagnostic_scored": not accepted,
        "highest_mass_component_weight": top[0], "point_latlon": list(predicted_latlon),
        "reference_error_km": great_circle_km(predicted_latlon, reference_latlon),
        "mixture_mean_enu_km": mixture_mean.tolist(),
        "mixture_mean_point_latlon": list(mixture_mean_latlon),
        "mixture_mean_reference_error_km": great_circle_km(mixture_mean_latlon, reference_latlon),
        "configured_center_reference_error_km": great_circle_km(prior_center_latlon, reference_latlon),
        "mode_horizontal95_ellipse_area_km2": pi * CHI2_2D_95 * sqrt(float(np.linalg.det(top[2]))),
        "reference_in_mode_horizontal95_ellipse": conditional_d2 <= CHI2_2D_95,
        "mode_reference_mahalanobis2": conditional_d2,
        "mixture_reference_density_per_km2": ref_density,
        "mixture_reference_in_approx_90_hpd": ref_density >= hpd["density_threshold_per_km2"],
        "mixture_90_hpd": hpd,
        "grid_convergence": {"fine_resolution": finer["resolution"], "fine_area_km2": finer["area_km2"],
                             "relative_area_change": abs(finer["area_km2"] - hpd["area_km2"]) / finer["area_km2"]},
    })
    if not accepted:
        result["failure_status"] = receipt.get("status", "missing")
        result["diagnostic_warning"] = "partial failed-run posterior; not accepted for scientific scoring"
    return result


def evaluate_attempts(receipts: Iterable[dict[str, Any]], *, reference_latlon: tuple[float, float],
                      prior_centers: dict[str, tuple[float, float]], grid_resolution: int = 241) -> dict[str, Any]:
    rows = [evaluate_receipt(receipt, reference_latlon=reference_latlon,
                             prior_center_latlon=prior_centers[receipt["prior_name"]],
                             grid_resolution=grid_resolution) for receipt in receipts]
    controls = {(row["dataset"], row["unit_id"], row["prior_name"]): row for row in rows if row["arm"] == "prior_only" and row["scored"]}
    for row in rows:
        control = controls.get((row["dataset"], row["unit_id"], row["prior_name"]))
        row["prior_only_mode_error_km"] = control["reference_error_km"] if control else None
        row["prior_only_error_km"] = control["mixture_mean_reference_error_km"] if control else None
        row["error_change_vs_prior_km"] = row.get("reference_error_km", np.nan) - control["mixture_mean_reference_error_km"] if row["scored"] and control else None
    return {"attempt_count": len(rows), "scored_count": sum(row["scored"] for row in rows), "attempts": rows}


def load_sealed_receipt(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"receipt checksum mismatch: expected {expected_sha256}, got {actual}")
    return json.loads(raw)
