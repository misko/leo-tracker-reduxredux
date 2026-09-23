#!/usr/bin/env python3
"""Compare repository TEME/ECEF Doppler with Astropy TEME/ITRS."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
import warnings
from collections import Counter
from pathlib import Path

import astropy
import astropy.units as u
import astropy_iers_data
import erfa
import numpy as np
import sgp4
from astropy.coordinates import ITRS, TEME, CartesianDifferential, CartesianRepresentation
from astropy.time import Time
from astropy.utils import iers

from leo.analysis.adaptive_tle_prediction import LIGHT_KM_S, REFERENCE_RF_HZ
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import find_element_set_record, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid

AUDIT_RECEIVER = (38.0, -122.0, 0.0)
FINITE_DIFFERENCE_HALF_WIDTH_NS = 100_000_000


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def distribution(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    if not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("finite nonempty metric vector required")
    absolute = np.abs(values)
    return {
        "count": int(len(values)),
        "mean": float(np.mean(values)),
        "rms": float(np.sqrt(np.mean(values**2))),
        "median_absolute": float(np.median(absolute)),
        "p90_absolute": float(np.percentile(absolute, 90)),
        "p99_absolute": float(np.percentile(absolute, 99)),
        "max_absolute": float(np.max(absolute)),
    }


def time_from_utc_ns(utc_ns: np.ndarray) -> Time:
    values = np.asarray(utc_ns, dtype=np.int64)
    seconds, remainder = np.divmod(values, 1_000_000_000)
    return Time(
        seconds.astype(np.float64),
        remainder.astype(np.float64) / 1e9,
        format="unix",
        scale="utc",
        precision=9,
    )


def astropy_itrs(
    position_teme_km: np.ndarray,
    velocity_teme_km_s: np.ndarray,
    utc_ns: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    representation = CartesianRepresentation(
        np.asarray(position_teme_km).T * u.km,
        differentials=CartesianDifferential(np.asarray(velocity_teme_km_s).T * u.km / u.s),
    )
    instant = time_from_utc_ns(utc_ns)
    transformed = TEME(representation, obstime=instant).transform_to(ITRS(obstime=instant))
    return (
        transformed.cartesian.xyz.to_value(u.km).T,
        transformed.cartesian.differentials["s"].d_xyz.to_value(u.km / u.s).T,
    )


def repo_ecef(
    position_teme_km: np.ndarray,
    velocity_teme_km_s: np.ndarray,
    utc_ns: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    day, fraction = julian_day_from_utc_ns(utc_ns)
    return teme_to_ecef(
        position_teme_km,
        velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(day, fraction),
    )


def doppler(position: np.ndarray, velocity: np.ndarray, receiver: np.ndarray) -> np.ndarray:
    relative = position - receiver
    line_of_sight_rate = np.einsum("ij,ij->i", relative, velocity) / np.linalg.norm(
        relative, axis=1
    )
    return -REFERENCE_RF_HZ / LIGHT_KM_S * line_of_sight_rate


def line_of_sight_rate(position: np.ndarray, velocity: np.ndarray, receiver: np.ndarray):
    relative = position - receiver
    return np.einsum("ij,ij->i", relative, velocity) / np.linalg.norm(relative, axis=1)


def status_name(value: int) -> str:
    names = {
        iers.FROM_IERS_B: "from_iers_b",
        iers.FROM_IERS_A: "from_iers_a",
        iers.FROM_IERS_A_PREDICTION: "from_iers_a_prediction",
        iers.TIME_BEFORE_IERS_RANGE: "before_iers_range",
        iers.TIME_BEYOND_IERS_RANGE: "beyond_iers_range",
    }
    return names.get(int(value), f"unknown_{int(value)}")


def summarize_warnings(caught) -> list[dict]:
    counts = Counter((item.category.__name__, str(item.message)) for item in caught)
    return [
        {"category": category, "message": message, "count": count}
        for (category, message), count in sorted(counts.items())
    ]


def verify_inputs(args):
    manifest = json.loads(args.manifest.read_text())
    material = json.loads(args.identities.read_text())
    sessions = manifest["partitions"]["train"]["session_ids"][:6]
    if len(sessions) != 6 or len(set(sessions)) != 6:
        raise ValueError("exact first-six TRAIN session order required")
    if material["bindings"]["manifest"] != digest(args.manifest):
        raise ValueError("identity receipt manifest binding changed")
    if material["bindings"]["baseline"] != digest(args.baseline):
        raise ValueError("identity receipt baseline binding changed")
    baseline_seal = args.baseline.with_suffix(".sha256").read_text().strip()
    if digest(args.baseline).removeprefix("sha256:") != baseline_seal:
        raise ValueError("baseline results seal mismatch")
    if material["bindings"]["tool"] != digest(args.identity_tool):
        raise ValueError("identity materializer source changed")
    if material["bindings"]["protocol"] != digest(args.identity_protocol):
        raise ValueError("identity materializer protocol changed")
    if material["bindings"]["materialized_npz"] != digest(args.identity_npz):
        raise ValueError("identity materialization changed")
    snapshots = {row["session_id"]: row for row in material["snapshots"]}
    if list(snapshots) != sessions:
        raise ValueError("identity receipt does not bind the exact session order")
    identity_rows = material["selection"]["tracks"]
    identities = {}
    for row in identity_rows:
        key = (row["session_id"], row["track_id"])
        if key in identities or row["session_id"] not in sessions:
            raise ValueError("duplicate or out-of-scope fixed identity")
        identities[key] = str(row["candidate_id"])
    return manifest, material, sessions, snapshots, identities


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    started = time.monotonic()
    manifest, material, sessions, snapshot_bindings, identities = verify_inputs(args)
    archive = TleArchiveReader(args.tle_root)
    available = {(row.digest, row.collected_utc_ns): row for row in archive.list_snapshots()}
    receiver = geodetic_to_ecef_km(*AUDIT_RECEIVER)

    track_rows = []
    base_teme_position = []
    base_teme_velocity = []
    minus_teme_position = []
    minus_teme_velocity = []
    plus_teme_position = []
    plus_teme_velocity = []
    epochs = []
    bindings = []
    tle_records = {}
    observation_offset = 0

    for session_id in sessions:
        directory = args.cache_root / session_id
        receipt_path = directory / "cache_receipt.json"
        cache_path = directory / "state_cache.npz"
        receipt_hash, cache_hash = digest(receipt_path), digest(cache_path)
        expected = snapshot_bindings[session_id]
        if receipt_hash != expected["cache_receipt"] or cache_hash != expected["state_cache"]:
            raise ValueError("cache binding changed")
        receipt = json.loads(receipt_path.read_text())
        if receipt["session_id"] != session_id or receipt["bindings"]["state_cache"] != cache_hash:
            raise ValueError("cache receipt identity or state binding mismatch")
        snapshot_key = (
            receipt["prepared_evidence"]["snapshot_digest"],
            receipt["prepared_evidence"]["snapshot_collected_utc_ns"],
        )
        if snapshot_key not in available:
            raise ValueError("exact causal snapshot is unavailable")
        snapshot = available[snapshot_key]
        if (
            snapshot.digest != expected["snapshot_digest"]
            or snapshot.collected_utc_ns != expected["snapshot_collected_utc_ns"]
            or snapshot.byte_size != expected["snapshot_byte_size"]
        ):
            raise ValueError("snapshot binding changed")
        payload, exclusion = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        candidate_lookup = {
            str(number): index for index, number in enumerate(catalogue.satellite_numbers)
        }
        evidence = [
            row
            for row in receipt["prepared_evidence"]["tracks"]
            if np.ptp(np.asarray(row["times_s"], dtype=float)) >= 3.0
        ]
        evidence_keys = {(session_id, row["track_id"]) for row in evidence}
        selected_keys = {key for key in identities if key[0] == session_id}
        if evidence_keys != selected_keys:
            raise ValueError("fixed identities do not cover exact eligible track support")

        session_candidate_records = {}
        for source in evidence:
            key = (session_id, source["track_id"])
            candidate_id = identities[key]
            if candidate_id not in candidate_lookup:
                raise ValueError("fixed identity absent from exact causal snapshot")
            if candidate_id not in session_candidate_records:
                record = find_element_set_record(payload, int(candidate_id))
                if record is None:
                    raise ValueError("fixed identity textual element set absent")
                session_candidate_records[candidate_id] = bytes_digest(record.text.encode())
                tle_records[(session_id, candidate_id)] = session_candidate_records[candidate_id]
            times = np.asarray(source["times_s"], dtype=float)
            utc_ns = np.asarray(
                [
                    receipt["prepared_evidence"]["start_utc_ns"]
                    + round(float(value) * 1e9)
                    for value in times
                ],
                dtype=np.int64,
            )
            direct_epochs = np.concatenate(
                (
                    utc_ns,
                    utc_ns - FINITE_DIFFERENCE_HALF_WIDTH_NS,
                    utc_ns + FINITE_DIFFERENCE_HALF_WIDTH_NS,
                )
            )
            grid = SamplingGrid(tuple(int(value) for value in direct_epochs), 0, 0.1)
            state = propagate_grid(catalogue, grid, [candidate_lookup[candidate_id]])
            if np.any(state.error_code != 0) or not np.all(np.isfinite(state.position_teme_km)):
                raise ValueError("direct SGP4 failed on selected baseline identity")
            count = len(times)
            base_teme_position.append(state.position_teme_km[0, :count])
            base_teme_velocity.append(state.velocity_teme_km_s[0, :count])
            minus_teme_position.append(state.position_teme_km[0, count : 2 * count])
            minus_teme_velocity.append(state.velocity_teme_km_s[0, count : 2 * count])
            plus_teme_position.append(state.position_teme_km[0, 2 * count :])
            plus_teme_velocity.append(state.velocity_teme_km_s[0, 2 * count :])
            epochs.append(utc_ns)
            track_rows.append(
                {
                    "session_id": session_id,
                    "track_id": source["track_id"],
                    "support_digest": source["support_digest"],
                    "candidate_id": candidate_id,
                    "start": observation_offset,
                    "count": count,
                    "first_utc_ns": int(utc_ns.min()),
                    "last_utc_ns": int(utc_ns.max()),
                }
            )
            observation_offset += count
        bindings.append(
            {
                "session_id": session_id,
                "cache_receipt": receipt_hash,
                "state_cache": cache_hash,
                "snapshot_digest": snapshot.digest,
                "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
                "snapshot_byte_size": snapshot.byte_size,
                "eligible_payload": bytes_digest(payload.encode()),
                "catalogue_count_after_exclusion": len(catalogue),
                "exclusion_receipt": [row.model_dump(mode="json") for row in exclusion],
            }
        )

    if len(track_rows) != len(identities):
        raise ValueError("unused or missing fixed identities")
    epoch = np.concatenate(epochs)
    base_position_teme = np.concatenate(base_teme_position)
    base_velocity_teme = np.concatenate(base_teme_velocity)
    minus_position_teme = np.concatenate(minus_teme_position)
    minus_velocity_teme = np.concatenate(minus_teme_velocity)
    plus_position_teme = np.concatenate(plus_teme_position)
    plus_velocity_teme = np.concatenate(plus_teme_velocity)
    minus_epoch = epoch - FINITE_DIFFERENCE_HALF_WIDTH_NS
    plus_epoch = epoch + FINITE_DIFFERENCE_HALF_WIDTH_NS

    iers.conf.auto_download = False
    iers.conf.auto_max_age = None
    iers.conf.iers_degraded_accuracy = "warn"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        eop = iers.earth_orientation_table.get()
        instant = time_from_utc_ns(epoch)
        dut1, dut1_status = eop.ut1_utc(instant, return_status=True)
        xp, yp, polar_status = eop.pm_xy(instant, return_status=True)
        repo_position, repo_velocity = repo_ecef(
            base_position_teme, base_velocity_teme, epoch
        )
        repo_minus_position, _ = repo_ecef(
            minus_position_teme, minus_velocity_teme, minus_epoch
        )
        repo_plus_position, _ = repo_ecef(plus_position_teme, plus_velocity_teme, plus_epoch)
        astro_position, astro_velocity = astropy_itrs(
            base_position_teme, base_velocity_teme, epoch
        )
        astro_minus_position, _ = astropy_itrs(
            minus_position_teme, minus_velocity_teme, minus_epoch
        )
        astro_plus_position, _ = astropy_itrs(
            plus_position_teme, plus_velocity_teme, plus_epoch
        )

    repo_doppler = doppler(repo_position, repo_velocity, receiver)
    astro_doppler = doppler(astro_position, astro_velocity, receiver)
    raw_doppler_difference = repo_doppler - astro_doppler
    centered_doppler_difference = np.empty_like(raw_doppler_difference)
    per_track = []
    for row in track_rows:
        index = slice(row["start"], row["start"] + row["count"])
        difference = raw_doppler_difference[index]
        centered = difference - np.mean(difference)
        centered_doppler_difference[index] = centered
        per_track.append(
            {
                **{
                    key: row[key]
                    for key in (
                        "session_id",
                        "track_id",
                        "support_digest",
                        "candidate_id",
                        "count",
                        "first_utc_ns",
                        "last_utc_ns",
                    )
                },
                "raw_doppler_mean_difference_hz": float(np.mean(difference)),
                "centered_doppler_rms_difference_hz": float(
                    np.sqrt(np.mean(centered**2))
                ),
                "centered_doppler_max_absolute_difference_hz": float(
                    np.max(np.abs(centered))
                ),
            }
        )

    session_metrics = []
    for session_id in sessions:
        selected = np.concatenate(
            [
                np.arange(row["start"], row["start"] + row["count"])
                for row in track_rows
                if row["session_id"] == session_id
            ]
        )
        session_metrics.append(
            {
                "session_id": session_id,
                "track_count": sum(row["session_id"] == session_id for row in track_rows),
                "observation_count": int(len(selected)),
                "position_norm_difference_m": distribution(
                    1000.0
                    * np.linalg.norm(
                        repo_position[selected] - astro_position[selected], axis=1
                    )
                ),
                "velocity_norm_difference_mm_s": distribution(
                    1e6 * np.linalg.norm(repo_velocity[selected] - astro_velocity[selected], axis=1)
                ),
                "centered_doppler_difference_hz": distribution(
                    centered_doppler_difference[selected]
                ),
            }
        )

    denominator_s = 2.0 * FINITE_DIFFERENCE_HALF_WIDTH_NS / 1e9
    repo_position_rate = (
        np.linalg.norm(repo_plus_position - receiver, axis=1)
        - np.linalg.norm(repo_minus_position - receiver, axis=1)
    ) / denominator_s
    astro_position_rate = (
        np.linalg.norm(astro_plus_position - receiver, axis=1)
        - np.linalg.norm(astro_minus_position - receiver, axis=1)
    ) / denominator_s
    repo_velocity_rate = line_of_sight_rate(repo_position, repo_velocity, receiver)
    astro_velocity_rate = line_of_sight_rate(astro_position, astro_velocity, receiver)

    iers_data_path = Path(eop.meta["data_path"])
    dut1_values = dut1.to_value(u.s)
    xp_values, yp_values = xp.to_value(u.arcsec), yp.to_value(u.arcsec)
    eop_status = Counter(status_name(value) for value in dut1_status)
    polar_status_counts = Counter(status_name(value) for value in polar_status)
    top_tracks = sorted(
        per_track,
        key=lambda row: row["centered_doppler_rms_difference_hz"],
        reverse=True,
    )[:10]
    results = {
        "schema": "long-astropy-doppler-oracle/v1",
        "protocol_frozen_before_execution": True,
        "position_fit_performed": False,
        "measured_frequencies_used": False,
        "training_masks_used": False,
        "reference_position_used": False,
        "validation_or_test_sessions_used": False,
        "audit_receiver": {
            "latitude_deg": AUDIT_RECEIVER[0],
            "longitude_deg": AUDIT_RECEIVER[1],
            "ellipsoidal_altitude_m": AUDIT_RECEIVER[2],
            "role": "arbitrary nontruth numerical probe",
            "ecef_km": receiver.tolist(),
        },
        "support": {
            "session_ids": sessions,
            "track_count": len(track_rows),
            "observation_count": int(len(epoch)),
            "unique_satellite_count": len({row["candidate_id"] for row in track_rows}),
            "first_utc_ns": int(epoch.min()),
            "last_utc_ns": int(epoch.max()),
        },
        "frame_assumptions": {
            "repository": "IAU 1982 GMST with UT1 approximated by UTC; polar motion neglected",
            "astropy": "TEME to ITRS with local IERS Earth-orientation table",
            "astropy_iers_auto_download": False,
            "astropy_iers_auto_max_age": None,
            "finite_difference_half_width_s": FINITE_DIFFERENCE_HALF_WIDTH_NS / 1e9,
            "rounded_utc_epoch_rule": "start_utc_ns + round(times_s * 1e9)",
        },
        "earth_orientation": {
            "table_class": f"{type(eop).__module__}.{type(eop).__name__}",
            "row_count": len(eop),
            "mjd_first": float(eop["MJD"][0].value),
            "mjd_last": float(eop["MJD"][-1].value),
            "predictive_mjd": float(eop.meta.get("predictive_mjd")),
            "data_path": str(iers_data_path),
            "data_sha256": digest(iers_data_path),
            "ut1_minus_utc_s": {
                "minimum": float(np.min(dut1_values)),
                "maximum": float(np.max(dut1_values)),
                "status_counts": dict(sorted(eop_status.items())),
            },
            "polar_motion_arcsec": {
                "x_minimum": float(np.min(xp_values)),
                "x_maximum": float(np.max(xp_values)),
                "y_minimum": float(np.min(yp_values)),
                "y_maximum": float(np.max(yp_values)),
                "status_counts": dict(sorted(polar_status_counts.items())),
            },
            "warnings": summarize_warnings(caught),
        },
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "astropy": astropy.__version__,
            "astropy_iers_data": astropy_iers_data.__version__,
            "pyerfa": erfa.__version__,
            "sgp4": sgp4.__version__,
        },
        "aggregate_metrics": {
            "position_norm_difference_m": distribution(
                1000.0 * np.linalg.norm(repo_position - astro_position, axis=1)
            ),
            "velocity_norm_difference_mm_s": distribution(
                1e6 * np.linalg.norm(repo_velocity - astro_velocity, axis=1)
            ),
            "raw_doppler_difference_hz": distribution(raw_doppler_difference),
            "centered_doppler_difference_hz": distribution(centered_doppler_difference),
            "repository_velocity_minus_position_derivative_mm_s": distribution(
                1e6 * (repo_velocity_rate - repo_position_rate)
            ),
            "astropy_velocity_minus_position_derivative_mm_s": distribution(
                1e6 * (astro_velocity_rate - astro_position_rate)
            ),
        },
        "session_metrics": session_metrics,
        "worst_tracks_by_centered_doppler_rms": top_tracks,
        "tracks": per_track,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "manifest": digest(args.manifest),
            "baseline_results_bytes_only": digest(args.baseline),
            "identity_receipt": digest(args.identities),
            "identity_tool": digest(args.identity_tool),
            "identity_protocol": digest(args.identity_protocol),
            "identity_npz": digest(args.identity_npz),
            "protocol": digest(Path(__file__).with_name("PROTOCOL.md")),
            "tool": digest(Path(__file__)),
            "repository_frames": digest(args.repository_frames),
            "repository_propagation": digest(args.repository_propagation),
            "repository_prediction": digest(args.repository_prediction),
            "caches_and_snapshots": bindings,
            "tle_records": [
                {
                    "session_id": session_id,
                    "candidate_id": candidate_id,
                    "element_set": value,
                }
                for (session_id, candidate_id), value in sorted(tle_records.items())
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(results, indent=2, sort_keys=True) + "\n"
    args.output.write_text(raw)
    args.output.with_suffix(".sha256").write_text(
        hashlib.sha256(raw.encode()).hexdigest() + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--identities", type=Path, required=True)
    parser.add_argument("--identity-tool", type=Path, required=True)
    parser.add_argument("--identity-protocol", type=Path, required=True)
    parser.add_argument("--identity-npz", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--repository-frames", type=Path, required=True)
    parser.add_argument("--repository-propagation", type=Path, required=True)
    parser.add_argument("--repository-prediction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
