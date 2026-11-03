"""Carry multi-peak arc repairs into full-scan, regional-box position fits.

No evaluation coordinate is present. Initial identities come from saved causal
RF discovery, never a hand-written satellite list. Evaluation is a separate tool.
"""

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from evaluate_ds23_arc_variants import CASES, describe
from evaluate_ds23_arc_variants import OUT as ARCS
from evaluate_ds23_phase_refreshed import FreshScan
from investigate_ds23_adaptive_failures import PRIOR_INPUTS, SOURCE, phase_widths
from investigate_dsx01_localization_failures import DiagnosticNormal, fit
from prototype_dsx01_continuous_position import CENTER, latlon
from run_dsx01_clean_region import zero_state

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.retained_track_likelihood import (
    PERIOD,
    projected_receiver_basis,
    whitening,
)
from leo.analysis.research.visible_arc_variants import (
    em_association,
    frequency,
    graph_proposals,
    greedy_repair,
    joint_selection,
    make_hypotheses,
    wrap,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/2026_10_18_ds23_arc_positions"
METHODS = ("baseline", "greedy_graph_repair", "joint_paths", "satellite_EM")


def read(path):
    return json.loads(path.read_text())


def secondary_noise(metadata, margin):
    if metadata["extra_parameter_BIC_gain"] <= 0:
        return float(metadata["constant_radio_sigma_hz"])
    return float(
        np.sqrt(
            metadata["floor_sigma_hz"] ** 2 + metadata["strength_hz2"] / max(float(margin), 1e-8)
        )
    )


def removed_target(track, case):
    channel, lo, hi = CASES[case]
    t = np.asarray(track["times"])
    return (
        track["receiver"] == 1
        and track["channel"] == channel
        and np.mean((t >= lo) & (t <= hi)) >= 0.5
    )


def alias_from_receiver_gauge(values, predicted, receiver_offset):
    """Integer alias only; receiver gauge comes from other radio tracks."""
    return int(
        np.rint(np.mean(np.asarray(predicted) + receiver_offset - np.asarray(values)) / PERIOD)
    )


def regional_receiver_gauges(scan, rows, aliases, excluded, case):
    offsets = {}
    by_key = {t["key"]: t for t in scan.tracks}
    for row in rows:
        track = by_key[row["component"]]
        if row["component"] in excluded or removed_target(track, case):
            continue
        j = row["candidate_index"]
        bank = dict(
            time_s=scan.sky["time_s"],
            position_km=scan.sky["position_km"][[j]],
            velocity_km_s=scan.sky["velocity_km_s"][[j]],
        )
        f, _ = paired_phase_frequency(
            bank, track["times"], np.zeros(len(track["times"]), int), np.zeros(1), *CENTER
        )
        delta = track["values"] + aliases[row["component"]] * PERIOD - track["rf_hz"] / 11.5e9 * f
        group = track["receiver"], int(track["channel"] > 4)
        offsets.setdefault(group, []).append(float(np.mean(delta)))
    return {group: float(np.median(values)) for group, values in offsets.items()}


def raw_track(case, method, number, source_track, document, scan, original_ids):
    """Only integer alias choices use the earlier fit; CFO samples are unchanged."""
    ix = np.asarray(source_track["indices"], int)
    times = np.asarray(document["times"])[ix]
    observed = np.array([document["candidates"][i]["cfo_hz"] for i in ix])
    prediction = frequency(
        scan.sky,
        source_track["candidate_index"],
        times,
        source_track["orbit"]["parameters"],
        document["site"],
        document["rf_hz"],
    )
    prediction += np.asarray(document["radio_hz"])[ix]
    lifted = prediction + wrap(observed - prediction)
    gauge = int(np.floor((lifted[0] + PERIOD / 2) / PERIOD))
    values = lifted - gauge * PERIOD
    if not np.allclose(
        (values - observed) / PERIOD, np.rint((values - observed) / PERIOD), atol=1e-8
    ):
        raise ValueError("a repaired CFO is not an integer alias of the raw measurement")
    ids = []
    for i in ix:
        peak = document["candidates"][i]
        if i in document["winners"]:
            ids.append(original_ids[peak["probe"]])
        else:
            identity = f"{case}:probe:{peak['probe']}:rank:{peak['rank']}:canonical-v1"
            ids.append("sha256:" + hashlib.sha256(identity.encode()).hexdigest())
    key = f"{case}-MULTIPEAK-{method}-{number:03}"
    return dict(
        key=key,
        receiver=1,
        channel=CASES[case][0],
        rf_hz=document["rf_hz"],
        bank="CH1-4",
        times=times,
        values=values,
        observation_ids=ids,
        start_s=float(times[0]),
        end_s=float(times[-1]),
        pieces=[],
        quality_status="no_structure_detected",
        source_canonical_indices=ix,
        candidate_index=source_track["candidate_index"],
    )


def install_tracks(scan, tracks, rows):
    scan.tracks = tracks
    keys = {row["component"] for row in rows}
    scan.curved = [i for i, t in enumerate(tracks) if t["key"] in keys]
    scan.times = np.unique(np.concatenate([t["times"] for t in tracks]))
    scan.index = [np.searchsorted(scan.times, t["times"]) for t in tracks]
    scan.groups = [(tracks[i]["key"], [tracks[i]]) for i in scan.curved]
    scan.geometry = prepare_phase_geometry(scan.sky, scan.times)
    scan.white = [whitening(t["times"]) for t in tracks]
    scan.ou = [
        whitening(t["times"], correlated_sigma_hz=150.0, correlation_seconds=10.0) for t in tracks
    ]
    scan.rx_basis = [projected_receiver_basis(t["times"]) for t in tracks]
    ids = [oid for i in scan.curved for oid in tracks[i]["observation_ids"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate physical observation ownership in position input")


def build(case, method, association_document=None, confident=False):
    """Use one common c=0 association snapshot for a controlled paired-c position fit."""
    if confident and method != "satellite_EM":
        raise ValueError("the conditional posterior policy applies only to satellite_EM")
    scan = FreshScan(SOURCE / case, noise_mode="radio")
    scan.previous_tle_path = PRIOR_INPUTS / case / "previous.tle"
    scan.receipt = read(PRIOR_INPUTS / case / "receipt.json")
    original = read(SOURCE / case / "fit_radio_noise.json")
    winner = next(
        c for c in original["choices"] if c["hypothesis"] == original["selected_hypothesis"]
    )
    base_rows = copy.deepcopy(winner["node"]["seed"]["rows"])
    aliases = {r["component"]: a for r, a in zip(base_rows, winner["node"]["aliases"], strict=True)}
    failed = {
        r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"] if not r["compatible"]
    }
    document = (
        read(ARCS / f"{case}_c0.json") if association_document is None else association_document
    )
    receiver_gauges = regional_receiver_gauges(scan, base_rows, aliases, failed, case)
    primary = document["results"]["greedy_graph_repair" if method == "baseline" else method]
    if method == "satellite_EM" and not confident:
        primary = primary["map_assignment_result"]
    scale_labels = sorted({t["candidate_index"] for t in primary["tracks"]})
    if method == "baseline":
        rows = base_rows
        selected = scan.tracks
        new_tracks = []
    else:
        result = document["results"][method]
        if method == "satellite_EM" and not confident:
            result = result["map_assignment_result"]
        old_by_key = {t["key"]: t for t in scan.tracks}
        rows = [
            r
            for r in base_rows
            if r["component"] not in failed and not removed_target(old_by_key[r["component"]], case)
        ]
        selected = [t for t in scan.tracks if not removed_target(t, case)]
        raw = read(SOURCE / case / "tracking.json")
        probe_ids = {
            (p["receiver_id"], p["valid_start_counter"]): i for i, p in enumerate(raw["probes"])
        }
        original_ids = {
            probe_ids[o["native_receiver_id"], o["valid_start_counter"]]: o["observation_id"]
            for o in read(SOURCE / case / "observations.json")
        }
        new_tracks = []
        for number, t in enumerate(result["tracks"]):
            track = raw_track(case, method, number, t, document, scan, original_ids)
            new_tracks.append(track)
            j = track["candidate_index"]
            rows.append(
                dict(
                    component=track["key"],
                    candidate_index=j,
                    candidate_norad=int(scan.norads[j]),
                    active_curvature=True,
                    points=len(track["times"]),
                    compatible=True,
                )
            )
            for i, oid in zip(t["indices"], track["observation_ids"], strict=True):
                if oid not in scan.fixed_window_noise["per_observation_noise_sigma_hz"]:
                    scan.fixed_window_noise["per_observation_noise_sigma_hz"][oid] = (
                        secondary_noise(
                            scan.fixed_window_noise, document["candidates"][i]["margin"]
                        )
                    )
        selected = selected + new_tracks
    install_tracks(scan, selected, rows)
    state = zero_state(scan)
    base = dict(rows=rows, state=state)
    # Preserve the existing receiver's frequency gauge. Estimate it only from
    # other curves at the regional center, not from a previous position solution.
    repaired_aliases = {}
    for track in new_tracks:
        j = track["candidate_index"]
        one = dict(
            time_s=scan.sky["time_s"],
            position_km=scan.sky["position_km"][[j]],
            velocity_km_s=scan.sky["velocity_km_s"][[j]],
        )
        f, _ = paired_phase_frequency(
            one, track["times"], np.zeros(len(track["times"]), int), np.zeros(1), *CENTER
        )
        group = track["receiver"], int(track["channel"] > 4)
        repaired_aliases[track["key"]] = alias_from_receiver_gauge(
            track["values"], track["rf_hz"] / 11.5e9 * f, receiver_gauges[group]
        )
    node = dict(
        seed=base,
        aliases=[
            aliases[r["component"]]
            if r["component"] in aliases
            else repaired_aliases[r["component"]]
            for r in rows
        ],
    )
    kept = np.concatenate(
        [
            np.full(len(scan.tracks[i]["times"]), rows[k]["component"] not in failed)
            for k, i in enumerate(scan.curved)
        ]
    )
    return (
        scan,
        node,
        kept,
        scale_labels,
        dict(
            failed_components=sorted(failed),
            replaced_components=[
                r["component"]
                for r in base_rows
                if removed_target(
                    next(
                        t for t in read(SOURCE / case / "tracks.json") if t["key"] == r["component"]
                    ),
                    case,
                )
            ]
            if method != "baseline"
            else [],
            source_associations=str(ARCS / f"{case}_c0.json"),
            conservative_EM_posterior_threshold=0.8 if confident else None,
            active_points=int(kept.sum()),
            new_track_keys=[t["key"] for t in new_tracks],
            region_center=CENTER,
            region_box_width_km=25.0,
            reference_position_used=False,
            receiver_alias_gauges_hz={
                f"RX{rx}_band{band}": v for (rx, band), v in receiver_gauges.items()
            },
        ),
    )


class PositionNormal(DiagnosticNormal):
    """Original integrated position model, optionally with shared satellite scales."""

    def __init__(self, *args, scale_labels=(), scale_reference=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scale_labels = [j for j in scale_labels if j in self.labels]
        self.scale_reference = (
            np.zeros(len(self.scale_labels))
            if scale_reference is None
            else np.asarray(scale_reference)
        )

    def calculate(self, x):
        if not self.scale_labels:
            return super().calculate(x)
        result = JointMarginal.calculate(self, x)
        features = result["features"].copy()
        intercept = result["intercept"].copy()
        scales = np.zeros((len(self.values), len(self.scale_labels)))
        start = self.hardware.shape[1] + self.smooth.shape[1]
        for k, j in enumerate(self.scale_labels):
            local = self.labels.index(j)
            use = self.flat_labels == local
            ref = float(self.scale_reference[k])
            scales[use, k] = self.q[use] * result["frequency"][use] * 0.005
            features[use, start + local] *= 1 + ref
            intercept[use] -= ref * result["derivative"][use] * self.reference[local]
        stop = features.shape[1] - len(self.members)
        features = np.column_stack((features[:, :stop], scales, features[:, stop:]))
        raw = self.values - self.q * intercept
        bound = hierarchical_bound(
            raw[self.keep],
            features[self.keep],
            self.point_noise[self.keep],
            self.noise_groups[self.keep],
        )
        present = np.unique(self.noise_groups[self.keep])
        weights = np.zeros(len(self.members))
        weights[present] = bound["noise_precision"]
        bound["noise_precision"] = weights
        bound["conditional_residual_hz"] = raw - features @ bound["coefficient"]
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.noise_volume)]
        result.update(bound, features=features, intercept=intercept)
        return result

    def scale_state(self, x):
        if not self.scale_labels:
            return np.zeros(0)
        a = self.calculate(x)["coefficient"]
        end = len(a) - len(self.members)
        return a[end - len(self.scale_labels) : end] * 0.005


def fit_position(
    scan, node, keep, scale_labels, arm, model, start=(0.0, 0.0), rounds=5, iterations=48
):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    widths, width_receipt = phase_widths(scan, labels)
    phase = np.zeros(len(labels))
    active_scale = [j for j in scale_labels if j in labels] if model == "shared_scale" else []
    reference_scale = np.zeros(len(active_scale))
    anchor = np.asarray(start, float)
    history = []
    for epoch in range(rounds):
        p = PositionNormal(
            scan,
            node,
            scan.radio_sigma_hz,
            arm == "fitted_c",
            reference=phase,
            keep=keep,
            scale_labels=active_scale,
            scale_reference=reference_scale,
        )
        p.phase_sigma = widths
        result = fit(p, anchor, iterations=iterations)
        anchor = np.asarray(result["parameters"])
        posterior_phase = p.state(anchor)["phases"][p.labels]
        posterior_scale = p.scale_state(anchor)
        history.append(
            dict(
                epoch=epoch,
                fit=result,
                phase_reference=phase,
                scale_reference=reference_scale,
                max_phase_change_s=float(max(abs(posterior_phase - phase))),
                max_scale_change=float(max(abs(posterior_scale - reference_scale), default=0)),
            )
        )
        phase = np.clip(posterior_phase, -15, 15)
        reference_scale = posterior_scale
    c = p.calculate(anchor)
    rows = []
    for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
        r = c["conditional_residual_hz"][sl]
        rows.append(
            dict(
                component=row["component"],
                norad=row["candidate_norad"],
                candidate_index=row["candidate_index"],
                points=int(p.keep[sl].sum()),
                residual_rms_hz=float(np.sqrt(np.mean(r * r))),
                noise_precision=float(c["noise_precision"][p.noise_groups[sl.start]]),
                observation_ids=scan.tracks[i]["observation_ids"],
            )
        )
    state = p.state(anchor)
    state["satellite_scales"] = {
        int(j): float(v) for j, v in zip(p.scale_labels, p.scale_state(anchor), strict=True)
    }
    record = dict(
        fit=result,
        history=history,
        endpoint_east_north_km=anchor,
        endpoint_latlon=latlon(anchor),
        state=state,
        phase_reference=p.reference,
        scale_reference=p.scale_reference,
        phase_widths_s=widths,
        phase_width_receipt=width_receipt,
        scales={
            str(int(scan.norads[j])): float(v)
            for j, v in zip(p.scale_labels, p.scale_state(anchor), strict=True)
        },
        active_points=int(keep.sum()),
        tracks=rows,
        rows=p.rows,
        aliases=p.alias,
        frequency_rms_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep] ** 2))),
        score=float(p.residual(anchor) @ p.residual(anchor)),
        noise_precision=c["noise_precision"],
        phase_rounds=rounds,
        scale_sigma=0.005 if active_scale else None,
        scale_gaussian_not_hard_truncated=True,
        max_last_phase_change_s=history[-1]["max_phase_change_s"],
        max_last_scale_change=history[-1]["max_scale_change"],
    )
    return p, record


