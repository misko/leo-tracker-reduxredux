"""Known-site DS7 track annotations using frozen candidate orbit banks."""

import csv
import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "local"
RF = 11.2e9  # Exported track observations are normalized to this canonical RF.
C = 299792.458


def geometry(lat, lon, altitude_m=0):
    lat, lon = np.radians([lat, lon])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    east = np.array([-np.sin(lon), np.cos(lon), 0])
    north = np.cross(up, east)
    n = 6378.137 / np.sqrt(1 - 6.69437999014e-3 * np.sin(lat) ** 2)
    rec = (
        np.array(
            [
                n * np.cos(lat) * np.cos(lon),
                n * np.cos(lat) * np.sin(lon),
                n * (1 - 6.69437999014e-3) * np.sin(lat),
            ]
        )
        + up * altitude_m / 1000
    )
    return rec, np.array([east, north, up])


def predict(pos, vel, rec, basis):
    delta = pos - rec
    ranges = np.linalg.norm(delta, axis=-1)
    unit = delta / ranges[..., None]
    enu = unit @ basis.T
    return (
        -RF / C * np.sum(unit * vel, axis=-1),
        np.degrees(np.arctan2(enu[..., 0], enu[..., 1])) % 360,
        np.degrees(np.arcsin(np.clip(enu[..., 2], -1, 1))),
        ranges,
    )


