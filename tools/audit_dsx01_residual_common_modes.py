"""Compare overlapping curved residuals by satellite and hardware grouping."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write


def overlap(a, b):
    """Interpolate within measured support only and across gaps <=1 second."""
    ta, tb = a["times"], b["times"]
    mask = (ta >= tb[0]) & (ta <= tb[-1])
    times = ta[mask]
    index = np.searchsorted(tb, times)
    index = np.clip(index, 1, len(tb) - 1)
    good = tb[index] - tb[index - 1] <= 1.0
    times = times[good]
    if len(times) < 12 or np.ptp(times) < 8:
        return None
    return times, a["residual"][mask][good], np.interp(times, tb, b["residual"])


def run(case, root, output):
    output.mkdir(parents=True, exist_ok=False)
    original = (
        Path(__file__).resolve().parents[1]
        / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter"
        / case
    )
    tracks = {t["key"]: t for t in load_tracks(original)}
    raw = json.loads((root / "cohort" / case / "fitted_c/diagnosis.json").read_text())[0]
    candidates = {r["component"]: r for r in raw["association"]["rows"]}
    associations = json.loads((root / "audit" / case / "fitted_c/association.json").read_text())[
        "rows"
    ]
    counts = {r["component"]: len(r["feasible_candidates"]) for r in associations}
    splits = json.loads(
        (root / "phase_split_audit" / case / "fitted_c/split_checks.json").read_text()
    )
    bridge = {
        r["component"]
        for r in splits
        if r["both_halves_compatible"]
        and all(
            h["candidate_count"] == 1
            and h["candidate_norad"] == candidates[r["component"]]["candidate_norad"]
            for h in r["halves"]
        )
    }
    curves = []
    for row in json.loads((root / "audit" / case / "fitted_c/examples_data.json").read_text()):
        key = row["component"]
        if not candidates[key]["active_curvature"]:
            continue
        if not ((candidates[key]["compatible"] and counts[key] == 1) or key in bridge):
            continue
        t = tracks[key]
        curves.append(
            dict(
                key=key,
                times=t["times"],
                residual=np.array(row["observed_native_hz"])
                - np.array(row["current_prediction_native_hz"]),
                receiver=t["receiver"],
                channel=t["channel"],
                group=2 * (t["receiver"] - 1) + int(t["channel"] > 4),
                q=t["rf_hz"] / 11.5e9,
                satellite=candidates[key]["candidate_norad"],
                status="accepted_curved_unique"
                if candidates[key]["compatible"]
                else "provisional_same_ID_halves",
            )
        )
    pairs = []
    for i, a in enumerate(curves):
        for b in curves[i + 1 :]:
            matched = overlap(a, b)
            if matched is None:
                continue
            times, ra, rb = matched
            same_sat = a["satellite"] == b["satellite"]
            category = (
                "same_satellite_cross_receiver"
                if same_sat and a["receiver"] != b["receiver"]
                else "same_satellite_same_receiver"
                if same_sat
                else "different_satellite_same_RX_band"
                if a["group"] == b["group"]
                else "different_satellite_different_RX_band"
            )
            if same_sat:
                ra, rb = ra / a["q"], rb / b["q"]
            ra, rb = ra - ra.mean(), rb - rb.mean()
            scale = np.sqrt((ra @ ra) * (rb @ rb))
            corr = float((ra @ rb) / scale) if scale > 1e-9 else None
            x = times - times.mean()
            pairs.append(
                dict(
                    a=a["key"],
                    b=b["key"],
                    category=category,
                    a_status=a["status"],
                    b_status=b["status"],
                    samples=len(times),
                    span_s=float(np.ptp(times)),
                    correlation=corr,
                    centered_difference_rms_hz=float(np.sqrt(np.mean((ra - rb) ** 2))),
                    first_rms_hz=float(np.sqrt(np.mean(ra**2))),
                    second_rms_hz=float(np.sqrt(np.mean(rb**2))),
                    first_slope_hz_s=float(ra @ x / (x @ x)),
                    second_slope_hz_s=float(rb @ x / (x @ x)),
                    time_s=times,
                    first_residual_hz=ra,
                    second_residual_hz=rb,
                )
            )
    summary = []
    for category in sorted({r["category"] for r in pairs}):
        own = [r for r in pairs if r["category"] == category]
        summary.append(
            dict(
                category=category,
                pairs=len(own),
                median_correlation=float(
                    np.median([r["correlation"] for r in own if r["correlation"] is not None])
                ),
                median_difference_rms_hz=float(
                    np.median([r["centered_difference_rms_hz"] for r in own])
                ),
                pairs_with_provisional_bridge=sum(
                    "provisional" in r["a_status"] or "provisional" in r["b_status"] for r in own
                ),
            )
        )
    write(output / "pairs.json", pairs)
    write(
        output / "summary.json",
        dict(case=case, curved_tracks=len(curves), pairs=len(pairs), categories=summary),
    )
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            minimum_pairs=12,
            minimum_overlap_s=8,
            maximum_interpolation_gap_s=1,
            no_extrapolation=True,
            all_inputs_curved=True,
            only_fitted_c_descriptive=True,
            candidate_identities_unverified=True,
            pairs_not_statistically_independent=True,
            no_calibration_or_position_fit=True,
        ),
    )
    print(
        json.dumps(dict(case=case, tracks=len(curves), pairs=len(pairs), categories=summary)),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    for case in (f"DSX01-S{i:02}" for i in range(1, 6)):
        run(case, a.root, a.output / case)