def run(case, method, arm, model, confident=False):
    directory = OUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{model}_{arm}{'_confident' if confident else ''}.json"
    began = time.monotonic()
    scan, node, keep, labels, receipt = build(case, method, confident=confident)
    p, record = fit_position(scan, node, keep, labels, arm, model)
    record.update(
        case=case,
        method=method,
        arm=arm,
        model=model,
        input_receipt=receipt,
        input_tracks=scan.tracks,
        seconds=time.monotonic() - began,
        GPS_used=False,
        future_TLE_used=False,
        position_start=[0.0, 0.0],
        satellite_identities_fixed_in_this_propagation=True,
        conservative_EM_posterior_threshold=0.8 if confident else None,
    )
    write(path, record)
    print(
        case,
        method,
        arm,
        model,
        record["endpoint_east_north_km"],
        record["frequency_rms_hz"],
        record["seconds"],
        flush=True,
    )


def refreshed_targets(case, method, arm, model, rounds=3):
    """Alternate repaired-lane associations and full-scan position updates."""
    if method == "baseline":
        raise ValueError("target refresh requires one of the three repair variants")
    directory = OUT / case / method
    current = read(directory / f"{model}_{arm}.json")
    document = read(ARCS / f"{case}_c0.json")
    fixed_candidates = copy.deepcopy(document["candidates"])
    full_history = []
    previous_signature = None
    began = time.monotonic()
    for epoch in range(rounds):
        scan, _, _, _, _ = build(case, method)
        t = np.asarray(document["times"])
        raw = np.array([p["cfo_hz"] for p in fixed_candidates])
        state = current["state"]
        dummy = dict(
            receiver=1, channel=CASES[case][0], rf_hz=document["rf_hz"], times=t, bank="CH1-4"
        )
        radio = scan.hardware(dummy, np.asarray(state["beta"]))
        radio += (
            document["rf_hz"]
            / 11.5e9
            * projected_receiver_basis(t)
            @ np.asarray(state["smooth"])[0]
        )
        data = dict(
            times=t,
            values=wrap(raw - radio),
            radio_hz=radio,
            probes=np.asarray(document["probes"]),
            quality=np.asarray(document["quality"]),
            rf_hz=document["rf_hz"],
            sigma=scan.radio_sigma_hz,
            site=latlon(current["endpoint_east_north_km"]),
        )
        nominal, elevation, derivative = phase_linear_frequency(
            prepare_phase_geometry(scan.sky, t), *data["site"], rf_hz=data["rf_hz"]
        )
        paths = graph_proposals(t, data["values"])
        hypotheses, attempts = make_hypotheses(
            scan.sky, data, nominal, derivative, elevation, paths
        )
        if method == "greedy_graph_repair":
            result = greedy_repair(scan.sky, data, hypotheses)
        else:
            result, pool, choices = joint_selection(scan.sky, data, hypotheses)
            if method == "satellite_EM":
                result = em_association(scan.sky, data, pool, choices)
        winners = np.asarray(document["winners"])
        result = describe(result, scan, data, fixed_candidates, winners)
        selected = result["map_assignment_result"] if method == "satellite_EM" else result
        signature = sorted((h["candidate_index"], tuple(h["indices"])) for h in selected["tracks"])
        document = dict(
            document,
            site=data["site"],
            values=data["values"],
            radio_hz=radio,
            results={method: result},
            candidates=fixed_candidates,
        )
        updated, node, keep, labels, receipt = build(case, method, document)
        _, fitted = fit_position(
            updated, node, keep, labels, arm, model, start=current["endpoint_east_north_km"]
        )
        full_history.append(
            dict(
                epoch=epoch,
                association_site=data["site"],
                association=result,
                attempts=attempts,
                input_receipt=receipt,
                fit=fitted,
                membership_stable=signature == previous_signature,
                position_change_km=float(
                    np.linalg.norm(
                        np.asarray(fitted["endpoint_east_north_km"])
                        - current["endpoint_east_north_km"]
                    )
                ),
            )
        )
        previous_signature = signature
        current = fitted
        if full_history[-1]["membership_stable"] and full_history[-1]["position_change_km"] < 0.001:
            break
    output = dict(
        current,
        case=case,
        method=method,
        arm=arm,
        model=model,
        target_refresh_history=full_history,
        seconds=time.monotonic() - began,
        GPS_used=False,
        future_TLE_used=False,
        target_associations_refreshed=True,
        remaining_scan_nominations_fixed=True,
        cold_position_start=[0.0, 0.0],
        input_tracks=updated.tracks,
    )
    write(directory / f"{model}_{arm}_refreshed.json", output)
    print(
        case,
        method,
        arm,
        model,
        "refreshed",
        current["endpoint_east_north_km"],
        "rounds",
        len(full_history),
        "points",
        current["active_points"],
        flush=True,
    )


