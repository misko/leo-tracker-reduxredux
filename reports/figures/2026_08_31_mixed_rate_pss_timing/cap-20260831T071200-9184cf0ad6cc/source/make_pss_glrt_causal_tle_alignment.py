from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset

ROOT = Path(__file__).resolve().parents[5]
OUTPUT = Path(__file__).resolve().parents[1]
CAPTURE_ID = "cap-20260831T071200-9184cf0ad6cc"
MANIFEST = Path("/srv/bulk/leo/recordings/2026/08/31") / CAPTURE_ID / "manifest.json"
MEASUREMENTS = (
    ROOT
    / "reports/figures/2026_08_31_mixed_rate_pss_timing"
    / CAPTURE_ID
    / "pss-vs-glrt-global-fit-residuals.json"
)
TLE = Path(
    "/mnt/qnap01/mouse9911/tle/raw/space-track/"
    "22b3616a4fc239761afedeaf7f12c62abc9dbb3808c620c0796a770e84f44b4b.tle"
)
FIRST_SAMPLE_UTC_NS = 1_788_160_324_963_802_026
PSS_RF_HZ = 10_825_117_187.5
GLRT_RF_HZ = 10_940_312_500.0
SAMPLE_RATE_HZ = 15_000_000.0
SITE_NAME = "spinnaker-sausalito"
TRAIN_FRACTION = 0.60
FINE_SPACING_S = 0.005
COARSE_POINT_COUNT = 31


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def iso_utc(utc_ns: int) -> str:
    seconds, nanoseconds = divmod(utc_ns, 1_000_000_000)
    stamp = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{nanoseconds:09d}Z"


def sampling_grid(relative_s: np.ndarray) -> SamplingGrid:
    instants = tuple(FIRST_SAMPLE_UTC_NS + round(float(value) * 1e9) for value in relative_s)
    return SamplingGrid(
        utc_ns=instants,
        anchor_index=len(instants) // 2,
        spacing_s=float(np.median(np.diff(relative_s))),
    )


def design(time_s: np.ndarray, degree: int) -> np.ndarray:
    return np.column_stack(tuple(time_s**power for power in range(degree + 1)))


