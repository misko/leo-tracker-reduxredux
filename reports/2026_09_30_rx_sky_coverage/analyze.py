"""Read-only DS9–11 sky-support audit; no fitted identity or antenna calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = {
    "DS9": ROOT / "reports/2026_09_28_ds9_post_ds8",
    "DS10": ROOT / "reports/2026_09_29_ds10_post_ds9/local",
    "DS11": ROOT / "reports/2026_09_30_ds11_post_ds10/local",
}
CONTROLS = (
    "radio_null_heldout_negative_log_score",
    "wrong_time_minus_500_heldout_negative_log_score",
    "wrong_time_plus_500_heldout_negative_log_score",
)


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def tier(h):
    if not h["leading_candidate_persisted_on_heldout"] or h["abstention_recommended"]:
        return "rejected"
    score = h["nominal_heldout_negative_log_score"]
    if np.isfinite(score) and all(np.isfinite(h[k]) and score < h[k] for k in CONTROLS):
        return "control_supported"
    return "heldout_only"


def validate_pose(pose, capture):
    content = {k: v for k, v in pose.items() if k != "binding_digest"}
    assert digest(canonical(content)) == pose["binding_digest"]
    authority = pose["pose_authority"]
    assert digest(canonical(authority)) == pose["pose_authority_digest"]
    assert pose["session_id"] == capture["session_id"]
    assert pose["manifest_sha256"] == capture["manifest_sha256"]
    assert authority["radio_id"] == capture["radio_id"]
    assert pose["capture_start_earliest_utc_ns"] == capture["capture_start_earliest_utc_ns"]
    assert pose["capture_end_utc_ns"] == capture["capture_end_utc_ns"]
    assert authority["valid_from_utc_ns"] <= pose["capture_start_earliest_utc_ns"]
    assert pose["capture_end_utc_ns"] < authority["valid_until_utc_ns"]
    return authority


def unit(az, el):
    a, e = np.deg2rad(az), np.deg2rad(el)
    return np.stack([np.cos(e) * np.sin(a), np.cos(e) * np.cos(a), np.sin(e)], axis=-1)


def off_axis(az, el, rx):
    b = unit(270 if rx == 0 else 90, 80)
    return np.rad2deg(np.arccos(np.clip(unit(az, el) @ b, -1, 1)))


def polarization_power(roll, angle=0.0, circular=False):
    """Ideal on-axis linear receive probe; not a measured LNB pattern."""
    x = np.deg2rad(np.asarray(roll) - angle)
    return np.full_like(x, 0.5) if circular else np.cos(x) ** 2


def project(satellite, times, site):
    from leo.sky.frames import (
        ecef_to_enu_matrix, geodetic_to_ecef_km, greenwich_mean_sidereal_time_rad,
        julian_day_from_utc_ns, look_angles, teme_to_ecef,
    )
    jd, fraction = julian_day_from_utc_ns(np.asarray(times, dtype=np.int64))
    err, p, v = satellite.sgp4_array(jd, fraction)
    if np.any(err):
        raise ValueError(f"SGP4 errors: {err.tolist()}")
    p, v = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fraction))
    az, el, _, _ = look_angles(
        p, v, geodetic_to_ecef_km(*site), ecef_to_enu_matrix(*site[:2])
    )
    return az, el


def collect():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.frames import geodetic_to_ecef_km
    from leo.sky.propagation import parse_element_sets

    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = {s.digest: s for s in archive.list_snapshots()}
    catalogues, hashes, authorities, rows, summaries, pose_receipts = {}, {}, {}, [], {}, []
    seen_sessions, seen_manifests = set(), set()
    observer_sites = Counter()
    discrepancies, height_changes, site_changes = [], [], []
    for dataset, folder in SOURCES.items():
        payload = (folder / "manifest.json").read_bytes()
        hashes[str(folder / "manifest.json")] = digest(payload)
        manifest = json.loads(payload)
        counts = Counter(recordings=len(manifest["captures"]), **{
            "visits": manifest["counts"]["visits"], "pose_bound": 0,
            "control_supported": 0, "heldout_only": 0, "rejected": 0,
        })
        for c in manifest["captures"]:
            sid = c["session_id"]
            assert sid not in seen_sessions and c["manifest_sha256"] not in seen_manifests
            seen_sessions.add(sid)
            seen_manifests.add(c["manifest_sha256"])
            apath = folder / "analysis" / f"{sid}.json"
            raw = apath.read_bytes()
            assert digest(raw) == c["analysis_evidence_sha256"]
            hashes[str(apath)] = digest(raw)
            evidence = json.loads(raw)
            p = evidence["tracking"]["product"]
            assert p["input_manifest_sha256"] == c["manifest_sha256"]
            assert p["analysis_manifest_sha256"] == evidence["glrt"]["metrics_manifest_sha256"]
            pp = folder / "pose" / f"{sid}.json"
            if not pp.exists():
                pp = Path("/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1") / f"{sid}.json"
            if not pp.exists():
                raise ValueError(f"No bound pose for {sid}; do not infer continuity")
            raw_pose = pp.read_bytes()
            pose = json.loads(raw_pose)
            authority = validate_pose(pose, c)
            if c.get("pose_file_sha256"):
                assert digest(raw_pose) == c["pose_file_sha256"]
            hashes[str(pp)] = digest(raw_pose)
            authorities[pose["pose_authority_digest"]] = authority
            pose_receipts.append({"dataset": dataset, "session_id": sid, "source": str(pp),
                                  "sha256": digest(raw_pose), "snapshot_pose_status": c["pose_status"]})
            counts["pose_bound"] += 1
            site = (authority["latitude_deg"], authority["longitude_deg"], 0.0)
            old = p["observer_site"]
            old_site = tuple(old[k] for k in ("latitude_deg", "longitude_deg", "altitude_m"))
            observer_sites[old_site] += 1
            discrepancies.append(float(np.linalg.norm(
                geodetic_to_ecef_km(*site) - geodetic_to_ecef_km(*old_site))))
            tracks = {t["tracklet_id"]: t for t in p["tracklets"]}
            assert len(tracks) == len(p["tracklets"])
            for t in tracks.values():
                counts[f"all_tracks_rx{t['receiver_id']}"] += 1
            counts["attempted_groups"] += p["attempted_group_count"]
            counts["eligible_groups"] += p["eligible_group_count"]
            snapshot_digest = p["original_tle_snapshot"]["digest"]
            if snapshot_digest not in catalogues:
                snap = snapshots[snapshot_digest]
                cat = parse_element_sets(archive.read(snap))
                catalogues[snapshot_digest] = dict(zip(cat.satellite_numbers, cat.satellites, strict=True))
            cat = catalogues[snapshot_digest]
            used = set()
            for h in p["tle_candidates"]:
                level = tier(h)
                counts[level] += 1
                if level == "rejected":
                    continue
                for tid in h["tracklet_ids"]:
                    if tid not in tracks:
                        counts["group_track_not_in_export"] += 1
                        continue
                    if tid in used:
                        raise ValueError("Overlapping candidate groups would duplicate a track")
                    used.add(tid)
                    t = tracks[tid]
                    times = np.linspace(t["start_utc_ns"], t["end_utc_ns"], 9).astype(np.int64)
                    sat = cat[h["leading_catalog_number"]]
                    az, el = project(sat, times, site)
                    azh, elh = project(sat, times, (*site[:2], 100.0))
                    azo, elo = project(sat, times, old_site)
                    height_changes.extend(np.rad2deg(np.arccos(np.clip(
                        np.sum(unit(az, el) * unit(azh, elh), axis=-1), -1, 1))).tolist())
                    site_changes.extend(np.rad2deg(np.arccos(np.clip(
                        np.sum(unit(az, el) * unit(azo, elo), axis=-1), -1, 1))).tolist())
                    rows.append({"dataset": dataset, "session_id": sid, "tracklet_id": tid,
                        "group_id": h["physical_group_id"], "tier": level,
                        "receiver_id": t["receiver_id"], "channel": t["channel"],
                        "edge": t["edge"], "sample_rate_hz": c["sample_rate_hz"],
                        "catalog_number": h["leading_catalog_number"],
                        "snapshot_digest": snapshot_digest, "times_utc_ns": times.tolist(),
                        "azimuth_deg": az.tolist(), "elevation_deg": el.tolist(),
                        "off_axis_deg": off_axis(az, el, t["receiver_id"]).tolist(),
                        "observation_count": t["observation_count"],
                        "selected_tau_s_not_applied": h["selected_tau_s"],
                        "control_margins_nats": {k: h[k] - h["nominal_heldout_negative_log_score"] for k in CONTROLS}})
        summaries[dataset] = dict(counts)
    return {"schema": "exploratory-rx-sky-support/v1", "summaries": summaries,
        "authorities": authorities, "pose_receipts": pose_receipts, "source_hashes": hashes,
        "archived_observer_sites": [{"site": list(k), "count": v} for k, v in observer_sites.items()],
        "site_displacement_km_range": [min(discrepancies), max(discrepancies)],
        "height_0_to_100m_max_direction_change_deg": max(height_changes),
        "old_to_roof_max_direction_change_deg": max(site_changes),
        "projection_altitude_m_assumed": 0.0, "rows": rows,
        "projection_policy": "Archived exact original TLE, actual track times, no fitted time shift; 9 illustrative knots per retained track; labels remain old-site conditional."}


def plot(doc):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 11, "axes.titlesize": 12})
    colors = ["#2166ac", "#c05b16"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 9), subplot_kw={"projection": "polar"})
    rows = doc["rows"]
    stats = {}
    for col, ds in enumerate(SOURCES):
        for rx in (0, 1):
            ax = axes[rx, col]
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            ax.set_ylim(0, 90)
            ax.set_yticks([30, 60, 90], ["60° el", "30° el", "horizon"])
            ax.set_xticks(np.deg2rad([0, 90, 180, 270]), ["N", "E", "S", "W"])
            sub = [r for r in rows if r["dataset"] == ds and r["receiver_id"] == rx]
            for r in sub:
                strong = r["tier"] == "control_supported"
                az, el = np.asarray(r["azimuth_deg"]), np.asarray(r["elevation_deg"])
                mask = el >= 0
                ax.scatter(np.deg2rad(az[mask]), 90-el[mask], s=3 if not strong else 9,
                           color=colors[rx] if strong else "#9c9c9c", alpha=.75 if strong else .1,
                           linewidths=0, zorder=3 if strong else 2)
            ax.scatter(np.deg2rad(270 if rx == 0 else 90), 10, marker="*", s=110,
                       color=colors[rx], edgecolor="black", linewidth=.5, zorder=5)
            nstrong = sum(r["tier"] == "control_supported" for r in sub)
            ax.set_title(f"{ds} · RX{rx}\n{len(sub)} conditional tracks; {nstrong} pass controls", pad=18)
            mid = [r["elevation_deg"][4] for r in sub]
            stats[f"{ds}_rx{rx}"] = {"conditional_tracks": len(sub), "control_supported_tracks": nstrong,
                "midpoint_elevation_quantiles_deg": np.percentile(mid, [0, 5, 50, 95, 100]).tolist() if mid else [],
                "below_horizon_knots": sum(e < 0 for r in sub for e in r["elevation_deg"])}
            strong = [r for r in sub if r["tier"] == "control_supported"]
            stats[f"{ds}_rx{rx}"]["control_supported"] = {
                "sessions": len({r["session_id"] for r in strong}),
                "groups": len({(r["session_id"], r["group_id"]) for r in strong}),
                "midpoint_elevation_quantiles_deg": np.percentile(
                    [r["elevation_deg"][4] for r in strong], [5, 50, 95]
                ).tolist() if strong else [],
                "midpoint_east_tracks": sum(r["azimuth_deg"][4] < 180 for r in strong),
                "midpoint_west_tracks": sum(r["azimuth_deg"][4] >= 180 for r in strong),
            }
    fig.suptitle("Conditional signal directions at the roof — not measured antenna coverage", fontsize=16)
    fig.text(.5, .025, "Gray: held-out leader only. Color: also beats radio-null and both wrong-time controls.\n"
             "Stars: nominal 10° outward tilt, assuming a level mount. Blank sky is untested, not invisible.\n"
             "Tracks and interpolated knots are dependent; no satellite identity is verified.", ha="center", fontsize=11)
    fig.subplots_adjust(top=.81, bottom=.13, hspace=.6, wspace=.32)
    fig.savefig(HERE / "conditional-sky.png", dpi=180)
    fig.savefig(HERE / "conditional-sky.svg")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    az, el = np.meshgrid(np.arange(361), np.arange(91))
    for rx, ax in enumerate(axes):
        im = ax.pcolormesh(az, el, off_axis(az, el, rx), cmap="viridis_r", vmin=0, vmax=100, shading="auto")
        cs = ax.contour(az, el, off_axis(az, el, rx), levels=[15, 30, 45, 60, 90], colors="white", linewidths=.8)
        ax.clabel(cs, fmt="%d°", fontsize=9)
        ax.scatter(270 if rx == 0 else 90, 80, marker="*", color="#d64c2e", s=90)
        ax.set(title=f"RX{rx}: nominal {'west' if rx == 0 else 'east'} tilt", xlabel="Azimuth from north", ylabel="Elevation (°)")
        ax.set_xticks([0, 90, 180, 270, 360], ["N", "E", "S", "W", "N"])
    fig.colorbar(im, ax=axes, label="Angular distance from nominal axis (°)", pad=.025, fraction=.03)
    fig.suptitle("Both nominal axes point mostly upward, only 20° apart", fontsize=15)
    fig.text(.5, .01, "Contours are geometric offsets, not gain or beam edges. Elevation and RX cable mapping remain unmeasured.", ha="center")
    fig.subplots_adjust(bottom=.15, top=.85, right=.84, wspace=.22)
    fig.savefig(HERE / "nominal-geometry.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    rolls = np.linspace(0, 180, 361)
    axes[0].plot(rolls, polarization_power(rolls, circular=True), label="Circular incident wave", lw=2)
    axes[0].plot(rolls, polarization_power(rolls), label="Known linear angle: 0°", lw=2)
    axes[0].plot(rolls, polarization_power(rolls, 45), label="Known linear angle: 45°", lw=2, ls="--")
    axes[0].set(xlabel="Probe roll (°)", ylabel="Fraction of incident power", title="Ideal on-axis polarization coupling", ylim=(-.03, 1.06))
    axes[0].legend(fontsize=9)
    names = list(SOURCES)
    held = [doc["summaries"][d]["heldout_only"] + doc["summaries"][d]["control_supported"] for d in names]
    strong = [doc["summaries"][d]["control_supported"] for d in names]
    axes[1].bar(names, held, color="#bbbbbb", label="Held-out leader (includes colored subset)")
    axes[1].bar(names, strong, color="#2166ac", label="Also beats all three controls")
    for i, (h, s) in enumerate(zip(held, strong, strict=True)):
        axes[1].text(i, h+8, f"{s} / {h}", ha="center")
    axes[1].set(ylabel="Candidate groups", title="How much directional evidence survives?", ylim=(0, max(held)*1.4))
    axes[1].legend(fontsize=8, loc="upper left")
    fig.text(.5, .01, "Left: analytical illustration, not a fit to DS9–11. Off-axis LNB patterns may break this symmetry, but need calibration.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(HERE / "roll-identifiability.png", dpi=180)
    plt.close(fig)
    (HERE / "sky-statistics.json").write_text(json.dumps(stats, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["collect", "plot"])
    args = parser.parse_args()
    if args.action == "collect":
        print(json.dumps(collect(), allow_nan=False))
    else:
        plot(json.loads((HERE / "evidence.json").read_text()))