def influence(case, arm):
    """Leave-added-track-out diagnostics; never choose an exclusion using GPS."""
    scan, node, keep, labels, receipt = build(case, "greedy_graph_repair")
    by_key = {t["key"]: t for t in scan.tracks}
    counts = [len(by_key[r["component"]]["times"]) for r in node["seed"]["rows"]]
    edges = np.r_[0, np.cumsum(counts)]
    slices = {
        r["component"]: slice(a, b)
        for r, a, b in zip(node["seed"]["rows"], edges[:-1], edges[1:], strict=True)
    }
    results = []
    targets = [([key], key) for key in receipt["new_track_keys"]]
    targets.append((receipt["new_track_keys"], "all_new_tracks"))
    for dropped, name in targets:
        retained = keep.copy()
        for key in dropped:
            retained[slices[key]] = False
        _, result = fit_position(scan, node, retained, labels, arm, "native")
        results.append(
            dict(
                dropped=dropped,
                label=name,
                fit=result,
                nuisance_design_and_prior_support_preserved=True,
            )
        )
    write(
        OUT / case / f"added_track_influence_{arm}.json",
        dict(
            case=case,
            arm=arm,
            results=results,
            GPS_used=False,
            role="Influence diagnostics only; no GPS-selected production rejection.",
        ),
    )
    print(case, arm, "influences finished", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=list(CASES), required=True)
    parser.add_argument("--method", choices=list(METHODS), required=True)
    parser.add_argument("--arm", choices=["c0", "fitted_c"], required=True)
    parser.add_argument("--model", choices=["native", "shared_scale"], required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--influence", action="store_true")
    parser.add_argument("--confident", action="store_true")
    args = parser.parse_args()
    if args.confident and (args.method != "satellite_EM" or args.refresh or args.influence):
        parser.error("--confident is only supported for the fixed EM propagation control")
    if args.influence:
        influence(args.case, args.arm)
    elif args.refresh:
        refreshed_targets(args.case, args.method, args.arm, args.model)
    else:
        run(args.case, args.method, args.arm, args.model, args.confident)
