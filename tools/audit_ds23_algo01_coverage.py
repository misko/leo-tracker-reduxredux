"""Audit full-scan memberships at saved ALGO01 and repaired position endpoints.

This does not refit position. GPS is absent: endpoints and calibration are replayed
from RF fits. Original winning marks and additional peaks have separate counts.
"""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_frame_joint import actual_metrics, conditional_gate
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_ds23_adaptive_failures import OUTPUT as FAILURES
from investigate_ds23_adaptive_failures import phase_widths
from propagate_ds23_arc_positions import OUT as POSITIONS
from propagate_ds23_arc_positions import SOURCE, PositionNormal, build
from prototype_dsx01_continuous_position import latlon

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/2026_10_18_ds23_algo01_coverage"


def read(path):
    return json.loads(path.read_text())


def coverage(accepted_tracks, tracks, original_ids):
    """Count unique measurements; never divide additional peaks by winner count."""
    by_key = {t["key"]: t for t in tracks}
    owned = []
    for row in accepted_tracks:
        if row["compatible"]:
            owned.extend(row.get("observation_ids", by_key[row["component"]]["observation_ids"]))
    if len(owned) != len(set(owned)):
        raise ValueError("a physical measurement has multiple accepted owners")
    associated = set(owned)
    return dict(
        original_winning_GLRT_points=len(original_ids),
        associated_original_winners=len(associated & original_ids),
        associated_original_percent=100 * len(associated & original_ids) / len(original_ids),
        associated_additional_peaks=len(associated - original_ids),
        associated_distinct_measurements=len(associated),
        associated_tracks=sum(bool(r["compatible"]) for r in accepted_tracks),
        associated_observation_ids=sorted(associated),
    )


def retained_metrics(p, x):
    """Apply the existing profile/conditional gates only to active observations.

    The 36-point salvage retains the original nuisance design. Masked prefix
    points must neither fail the suffix gate nor be counted as accepted suffix.
    """
    scan, state = p.scan, p.state(x)
    result = p.calculate(x)
    frequency, elevation = p.conditional_frequency(x)
    rows = []
    for row, i, sl, alias in zip(p.rows, p.members, p.slices, p.alias, strict=True):
        t, active = scan.tracks[i], p.keep[sl]
        if not active.any():
            continue
        times = t["times"][active]
        q = t["rf_hz"] / 11.5e9
        y = t["values"] - scan.hardware(t, state["beta"])
        y -= q * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        terms = profile(y[active], q * frequency[sl][active], *whitening(times))
        noise = batch_noise_screen(terms["innovations"], times)
        conditional = conditional_gate(result["conditional_residual_hz"][sl][active], times)
        passing = bool(
            terms["rms"][0] <= 450
            and abs(terms["bias"][0]) <= 3000
            and noise["noise_screen_pass"][0]
            and conditional["compatible"]
            and int(terms["alias"][0]) == alias
            and elevation[sl][active].min() >= 0
        )
        rows.append(
            dict(
                component=t["key"],
                norad=row["candidate_norad"],
                candidate_index=row["candidate_index"],
                points=int(active.sum()),
                compatible=passing,
                observation_ids=np.asarray(t["observation_ids"])[active].tolist(),
                conditional_residual_gate=conditional,
                profile_rms_hz=float(terms["rms"][0]),
                profile_bias_hz=float(terms["bias"][0]),
                aliases_changed=int(int(terms["alias"][0]) != alias),
            )
        )
    while True:
        owners = {}
        by_key = {t["key"]: t for t in scan.tracks}
        for row in rows:
            if row["compatible"]:
                t = by_key[row["component"]]
                owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
        changed = False
        for row in rows:
            if (
                row["compatible"]
                and row["candidate_index"] in p.supported
                and len(owners[row["candidate_index"]]) < 2
            ):
                row["compatible"] = False
                changed = True
        if not changed:
            break
    return dict(tracks=rows, accepted_points=sum(r["points"] for r in rows if r["compatible"]))