def scores(y, predictions, mask):
    offsets = np.mean(y[None, mask] - predictions[:, mask], axis=1)
    residual = y[None, :] - predictions - offsets[:, None]
    train = np.sqrt(np.mean(residual[:, mask] ** 2, axis=1))
    hold = np.sqrt(np.mean(residual[:, ~mask] ** 2, axis=1))
    return train, hold, offsets, residual


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def main():
    inputs = json.loads((OUT / "inputs.json").read_text())
    annotations, candidates, coverage = [], [], []
    for number, item in enumerate(inputs["recordings"]):
        start = time.monotonic()
        document = json.loads(Path(item["tracks"]).read_text())
        assert (
            "sha256:" + hashlib.sha256(Path(item["tracks"]).read_bytes()).hexdigest()
            == item["tracks_sha256"]
        )
        bankdir = Path(item["bank"])
        assert (
            "sha256:" + hashlib.sha256((bankdir / "banks.npz").read_bytes()).hexdigest()
            == item["bank_sha256"]
        )
        meta = json.loads((bankdir / "manifest.json").read_text())
        authority = json.loads(Path(item["pose"]).read_text())["pose_authority"]
        rec, basis = geometry(authority["latitude_deg"], authority["longitude_deg"])
        high, _ = geometry(authority["latitude_deg"], authority["longitude_deg"], 100)
        catalogue = inputs["catalogues"][item["catalogue_digest"]]
        by_id = {r["track_id"]: r for r in document["tracks"]}
        bank_ids = {r["track_id"] for r in meta["tracks"]}
        assert bank_ids <= set(by_id)
        session_rows = []
        for track_id in sorted(set(by_id) - bank_ids):
            tr = by_id[track_id]
            t = tr["times_s"]
            session_rows.append(
                dict(
                    session_id=item["session_id"],
                    track_id=track_id,
                    receiver_id=tr["receiver_id"],
                    channel=tr["channel"],
                    rf_hz=tr["rf_hz"],
                    start_utc=utc(document["start_utc_ns"] + int(t[0] * 1e9)),
                    end_utc=utc(document["start_utc_ns"] + int(t[-1] * 1e9)),
                    observations=len(t),
                    duration_s=t[-1] - t[0],
                    status="unresolved_no_candidate_bank",
                    norad_id=None,
                    satellite_name=None,
                    start_relative_s=t[0],
                    end_relative_s=t[-1],
                )
            )
        with np.load(bankdir / "banks.npz", allow_pickle=False) as bank:
            taus = bank["timing_grid_s"]
            zero = int(np.flatnonzero(taus == 0)[0])
            for spec in meta["tracks"]:
                tr = by_id[spec["track_id"]]
                index = spec["index"]
                pos = bank[f"position_km_{index}"]
                vel = bank[f"velocity_km_s_{index}"]
                ids = bank[f"candidate_ids_{index}"]
                y, t = np.asarray(tr["measured_hz"]), np.asarray(tr["times_s"])
                mask = np.asarray(tr["training_mask"], bool)
                pred, az, el, ranges = predict(pos[:, zero], vel[:, zero], rec, basis)
                train, hold, offsets, residual = scores(y, pred, mask)
                visible = np.mean(el >= 0, axis=1)
                eligible = visible >= 0.95
                ranked = np.argsort(np.where(eligible, train, np.inf))
                valid = [int(i) for i in ranked if eligible[i]]
                row = dict(
                    session_id=item["session_id"],
                    track_id=tr["track_id"],
                    receiver_id=tr["receiver_id"],
                    channel=tr["channel"],
                    rf_hz=tr["rf_hz"],
                    start_utc=utc(document["start_utc_ns"] + int(t[0] * 1e9)),
                    end_utc=utc(document["start_utc_ns"] + int(t[-1] * 1e9)),
                    observations=len(y),
                    train_observations=int(mask.sum()),
                    validation_observations=int((~mask).sum()),
                    duration_s=float(t[-1] - t[0]),
                    shortlisted_candidates=len(ids),
                    visible_candidates=len(valid),
                    status="unresolved_no_visible_candidate",
                    norad_id=None,
                    satellite_name=None,
                    pose_revision=authority["revision"],
                    start_relative_s=float(t[0]),
                    end_relative_s=float(t[-1]),
                )
                if not valid:
                    session_rows.append(row)
                    continue
                best = valid[0]
                runner = valid[1] if len(valid) > 1 else None
                midpoint = int(np.argmin(abs(t - (t[0] + t[-1]) / 2)))
                sensitivity = []
                for tau_index, receiver in [(zero - 1, rec), (zero + 1, rec), (zero, high)]:
                    alternative = predict(pos[:, tau_index], vel[:, tau_index], receiver, basis)
                    s = scores(y, alternative[0], mask)[0]
                    ok = np.mean(alternative[2] >= 0, axis=1) >= 0.95
                    sensitivity.append(int(np.argmin(np.where(ok, s, np.inf))) == best)
                centered = t - np.mean(t[mask])
                design = np.c_[np.ones(len(t)), centered]
                coefficients = np.linalg.lstsq(design[mask], y[mask], rcond=None)[0]
                null_rms = float(np.sqrt(np.mean((y[~mask] - design[~mask] @ coefficients) ** 2)))
                # Drift sensitivity is diagnostic only; main fit has just a constant offset.
                drift = np.clip(
                    np.sum(residual[:, mask] * centered[mask], axis=1)
                    / np.sum(centered[mask] ** 2),
                    -25,
                    25,
                )
                drift_rms = np.sqrt(
                    np.mean((residual[:, mask] - drift[:, None] * centered[mask]) ** 2, axis=1)
                )
                drift_stable = int(np.argmin(np.where(eligible, drift_rms, np.inf))) == best
                margin = float(train[runner] - train[best]) if runner is not None else None
                val_margin = float(hold[runner] - hold[best]) if runner is not None else None
                likely = (
                    len(y) >= 20
                    and t[-1] - t[0] >= 10
                    and hold[best] <= 250
                    and margin is not None
                    and margin >= 100
                    and val_margin >= 100
                    and all(sensitivity)
                    and drift_stable
                    and null_rms - hold[best] >= 25
                )
                status = (
                    "likely_conditional"
                    if likely
                    else ("tentative" if hold[best] <= 500 else "unresolved_poor_fit")
                )
                azimuth = float(az[best, midpoint])
                facing = 270 if tr["receiver_id"] == 0 else 90
                gap = abs((azimuth - facing + 180) % 360 - 180)
                row.update(
                    status=status,
                    norad_id=int(catalogue["norad_ids"][ids[best]]),
                    satellite_name=catalogue["names"][ids[best]],
                    train_rms_hz=float(train[best]),
                    validation_rms_hz=float(hold[best]),
                    offset_hz=float(offsets[best]),
                    runner_up_margin_hz=margin,
                    validation_runner_up_margin_hz=val_margin,
                    linear_null_validation_rms_hz=null_rms,
                    null_advantage_hz=null_rms - float(hold[best]),
                    time_height_stable=all(sensitivity),
                    bounded_drift_stable=drift_stable,
                    azimuth_mid_deg=azimuth,
                    elevation_mid_deg=float(el[best, midpoint]),
                    elevation_min_deg=float(el[best].min()),
                    range_mid_km=float(ranges[best, midpoint]),
                    azimuth_difference_from_provisional_rx_deg=gap,
                    provisional_facing_hemisphere=gap <= 90,
                    runner_up_norad_id=int(catalogue["norad_ids"][ids[runner]])
                    if runner is not None
                    else None,
                )
                for rank, candidate in enumerate(valid[:3], 1):
                    candidates.append(
                        dict(
                            session_id=item["session_id"],
                            track_id=tr["track_id"],
                            rank=rank,
                            norad_id=int(catalogue["norad_ids"][ids[candidate]]),
                            satellite_name=catalogue["names"][ids[candidate]],
                            train_rms_hz=float(train[candidate]),
                            validation_rms_hz=float(hold[candidate]),
                            azimuth_mid_deg=float(az[candidate, midpoint]),
                            elevation_mid_deg=float(el[candidate, midpoint]),
                            visible_fraction=float(visible[candidate]),
                        )
                    )
                session_rows.append(row)
        for row in session_rows:
            peers = [
                other
                for other in session_rows
                if other["receiver_id"] != row["receiver_id"]
                and other["channel"] == row["channel"]
                and min(row["end_relative_s"], other["end_relative_s"])
                > max(row["start_relative_s"], other["start_relative_s"])
            ]
            row["overlapping_other_rx_tracks"] = len(peers)
            row["other_rx_same_top_candidate"] = bool(
                row["norad_id"] and any(other["norad_id"] == row["norad_id"] for other in peers)
            )
        annotations.extend(session_rows)
        coverage.append(
            dict(
                session_id=item["session_id"],
                tracks=len(session_rows),
                elapsed_s=time.monotonic() - start,
            )
        )
        if number % 8 == 0:
            print(f"Processed {number + 1}/88 recordings; {len(annotations)} tracks", flush=True)
    for name, rows in [("track-annotations", annotations), ("top-three-candidates", candidates)]:
        (OUT / (name + ".json")).write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
        columns = list(dict.fromkeys(k for row in rows for k in row))
        with (OUT / (name + ".csv")).open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    summary = dict(
        recordings=len(coverage),
        tracks=len(annotations),
        statuses=dict(Counter(r["status"] for r in annotations)),
        coverage=coverage,
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "coverage"}))


if __name__ == "__main__":
    main()
