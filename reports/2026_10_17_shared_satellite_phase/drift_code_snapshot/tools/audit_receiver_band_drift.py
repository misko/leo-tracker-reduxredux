"""Matched small-drift sensitivity at the supplied, fixed evaluation site.

No geographic estimate or authenticated satellite identity is produced. The
same Graph points, merged groups and causal orbit bank are used in every arm.
"""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, solve_bias, write

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.track_catalogue_geometry import frequency_grid

LABELS = ("RX1 low", "RX1 high", "RX2 low", "RX2 high")
CONTRASTS = (
    ("RX2 minus RX1 low", 2, 0),
    ("RX2 minus RX1 high", 3, 1),
    ("RX1 high minus low", 1, 0),
    ("RX2 high minus low", 3, 2),
)
POLICIES = (("zero", 0.0, 0.5), ("tight", 1.0, 0.5), ("baseline", 5.0, 2.0))


def calibration_summary(beta, *, bound_hz_s):
    """Native-Hz intercepts at 150 s and 11.5 GHz; contrasts modulo alias."""
    beta = np.asarray(beta, dtype=float)
    if beta.shape not in ((8,), (9,)) or not np.all(np.isfinite(beta)):
        raise ValueError("eight or nine finite calibration parameters required")
    if not np.isfinite(bound_hz_s) or bound_hz_s < 0:
        raise ValueError("finite nonnegative drift bound required")
    result = dict(
        groups=[
            dict(
                label=label,
                offset_hz=float(beta[g]),
                drift_hz_s=float(beta[g + 4] / 150),
                bound_active=bool(bound_hz_s > 0 and abs(beta[g + 4] / 150) >= bound_hz_s - 1e-4),
            )
            for g, label in enumerate(LABELS)
        ],
        contrasts=[],
        rf_c_hz_per_ghz=float(beta[8]) if len(beta) == 9 else 0.0,
    )
    for label, left, right in CONTRASTS:
        delta = (
            beta[left] - beta[right] + matching.PERIOD / 2
        ) % matching.PERIOD - matching.PERIOD / 2
        result["contrasts"].append(
            dict(
                label=label,
                offset_hz=float(delta),
                drift_hz_s=float((beta[left + 4] - beta[right + 4]) / 150),
            )
        )
    return result


def evaluate_fit(groups, tracks, sky, times, frequency, stats, beta, ranks, bound):
    terms = profile_component_bias(stats, beta, bias_sigma_hz=1000.0)
    rows = []
    for ci, (key, _members) in enumerate(groups):
        candidate = terms.best[ci]
        checks = []
        for fi in np.flatnonzero(stats["ci"] == ci):
            track = stats["fragments"][fi]
            g = matching.group(track)
            cal = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
            if len(beta) == 9:
                cal += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
            residual = track["values"] + terms.aliases[fi, candidate] * matching.PERIOD - cal
            residual -= (
                track["rf_hz"]
                / 11.5e9
                * frequency[candidate, np.searchsorted(times, track["times"])]
            )
            residual -= terms.bias_hz[ci, candidate]
            checks.append(matching.noise_screen(residual, track["times"])["noise_screen_pass"])
        compatible = (
            stats["component_visible"][ci, candidate]
            and terms.rms_hz[ci] <= 450
            and abs(terms.bias_hz[ci, candidate]) <= 3000
            and all(checks)
        )
        rows.append(
            dict(
                component=key,
                candidate_norad=int(sky["norad"][candidate]),
                points=int(stats["count"][ci]),
                rms_hz=float(terms.rms_hz[ci]),
                compatible=bool(compatible),
                active_curvature=bool(stats["active"][ci]),
            )
        )
    supported = (
        stats["fragment_active"] & stats["active"][stats["ci"]] & (terms.rms_hz[stats["ci"]] < 450)
    )
    support = []
    for g in range(4):
        indexes = np.flatnonzero(supported & (stats["g"] == g))
        supported_times = (
            np.concatenate([stats["fragments"][i]["times"] for i in indexes])
            if len(indexes)
            else np.array([])
        )
        support.append(
            dict(
                label=LABELS[g],
                curved_fragments=len(indexes),
                curved_components=len(set(stats["ci"][indexes].tolist())),
                time_span_s=float(np.ptp(supported_times)) if len(supported_times) else 0.0,
            )
        )
    active = np.flatnonzero(stats["active"])
    score = float(
        np.sum(
            np.minimum(stats["count"][active], 50)
            * np.minimum(terms.score[active, terms.best[active]], 900.0**2)
        )
    )
    score += 150.0**2 * float(np.sum((beta[4:8] / (150 * matching.DRIFT_SIGMA_HZ_S)) ** 2))
    return dict(
        calibration=calibration_summary(beta, bound_hz_s=bound),
        support=support,
        calibration_ranks=ranks,
        points=sum(len(t["times"]) for t in tracks),
        compatible_points=sum(r["points"] for r in rows if r["compatible"]),
        compatible_components=sum(r["compatible"] for r in rows),
        penalized_score=score,
        components=rows,
    )