def endpoint(case, method, arm):
    scan, node, keep, _, _ = build(case, "baseline" if method == "ALGO01" else method)
    if method == "ALGO01" and case == "DS23-0342":
        path = FAILURES / "genuine_causal_prior" / case / "trim_failed.json"
        document = read(path)["results"][0]
        selected = document["selected"]
        k = next(
            k for k, r in enumerate(node["seed"]["rows"]) if r["component"] == document["component"]
        )
        node = copy.deepcopy(node)
        node["seed"]["rows"][k].update(
            candidate_index=selected["candidate_index"], candidate_norad=selected["norad"]
        )
        node["aliases"][k] = selected["alias"]
        probe = PositionNormal(scan, node, scan.radio_sigma_hz, arm == "fitted_c", keep=keep)
        sl = probe.slices[k]
        keep[sl.start + selected["start_index"] : sl.start + selected["stop_index"]] = True
        saved = next(r for r in document["refits"] if r["kind"] == "causal" and r["arm"] == arm)
        reference = saved["phase_reference"]
        fit = saved["fit"]
    else:
        dirname = "baseline" if method == "ALGO01" else method
        suffix = "" if method == "ALGO01" else "_refreshed"
        path = POSITIONS / case / dirname / f"native_{arm}{suffix}.json"
        saved = read(path)
        assert node["aliases"] == saved["aliases"]
        assert [t["observation_ids"] for t in scan.tracks] == [
            t["observation_ids"] for t in saved["input_tracks"]
        ]
        assert node["seed"]["rows"] == saved["rows"]
        reference = saved["phase_reference"]
        fit = saved["fit"]
    p = PositionNormal(
        scan,
        node,
        scan.radio_sigma_hz,
        arm == "fitted_c",
        reference=np.asarray(reference),
        keep=keep,
    )
    p.phase_sigma, _ = phase_widths(scan, p.labels)
    x = np.asarray(fit["parameters"])
    score = float(p.residual(x) @ p.residual(x))
    assert abs(score - fit["score"]) < 1e-5, (case, method, score, fit["score"])
    return p, x, path


def run(case, method, arm):
    p, x, path = endpoint(case, method, arm)
    observations = read(SOURCE / case / "observations.json")
    original_ids = {o["observation_id"] for o in observations}
    metrics = retained_metrics(p, x)
    if p.keep.all():
        legacy = dict(
            rows=p.rows,
            state=p.state(x),
            aliases=p.alias,
            east_north_km=x,
            fits=[dict(parameters=x, score=float(p.residual(x) @ p.residual(x)))],
        )
        original = actual_metrics(p, legacy, arm, x)
        assert {r["component"]: r["compatible"] for r in metrics["tracks"]} == {
            r["component"]: r["compatible"] for r in original["tracks"]
        }
    extended = extend_associations(p, x, metrics)
    result = dict(
        case=case,
        method=method,
        arm=arm,
        endpoint_latlon=latlon(x),
        endpoint_east_north_km=x,
        position_refitted=False,
        frozen_calibration_extension=True,
        calibration_gate_failures=[r for r in metrics["tracks"] if not r["compatible"]],
        compatible_curved_points=metrics["accepted_points"],
        fitted_curved_points=int(p.keep.sum()),
        association=coverage(extended["tracks"], p.scan.tracks, original_ids),
        association_tracks=extended["tracks"],
        endpoint_source=str(path.relative_to(ROOT)),
        endpoint_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        GPS_used=False,
        future_TLE_used=False,
    )
    write(OUT / f"{case}_{method}_{arm}.json", result)
    print(
        case,
        method,
        arm,
        {k: v for k, v in result["association"].items() if k != "associated_observation_ids"},
        "curved failures",
        len(result["calibration_gate_failures"]),
        flush=True,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=("DS23-0342", "DS23-0039"))
    parser.add_argument(
        "--method",
        required=True,
        choices=("ALGO01", "greedy_graph_repair", "joint_paths", "satellite_EM"),
    )
    parser.add_argument("--arm", required=True, choices=("c0", "fitted_c"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    run(args.case, args.method, args.arm)
