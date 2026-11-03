"""Validate the bounded native replay and export its candidate position/time tuples."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

from leo.native_pipeline.orbit_input import catalogue_id
from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)


def read_observations(path):
    lines = iter(path.read_text().splitlines())
    next(lines)
    count = int(next(lines))
    tracks = []
    for _ in range(count):
        n, k = map(int, next(lines).split())
        data = np.array([list(map(float, next(lines).split())) for _ in range(n)])
        for _ in range(k):
            next(lines)
        tracks.append(data)
    return tracks


def states(satellite, origin, times):
    jd, fraction = julian_day_from_utc_ns(origin + np.rint(times * 1e9).astype(np.int64))
    errors, p, v = satellite.sgp4_array(jd, fraction)
    if np.any(errors):
        raise ValueError("direct validation propagation failed")
    return teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fraction))


def hermite(p, v, begin, step, times):
    coordinate = (times - begin) / step
    k = np.minimum(coordinate.astype(int), len(p) - 2)
    u = (coordinate - k)[:, None]
    position = (
        (2 * u**3 - 3 * u * u + 1) * p[k]
        + (u**3 - 2 * u * u + u) * step * v[k]
        + (-2 * u**3 + 3 * u * u) * p[k + 1]
        + (u**3 - u * u) * step * v[k + 1]
    )
    velocity = (
        ((6 * u * u - 6 * u) * p[k] + (-6 * u * u + 6 * u) * p[k + 1]) / step
        + (3 * u * u - 4 * u + 1) * v[k]
        + (3 * u * u - 2 * u) * v[k + 1]
    )
    return position, velocity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    root = args.report

    def read(name):
        return json.loads((root / name).read_text())

    meta, host, arm = read("input/input.json"), read("host.json"), read("arm.json")
    audit, reference = read("host-full-audit.json"), read("host-ungated-reference.json")
    endpoint = read("host-endpoint-experiment.json")
    observations = read_observations(root / "input/observations.txt")
    tle_lines = (root / "input/catalogue.tle").read_text().splitlines()[1:]
    elements = {
        catalogue_id(a[2:7]): (a, b) for a, b in zip(tle_lines[::2], tle_lines[1::2], strict=True)
    }
    times = np.arange(host["cache_begin_s"], host["cache_end_s"] + 0.1, host["fine_step_s"])
    max_interp, max_native_rms = 0.0, 0.0
    rows = []
    for t, data, description in zip(arm["tracks"], observations, meta["tracks"], strict=True):
        for rank, hypothesis in enumerate(t["hypotheses"], 1):
            sat = Satrec.twoline2rv(*elements[hypothesis["satellite_id"]])
            local = data[:, 0] + hypothesis["time_offset_s"]
            p, v = states(sat, meta["origin_utc_ns"], local)
            kp, kv = states(sat, meta["origin_utc_ns"], times)
            ip, iv = hermite(kp, kv, times[0], host["fine_step_s"], local)
            site = geodetic_to_ecef_km(hypothesis["latitude_deg"], hypothesis["longitude_deg"], 0)

            def frequency(position, velocity, receiver):
                q = position - receiver
                rate = np.sum(q * velocity, axis=1) / np.linalg.norm(q, axis=1)
                return -meta["carrier_hz"] / 299792.458 * rate

            direct, interpolated = frequency(p, v, site), frequency(ip, iv, site)
            max_interp = max(max_interp, float(np.max(np.abs(direct - interpolated))))
            train = data[:, 2].astype(bool)
            residual = data[:, 1] - direct
            residual -= np.mean(residual[train])
            direct_training_rms = float(np.sqrt(np.mean(residual[train] ** 2)))
            direct_validation_rms = float(np.sqrt(np.mean(residual[~train] ** 2)))
            max_native_rms = max(
                max_native_rms, abs(direct_validation_rms - hypothesis["validation_rms_hz"])
            )
            origin = meta["origin_utc_ns"] + round(hypothesis["time_offset_s"] * 1e9)
            rows.append(
                {
                    "track_index": t["track_index"],
                    "track_id": description["track_id"],
                    "rank": rank,
                    **hypothesis,
                    "local_zero_utc_ns": origin,
                    "fragment_start_utc_ns": origin + round(description["start_s"] * 1e9),
                    "direct_training_rms_hz": direct_training_rms,
                    "direct_validation_rms_hz": direct_validation_rms,
                }
            )
    with (root / "hypotheses.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    best = [r for r in rows if r["rank"] == 1]
    summary = {
        "session_id": meta["session_id"],
        "candidate_only": True,
        "arm_whole_process": json.loads((root / "arm.time.txt").read_text()),
        "host_total_s": host["total_s"],
        "catalogue_records": arm["catalogue_records"],
        "regional_candidates": arm["retained_catalogue_count"],
        "track_count": len(best),
        "observation_count": arm["observation_count"],
        "orbit_workspace_bytes": arm["orbit_state_capacity_bytes"],
        "hypothesis_capacity_bytes": arm["hypothesis_capacity_bytes"],
        "gate_matches_unfiltered_ranked_results": host["tracks"] == reference["tracks"],
        "fine_envelope_gate_misses": audit["gate_fine_envelope_misses"],
        "arm_host_same_ranked_ids": all(
            [h["satellite_id"] for h in a["hypotheses"]]
            == [h["satellite_id"] for h in b["hypotheses"]]
            for a, b in zip(host["tracks"], arm["tracks"], strict=True)
        ),
        "maximum_direct_vs_interpolated_doppler_hz": max_interp,
        "maximum_direct_vs_arm_validation_rms_delta_hz": max_native_rms,
        "median_validation_rms_hz": float(np.median([r["direct_validation_rms_hz"] for r in best])),
        "validation_rms_under_200_hz": sum(r["direct_validation_rms_hz"] < 200 for r in best),
        "tracks_with_runner_up_within_1hz_training_rms": sum(
            t["hypotheses"][1]["training_rms_hz"] - t["hypotheses"][0]["training_rms_hz"] < 1
            for t in arm["tracks"]
        ),
        "best_at_time_boundary": sum(abs(r["time_offset_s"]) >= 59.9 for r in best),
        "best_at_region_boundary": sum(
            bool(np.hypot(r["east_km"], r["north_km"]) >= meta["region"]["radius_km"] - 0.1)
            for r in best
        ),
        "rejected_endpoint_shortcut_same_winners": sum(
            a["hypotheses"][0]["satellite_id"] == b["hypotheses"][0]["satellite_id"]
            for a, b in zip(endpoint["tracks"], host["tracks"], strict=True)
        ),
        "scope": "Independent fragment candidate retrieval; not a shared-clock position fix, "
        "identity confirmation, exhaustive continuous search, or IQ pipeline benchmark.",
    }
    summary["artifacts_sha256"] = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in [
            "host.json",
            "arm.json",
            "hypotheses.csv",
            "host-ungated-reference.json",
            "arm-protocol.json",
        ]
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    angle = np.linspace(0, 2 * np.pi, 200)
    radius = meta["region"]["radius_km"]
    ax[0].plot(radius * np.cos(angle), radius * np.sin(angle), color="0.65", lw=1)
    scatter = ax[0].scatter(
        [r["east_km"] for r in best],
        [r["north_km"] for r in best],
        c=[r["time_offset_s"] for r in best],
        cmap="coolwarm",
        vmin=-60,
        vmax=60,
    )
    fig.colorbar(scatter, ax=ax[0], label="Fitted clock offset (s)")
    ax[0].set(
        xlabel="East of region centre (km)",
        ylabel="North of region centre (km)",
        title="Best candidate per fragment; positions remain ambiguous",
        aspect="equal",
    )
    x = np.sort([r["direct_validation_rms_hz"] for r in best])
    ax[1].plot(x, np.arange(1, len(x) + 1), lw=2)
    ax[1].axvline(200, color="0.5", ls="--", label="200 Hz diagnostic threshold")
    ax[1].set(
        xlabel="Held-out frequency RMS (Hz), direct SGP4",
        ylabel="Cumulative fragments",
        title="Candidates selected using training measurements",
    )
    ax[1].legend(fontsize=8)
    fig.savefig(root / "candidate-summary.png", dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