def run(recording, inputs, output, latitude, longitude):
    output.mkdir(parents=True, exist_ok=False)
    receipt = json.loads((inputs / "receipt.json").read_text())
    for path, expected in (
        (inputs / "bank.npz", receipt["bank_sha256"]),
        (recording / "tracks.json", receipt["tracks_sha256"]),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("input digest changed")
    tracks = load_tracks(recording)
    merged = json.loads((recording / "merged.json").read_text())
    groups = {}
    for track in tracks:
        groups.setdefault(merged["result"]["ownership"][track["key"]], []).append(track)
    groups = sorted(groups.items())
    with np.load(inputs / "bank.npz") as archive:
        sky = {k: archive[k] for k in archive.files}
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    frequency, elevation = frequency_grid(sky, times, latitude, longitude)
    stats = matching.statistics(
        groups,
        dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
        {str(t["channel"]): 0.0 for t in tracks},
    )
    protocol = dict(
        source_id=receipt["source_id"],
        latitude_deg=latitude,
        longitude_deg=longitude,
        position_mode="supplied fixed evaluation site; no position estimate",
        independent_identity_labels=False,
        grouping="frozen merged",
        seed_budget=160,
        bias_sigma_hz=1000.0,
        policies=POLICIES,
        receipt=receipt,
        source_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(matching.__file__),
                Path(__file__).with_name("associate_merged_track_catalogue.py"),
            )
        },
    )
    write(output / "protocol.json", protocol)
    rows = []
    original = matching.DRIFT_BOUND_HZ_S, matching.DRIFT_SIGMA_HZ_S
    try:
        for policy, bound, sigma in POLICIES:
            matching.DRIFT_BOUND_HZ_S, matching.DRIFT_SIGMA_HZ_S = bound, sigma
            for fitted_c in (False, True):
                initial = np.asarray(merged["calibration"]["beta"])
                if fitted_c:
                    initial = np.r_[initial, 0.0]
                beta, ranks = solve_bias(stats, initial, 1000.0, 160)
                row = evaluate_fit(groups, tracks, sky, times, frequency, stats, beta, ranks, bound)
                row.update(
                    policy=policy,
                    bound_hz_s=bound,
                    sigma_hz_s=sigma,
                    fitted_c=fitted_c,
                    beta=beta.tolist(),
                    source_id=receipt["source_id"],
                )
                write(output / f"{policy}_{'fitted_c' if fitted_c else 'c0'}.json", row)
                rows.append(row)
                print(
                    json.dumps(
                        {
                            k: row[k]
                            for k in (
                                "source_id",
                                "policy",
                                "fitted_c",
                                "compatible_points",
                                "penalized_score",
                            )
                        }
                    ),
                    flush=True,
                )
    finally:
        matching.DRIFT_BOUND_HZ_S, matching.DRIFT_SIGMA_HZ_S = original
    write(
        output / "summary.json",
        [{k: v for k, v in row.items() if k != "components"} for row in rows],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--longitude", type=float, required=True)
    a = p.parse_args()
    run(a.recording, a.inputs, a.output, a.latitude, a.longitude)