def fit_nuisance(
    observed: np.ndarray,
    predicted: np.ndarray,
    time_s: np.ndarray,
    degree: int,
    train_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    selected = np.ones(observed.size, dtype=bool) if train_mask is None else train_mask
    matrix = design(time_s, degree)
    coefficients = np.linalg.lstsq(matrix[selected], (observed - predicted)[selected], rcond=None)[
        0
    ]
    fitted = predicted + matrix @ coefficients
    return coefficients, fitted, observed - fitted


def holdout(
    observed: np.ndarray,
    predicted: np.ndarray,
    time_s: np.ndarray,
    degree: int,
) -> dict[str, object]:
    count = observed.size
    training_count = math.ceil(TRAIN_FRACTION * count)
    indexes = np.arange(count)
    folds: list[dict[str, object]] = []
    for label, training, evaluation in (
        ("forward", indexes < training_count, indexes >= training_count),
        ("reverse", indexes >= count - training_count, indexes < count - training_count),
    ):
        coefficients, _, residual = fit_nuisance(observed, predicted, time_s, degree, training)
        folds.append(
            {
                "label": label,
                "training_count": int(np.count_nonzero(training)),
                "evaluation_count": int(np.count_nonzero(evaluation)),
                "nuisance_coefficients_ascending": coefficients.tolist(),
                "evaluation_rms": float(np.sqrt(np.mean(np.square(residual[evaluation])))),
            }
        )
    rms = float(np.sqrt(np.mean([float(item["evaluation_rms"]) ** 2 for item in folds])))
    return {"rms": rms, "folds": folds}


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def main() -> None:
    source = json.loads(MEASUREMENTS.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stream = next(item for item in manifest["streams"] if item["stream_id"] == "stream-1")
    assert stream["timing"]["first_sample"]["estimate_utc_ns"] == FIRST_SAMPLE_UTC_NS

    pss_time = np.asarray([row["time_s"] for row in source["pss_rows"]], dtype=float)
    pss_observed = np.asarray(
        [row["frame_phase_samples"] for row in source["pss_rows"]], dtype=float
    )
    glrt_time = np.asarray([row["time_s"] for row in source["glrt_segment_rows"]], dtype=float)
    glrt_observed = np.asarray([row["cfo_hz"] for row in source["glrt_segment_rows"]], dtype=float)
    analysis_stop_s = float(max(pss_time.max(), glrt_time.max()))

    catalogue = parse_element_sets(TLE.read_text(encoding="ascii"))
    element_epoch_ns = np.asarray(catalogue.element_epoch_utc_ns(), dtype=np.int64)
    coarse_time = np.linspace(0.0, analysis_stop_s, COARSE_POINT_COUNT)
    coarse_grid = sampling_grid(coarse_time)
    coarse_tracks = observe_grid(
        propagate_grid(catalogue, coarse_grid), resolve_preset(SITE_NAME), coarse_grid
    )
    margin_deg = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    causal = element_epoch_ns <= FIRST_SAMPLE_UTC_NS
    plausible = (
        coarse_tracks.usable
        & causal
        & (np.min(coarse_tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    )
    coarse_candidates = np.flatnonzero(
        plausible & (np.max(coarse_tracks.elevation_deg, axis=1) > -margin_deg)
    )

    fine_stop_s = analysis_stop_s + 2.0 * FINE_SPACING_S
    fine_count = int(math.ceil(fine_stop_s / FINE_SPACING_S)) + 1
    fine_time = np.linspace(0.0, fine_stop_s, fine_count)
    fine_grid = sampling_grid(fine_time)
    candidate_tracks = observe_grid(
        propagate_grid(catalogue, fine_grid, coarse_candidates.tolist()),
        resolve_preset(SITE_NAME),
        fine_grid,
    )
    actual = fine_time <= analysis_stop_s
    fine_plausible = candidate_tracks.usable & (
        np.min(candidate_tracks.altitude_km[:, actual], axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    visible_rows = np.flatnonzero(
        fine_plausible & (np.max(candidate_tracks.elevation_deg[:, actual], axis=1) > 0.0)
    )
    visible_indices = coarse_candidates[visible_rows]

    pss_null = holdout(pss_observed, np.zeros_like(pss_observed), pss_time, degree=1)
    glrt_null = holdout(glrt_observed, np.zeros_like(glrt_observed), glrt_time, degree=0)
    _, pss_null_fitted, pss_null_residual = fit_nuisance(
        pss_observed, np.zeros_like(pss_observed), pss_time, degree=1
    )
    _, glrt_null_fitted, glrt_null_residual = fit_nuisance(
        glrt_observed, np.zeros_like(glrt_observed), glrt_time, degree=0
    )

    candidates: list[dict[str, object]] = []
    curves: dict[int, dict[str, np.ndarray]] = {}
    for track_row, catalogue_index in zip(visible_rows, visible_indices, strict=True):
        pss_doppler = np.asarray(
            doppler_shift_hz(PSS_RF_HZ, candidate_tracks.range_rate_km_s[track_row]),
            dtype=float,
        )
        glrt_doppler = np.asarray(
            doppler_shift_hz(GLRT_RF_HZ, candidate_tracks.range_rate_km_s[track_row]),
            dtype=float,
        )
        integrated = np.zeros(fine_time.size, dtype=float)
        integrated[1:] = np.cumsum(
            0.5 * (pss_doppler[:-1] + pss_doppler[1:]) * np.diff(fine_time)
        ) / (PSS_RF_HZ / SAMPLE_RATE_HZ)

        # Positive frame epoch is a later observed arrival. The conventional
        # received-minus-transmitted physical Doppler mapping therefore has a minus sign.
        pss_physical = np.interp(pss_time, fine_time, -integrated)
        # This sensitivity is the repository same-sign comparison used in the prior report.
        pss_same_sign = np.interp(pss_time, fine_time, integrated)
        glrt_physical = np.interp(glrt_time, fine_time, glrt_doppler)

        physical_coefficients, physical_fitted, physical_residual = fit_nuisance(
            pss_observed, pss_physical, pss_time, degree=1
        )
        same_coefficients, same_fitted, same_residual = fit_nuisance(
            pss_observed, pss_same_sign, pss_time, degree=1
        )
        glrt_coefficients, glrt_fitted, glrt_residual = fit_nuisance(
            glrt_observed, glrt_physical, glrt_time, degree=0
        )
        physical_holdout = holdout(pss_observed, pss_physical, pss_time, degree=1)
        same_holdout = holdout(pss_observed, pss_same_sign, pss_time, degree=1)
        glrt_holdout = holdout(glrt_observed, glrt_physical, glrt_time, degree=0)

        center = int(np.argmin(np.abs(fine_time - analysis_stop_s / 2.0)))
        doppler_rate = np.gradient(glrt_doppler, fine_time)
        norad = int(catalogue.satellite_numbers[int(catalogue_index)])
        row: dict[str, object] = {
            "norad_id": norad,
            "object_name": catalogue.names[int(catalogue_index)],
            "catalogue_index": int(catalogue_index),
            "element_epoch_utc_ns": int(element_epoch_ns[int(catalogue_index)]),
            "element_epoch_utc": iso_utc(int(element_epoch_ns[int(catalogue_index)])),
            "element_age_at_first_sample_h": float(
                (FIRST_SAMPLE_UTC_NS - element_epoch_ns[int(catalogue_index)]) / 3.6e12
            ),
            "minimum_elevation_deg": float(
                np.min(candidate_tracks.elevation_deg[track_row, actual])
            ),
            "maximum_elevation_deg": float(
                np.max(candidate_tracks.elevation_deg[track_row, actual])
            ),
            "midpoint_azimuth_deg": float(candidate_tracks.azimuth_deg[track_row, center]),
            "midpoint_elevation_deg": float(candidate_tracks.elevation_deg[track_row, center]),
            "midpoint_range_km": float(candidate_tracks.range_km[track_row, center]),
            "midpoint_range_rate_km_s": float(candidate_tracks.range_rate_km_s[track_row, center]),
            "midpoint_glrt_doppler_hz": float(glrt_doppler[center]),
            "midpoint_glrt_doppler_rate_hz_s": float(doppler_rate[center]),
            "pss_physical_delay": {
                "full_nuisance_coefficients_ascending_samples": physical_coefficients.tolist(),
                "full_rms_samples": rms(physical_residual),
                "bidirectional_holdout": physical_holdout,
                "holdout_mse_improvement_over_affine_null": float(
                    1.0 - (float(physical_holdout["rms"]) / float(pss_null["rms"])) ** 2
                ),
            },
            "pss_same_sign_sensitivity": {
                "full_nuisance_coefficients_ascending_samples": same_coefficients.tolist(),
                "full_rms_samples": rms(same_residual),
                "bidirectional_holdout": same_holdout,
                "holdout_mse_improvement_over_affine_null": float(
                    1.0 - (float(same_holdout["rms"]) / float(pss_null["rms"])) ** 2
                ),
            },
            "glrt_physical_doppler": {
                "full_constant_cfo_offset_hz": float(glrt_coefficients[0]),
                "full_rms_hz": rms(glrt_residual),
                "bidirectional_holdout": glrt_holdout,
                "holdout_mse_improvement_over_constant_null": float(
                    1.0 - (float(glrt_holdout["rms"]) / float(glrt_null["rms"])) ** 2
                ),
            },
        }
        candidates.append(row)
        curves[norad] = {
            "pss_physical_fitted": physical_fitted,
            "pss_physical_residual": physical_residual,
            "pss_same_fitted": same_fitted,
            "pss_same_residual": same_residual,
            "glrt_fitted": glrt_fitted,
            "glrt_residual": glrt_residual,
        }

    pss_physical_ranked = sorted(
        candidates,
        key=lambda row: float(
            row["pss_physical_delay"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ),
    )
    pss_same_ranked = sorted(
        candidates,
        key=lambda row: float(
            row["pss_same_sign_sensitivity"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ),
    )
    glrt_ranked = sorted(
        candidates,
        key=lambda row: float(
            row["glrt_physical_doppler"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ),
    )
    for rank_name, ranked in (
        ("pss_physical_delay_rank", pss_physical_ranked),
        ("pss_same_sign_rank", pss_same_ranked),
        ("glrt_physical_doppler_rank", glrt_ranked),
    ):
        for rank_index, row in enumerate(ranked, start=1):
            row[rank_name] = rank_index

    for row in candidates:
        pss_ratio = float(
            row["pss_same_sign_sensitivity"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ) / float(pss_null["rms"])
        glrt_ratio = float(
            row["glrt_physical_doppler"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ) / float(glrt_null["rms"])
        row["same_sign_joint_normalized_score"] = pss_ratio**2 + glrt_ratio**2
    joint_ranked = sorted(
        candidates, key=lambda row: float(row["same_sign_joint_normalized_score"])
    )
    for rank_index, row in enumerate(joint_ranked, start=1):
        row["same_sign_joint_rank"] = rank_index

    physical_best = pss_physical_ranked[0]
    same_best = pss_same_ranked[0]
    glrt_best = glrt_ranked[0]
    joint_best = joint_ranked[0]

    alignment_png = OUTPUT / "071200-pss-glrt-tle-alignment.png"
    render_alignment(
        alignment_png,
        pss_time,
        pss_observed,
        glrt_time,
        glrt_observed,
        physical_best,
        same_best,
        glrt_best,
        curves,
    )
    ranking_png = OUTPUT / "071200-tle-candidate-ranking.png"
    render_ranking(
        ranking_png,
        candidates,
        pss_physical_ranked,
        pss_same_ranked,
        glrt_ranked,
        pss_null,
        glrt_null,
        same_best,
        glrt_best,
        joint_best,
    )

    candidates.sort(key=lambda row: int(row["glrt_physical_doppler_rank"]))
    tle_stat = TLE.stat()
    evidence = {
        "schema_version": 1,
        "analysis_kind": "candidate-only-fixed-time-pss-glrt-causal-tle-alignment",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "candidate_only": True,
        "capture_id": CAPTURE_ID,
        "inputs": {
            "capture_manifest_path": str(MANIFEST),
            "capture_manifest_sha256": f"sha256:{sha256(MANIFEST)}",
            "measurement_source_path": str(MEASUREMENTS.relative_to(ROOT)),
            "measurement_source_sha256": f"sha256:{sha256(MEASUREMENTS)}",
            "tle_path": str(TLE),
            "tle_sha256": f"sha256:{sha256(TLE)}",
            "tle_provider": "Space-Track GP 3LE",
            "tle_collection_time_authority": (
                "source filesystem mtime; legacy raw filename has a digest but no timestamp"
            ),
            "tle_collection_utc_ns": tle_stat.st_mtime_ns,
            "tle_collection_utc": iso_utc(tle_stat.st_mtime_ns),
            "tle_collection_age_at_first_sample_s": float(
                (FIRST_SAMPLE_UTC_NS - tle_stat.st_mtime_ns) / 1e9
            ),
            "stream_first_sample_estimate_utc_ns": FIRST_SAMPLE_UTC_NS,
            "stream_first_sample_estimate_utc": iso_utc(FIRST_SAMPLE_UTC_NS),
            "stream_first_sample_earliest_utc_ns": stream["timing"]["first_sample"][
                "earliest_utc_ns"
            ],
            "stream_first_sample_latest_utc_ns": stream["timing"]["first_sample"]["latest_utc_ns"],
            "analysis_stop_s": analysis_stop_s,
            "pss_rf_reference_hz": PSS_RF_HZ,
            "glrt_rf_reference_hz": GLRT_RF_HZ,
            "sample_rate_hz": SAMPLE_RATE_HZ,
        },
        "observer": {
            **resolve_preset(SITE_NAME).model_dump(mode="json"),
            "capture_bound": False,
            "antenna_boresight_known": False,
        },
        "method": {
            "time_shift_s": 0.0,
            "scale_fitted": False,
            "slope_or_curvature_fitted_to_tle": False,
            "catalogue_filter": (
                "element epoch no later than first sample, propagation usable, plausible "
                "altitude, above geometric horizon at an actual-time fine knot"
            ),
            "glrt_model": ("observed_CFO(t) = physical_TLE_Doppler(t) + constant_CFO_offset"),
            "pss_physical_delay_model": (
                "observed_epoch(t) = -integral(physical_TLE_Doppler)/(fRF/fs) "
                "+ constant_epoch + constant_epoch_rate*t"
            ),
            "pss_same_sign_sensitivity_model": (
                "observed_epoch(t) = +integral(physical_TLE_Doppler)/(fRF/fs) "
                "+ constant_epoch + constant_epoch_rate*t; diagnostic only"
            ),
            "glrt_nuisance_parameters": ["constant_CFO_offset_hz"],
            "pss_nuisance_parameters": [
                "constant_epoch_samples",
                "constant_epoch_rate_samples_s",
            ],
            "training_fraction": TRAIN_FRACTION,
            "holdout": (
                "first 60% fits nuisance and predicts last 40%, then last 60% fits "
                "nuisance and predicts first 40%"
            ),
            "ranking_metric": "quadratic mean of forward and reverse holdout RMS",
            "fine_propagation_spacing_s": float(fine_grid.spacing_s),
            "coarse_candidate_spacing_s": float(coarse_grid.spacing_s),
            "coarse_horizon_margin_deg": float(margin_deg),
        },
        "accounting": {
            "catalogue_element_count": len(catalogue),
            "future_element_epoch_excluded_count": int(np.count_nonzero(~causal)),
            "coarse_candidate_count": int(coarse_candidates.size),
            "fixed_time_horizon_visible_candidate_count": len(candidates),
            "peak_elevation_at_least_10_deg_count": int(
                np.count_nonzero(
                    [float(row["maximum_elevation_deg"]) >= 10.0 for row in candidates]
                )
            ),
            "pss_block_median_count": int(pss_time.size),
            "glrt_segment_median_count": int(glrt_time.size),
        },
        "nulls": {
            "pss_affine": {
                "full_rms_samples": rms(pss_null_residual),
                "bidirectional_holdout": pss_null,
                "full_fitted_samples": pss_null_fitted.tolist(),
            },
            "glrt_constant": {
                "full_rms_hz": rms(glrt_null_residual),
                "bidirectional_holdout": glrt_null,
                "full_fitted_hz": glrt_null_fitted.tolist(),
            },
        },
        "headline": {
            "glrt_physical_best": glrt_best,
            "pss_physical_delay_best": physical_best,
            "pss_same_sign_sensitivity_best": same_best,
            "same_sign_joint_best": joint_best,
            "cross_ranks": {
                "glrt_best_pss_physical_rank": glrt_best["pss_physical_delay_rank"],
                "glrt_best_pss_same_sign_rank": glrt_best["pss_same_sign_rank"],
                "pss_physical_best_glrt_rank": physical_best["glrt_physical_doppler_rank"],
                "pss_same_sign_best_glrt_rank": same_best["glrt_physical_doppler_rank"],
            },
        },
        "candidates": candidates,
        "limitations": [
            "The observer is a reviewed site preset, not capture-bound GPS authority.",
            "The antenna boresight and gain pattern are unknown.",
            "The legacy raw TLE path records collection time only through its mtime.",
            "A 7.03 s catalogue ranking cannot identify a satellite.",
            "PSS and GLRT use the same IQ and are not statistically independent.",
            "The PSS frame epoch is template/channel-relative and clock-confounded.",
            "The same-sign PSS sensitivity is not a physical arrival-delay model.",
            "No time shift, Doppler scale, slope, or curvature was fitted.",
        ],
        "artifacts": {
            "alignment_png": {
                "path": alignment_png.name,
                "sha256": f"sha256:{sha256(alignment_png)}",
            },
            "ranking_png": {
                "path": ranking_png.name,
                "sha256": f"sha256:{sha256(ranking_png)}",
            },
        },
    }
    evidence_path = OUTPUT / "071200-pss-glrt-tle-alignment.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "tle_age_s": evidence["inputs"]["tle_collection_age_at_first_sample_s"],
                "glrt_best": summary(glrt_best, "glrt_physical_doppler"),
                "pss_physical_best": summary(physical_best, "pss_physical_delay"),
                "pss_same_sign_best": summary(same_best, "pss_same_sign_sensitivity"),
                "cross_ranks": evidence["headline"]["cross_ranks"],
                "output": str(OUTPUT),
            },
            indent=2,
        )
    )


def summary(row: dict[str, object], field: str) -> dict[str, object]:
    result = row[field]  # type: ignore[assignment]
    return {
        "norad_id": row["norad_id"],
        "object_name": row["object_name"],
        "maximum_elevation_deg": row["maximum_elevation_deg"],
        "midpoint_doppler_rate_hz_s": row["midpoint_glrt_doppler_rate_hz_s"],
        "holdout_rms": result["bidirectional_holdout"]["rms"],  # type: ignore[index]
        "full_rms": result.get("full_rms_hz", result.get("full_rms_samples")),  # type: ignore[union-attr]
    }


def render_alignment(
    output: Path,
    pss_time: np.ndarray,
    pss_observed: np.ndarray,
    glrt_time: np.ndarray,
    glrt_observed: np.ndarray,
    physical_best: dict[str, object],
    same_best: dict[str, object],
    glrt_best: dict[str, object],
    curves: dict[int, dict[str, np.ndarray]],
) -> None:
    fig, axes = plt.subplots(3, 2, figsize=(15, 13), constrained_layout=True)
    panels = (
        (
            "GLRT physical CFO",
            glrt_time,
            glrt_observed,
            glrt_best,
            "glrt_fitted",
            "glrt_residual",
            "Hz",
        ),
        (
            "PSS physical arrival-delay sign",
            pss_time,
            pss_observed,
            physical_best,
            "pss_physical_fitted",
            "pss_physical_residual",
            "samples",
        ),
        (
            "PSS repository same-sign sensitivity",
            pss_time,
            pss_observed,
            same_best,
            "pss_same_fitted",
            "pss_same_residual",
            "samples",
        ),
    )
    for panel, (title, times, observed, candidate, fit_key, residual_key, unit) in enumerate(
        panels
    ):
        norad = int(candidate["norad_id"])
        values = curves[norad]
        order = np.argsort(times)
        ax = axes[panel, 0]
        ax.scatter(times, observed, s=30, color="#1f2937", zorder=3, label="observed")
        ax.plot(
            times[order],
            values[fit_key][order],
            color="#d97706",
            linewidth=2.2,
            label="fixed-time TLE + allowed nuisance",
        )
        ax.set_title(f"{title}: {candidate['object_name']} / {candidate['norad_id']}", loc="left")
        ax.set_xlabel("Seconds from RX1 first sample")
        ax.set_ylabel(f"Observed coordinate ({unit})")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9)
        ax = axes[panel, 1]
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.scatter(times, values[residual_key], s=30, color="#2563eb")
        ax.set_title("Full-data descriptive residual", loc="left")
        ax.set_xlabel("Seconds from RX1 first sample")
        ax.set_ylabel(f"Observed - aligned TLE ({unit})")
        ax.grid(alpha=0.25)
    fig.suptitle(
        "071200 fixed-time causal-TLE alignment\n"
        "physical GLRT closes; PSS closes only under the same-sign sensitivity",
        fontsize=16,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


def render_ranking(
    output: Path,
    candidates: list[dict[str, object]],
    physical_ranked: list[dict[str, object]],
    same_ranked: list[dict[str, object]],
    glrt_ranked: list[dict[str, object]],
    pss_null: dict[str, object],
    glrt_null: dict[str, object],
    same_best: dict[str, object],
    glrt_best: dict[str, object],
    joint_best: dict[str, object],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    specs = (
        (
            axes[0, 0],
            glrt_ranked,
            "glrt_physical_doppler",
            float(glrt_null["rms"]),
            "GLRT physical Doppler",
            "Hz",
            "glrt_physical_doppler_rank",
        ),
        (
            axes[0, 1],
            physical_ranked,
            "pss_physical_delay",
            float(pss_null["rms"]),
            "PSS physical arrival-delay sign",
            "samples",
            "pss_physical_delay_rank",
        ),
        (
            axes[1, 0],
            same_ranked,
            "pss_same_sign_sensitivity",
            float(pss_null["rms"]),
            "PSS same-sign sensitivity",
            "samples",
            "pss_same_sign_rank",
        ),
    )
    for ax, ranked, field, null_rms, title, unit, rank_field in specs:
        values = np.asarray(
            [float(row[field]["bidirectional_holdout"]["rms"]) for row in ranked]  # type: ignore[index]
        )
        ax.scatter(np.arange(1, values.size + 1), values, s=11, color="0.55", alpha=0.65)
        ax.axhline(
            null_rms,
            color="#dc2626",
            linestyle="--",
            linewidth=1.5,
            label="same-nuisance null",
        )
        for candidate, color, label in (
            (glrt_best, "#2563eb", f"GLRT best {glrt_best['norad_id']}"),
            (same_best, "#d97706", f"PSS same-sign best {same_best['norad_id']}"),
        ):
            rank_value = int(candidate[rank_field])
            value = float(candidate[field]["bidirectional_holdout"]["rms"])  # type: ignore[index]
            ax.scatter(
                rank_value,
                value,
                s=65,
                color=color,
                edgecolor="white",
                linewidth=0.8,
                zorder=4,
                label=label,
            )
        ax.set_title(title, loc="left")
        ax.set_xlabel("Rank among fixed-time horizon-visible TLEs")
        ax.set_ylabel(f"Bidirectional holdout RMS ({unit})")
        ax.set_yscale("log")
        ax.grid(alpha=0.25, which="both")
        ax.legend(fontsize=8)

    ax = axes[1, 1]
    pss_ratio = np.asarray(
        [
            float(row["pss_same_sign_sensitivity"]["bidirectional_holdout"]["rms"])  # type: ignore[index]
            / float(pss_null["rms"])
            for row in candidates
        ]
    )
    glrt_ratio = np.asarray(
        [
            float(row["glrt_physical_doppler"]["bidirectional_holdout"]["rms"])  # type: ignore[index]
            / float(glrt_null["rms"])
            for row in candidates
        ]
    )
    elevation = np.asarray([float(row["maximum_elevation_deg"]) for row in candidates])
    scatter = ax.scatter(glrt_ratio, pss_ratio, c=elevation, s=20, cmap="viridis", alpha=0.75)
    for candidate, color, label in (
        (joint_best, "#dc2626", f"joint best {joint_best['norad_id']}"),
        (glrt_best, "#2563eb", f"GLRT best {glrt_best['norad_id']}"),
    ):
        x_value = float(
            candidate["glrt_physical_doppler"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ) / float(glrt_null["rms"])
        y_value = float(
            candidate["pss_same_sign_sensitivity"]["bidirectional_holdout"]["rms"]  # type: ignore[index]
        ) / float(pss_null["rms"])
        ax.scatter(
            x_value,
            y_value,
            s=85,
            color=color,
            edgecolor="white",
            linewidth=1.0,
            zorder=4,
            label=label,
        )
    ax.axvline(1.0, color="0.3", linestyle="--", linewidth=1.0)
    ax.axhline(1.0, color="0.3", linestyle="--", linewidth=1.0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("Cross-observable same-sign sensitivity", loc="left")
    ax.set_xlabel("GLRT holdout RMS / constant-null RMS")
    ax.set_ylabel("PSS holdout RMS / affine-null RMS")
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8)
    fig.colorbar(scatter, ax=ax, label="Peak elevation (deg)")
    fig.suptitle(
        "Causal TLE catalogue ranking at fixed capture time and conditional Sausalito site",
        fontsize=16,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
