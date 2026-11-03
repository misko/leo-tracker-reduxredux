"""Bounded paired identity proposals on the 71-percent retained observation set."""

from concurrent.futures import ProcessPoolExecutor
import argparse
import copy

import numpy as np

from algo02_scan import pair_passes
from debug_ds23_0268_visibility_reentry import OUT, apply_nominations
from investigate_ds23_0268_remaining_tracks import load, fine_receiver_basis
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import refit
from run_algo01_ds23_sample import ROOT, read, write, sha


def split_rx1_predictive(entries, tracks, new_candidate_index):
    changed = copy.deepcopy(entries)
    for entry in changed:
        if entry["norad"] == 53923 and tracks[entry["track_index"]]["receiver"] == 1:
            entry["norad"] = 67953
            entry["candidate_index"] = new_candidate_index
    return changed


def job(name):
    destination = OUT / (name + ".json")
    if destination.exists():
        raise FileExistsError("preserve identity proposal")
    scan, base, saved, _, _ = load()
    selected_path = OUT / "trials/interior_add_66797.json"
    selected = read(selected_path)
    old = context("DS23-0268")[4]
    replacements = [(row["component"], 67953, None) for row in base.rows
        if any(key in row["component"] for key in ("RX1-CH1-T005", "RX1-CH5-T003"))]
    additions = []
    if name.endswith("with_CH2"):
        additions = ["RX1-CH2-T005"]
        candidate = next(r for r in read(ROOT / "reports/2026_10_20_ds23_0268_remaining_tracks/causal_refined.json")["arms"]["c0"]
                         if "RX1-CH2-T005" in r["component"])
        best = next(r["best"] for r in candidate["refined"] if r["best"]["norad"] == 67953)
        replacements.append((candidate["component"], 67953, best["alias"]))
    node, mask, changes = apply_nominations(scan, selected["node"], base, selected["mask"], additions, replacements)
    changed = copy.copy(scan)
    changed.rx_basis = [fine_receiver_basis(t["times"]) for t in scan.tracks]
    hyper = old["hyperparameters_from_pre_RF_TLE_only"]
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, hyper["shrinkage"])
    entries = copy.deepcopy(old["linear_entries"])
    if "all_RX1" in name:
        entries = split_rx1_predictive(entries, scan.tracks, int(np.flatnonzero(scan.norads == 67953)[0]))
    pair = {arm: refit(changed, node, mask, arm, np.asarray(selected["powers"]), means,
                      hyper, saved["events"], entries) for arm in ("c0", "fitted_c")}
    write(destination, dict(name=name, arms=pair, paired_valid=pair_passes(pair, include_linear=True),
        node=node, mask=mask, changes=changes, powers=selected["powers"],
        selected_source_sha256=sha(selected_path), GPS_used=False, future_TLE_used=False,
        original_selected_observation_mask_retained=True, original_predictive_entries_retained=True,
        predictive_entries=entries,
        gates_and_priors_unchanged=True, phase_rounds=5, position_steps_per_round=48,
        cold_start_km=[0, 0], candidate_screen="family-excluded causal whole-catalogue",
        no_candidate_accepted_by_visual_or_GPS_agreement=True))
    print(name, "paired_valid", pair_passes(pair, include_linear=True), flush=True)


def constrained_job(name):
    from ds23_feasible_position import feasible_fit
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from probe_algo03_feasible_recovery import gate_slacks
    from probe_ds23_frequency_events import summary, cached

    source = OUT / (name + ".json")
    destination = OUT / (name + "_constrained.json")
    if destination.exists():
        raise FileExistsError("preserve constrained identity proposal")
    record = read(source)
    scan, _, saved, _, _ = load()
    changed = copy.copy(scan)
    changed.rx_basis = [fine_receiver_basis(t["times"]) for t in scan.tracks]
    old = context("DS23-0268")[4]
    entries = record.get("predictive_entries", old["linear_entries"])
    hyper = old["hyperparameters_from_pre_RF_TLE_only"]
    labels = sorted({r["candidate_index"] for r in record["node"]["seed"]["rows"]})
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, hyper["shrinkage"])
    arms = {}
    for arm in ("c0", "fitted_c"):
        x = np.asarray(record["arms"][arm]["endpoint_east_north_km"])
        reference = np.asarray(record["arms"][arm]["phase_reference"])
        history = []
        for epoch in range(5):
            p = make_event_problem(changed, record["node"], np.asarray(record["mask"], bool),
                arm, reference, np.asarray(record["powers"]), means, hyper, saved["events"])
            attach_event_predictive(p, entries, np.asarray(record["powers"]))
            cached(p)
            if epoch == 0 and abs(p.calculate(x)["negative_twice_elbo"] - record["arms"][arm]["negative_twice_elbo"]) > 1e-3:
                raise ValueError("identity proposal changed before constrained refinement")
            result = feasible_fit(lambda z: p.calculate(z)["negative_twice_elbo"],
                lambda z: np.array(list(gate_slacks(p, z, entries).values())) - .01,
                x, p.lower, p.upper, iterations=40)
            x = np.asarray(result["parameters"])
            phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
            change = float(np.max(abs(phase - p.reference)))
            endpoint = summary(p, x, entries)
            history.append(dict(epoch=epoch, fit=result, phase_change_s=change))
            arms[arm] = dict(endpoint, history=history, final_phase_change_s=change,
                minimum_gate_slack=min(gate_slacks(p, x, entries).values()))
            reference = phase
    result = dict(record, name=name+"_constrained", arms=arms,
        paired_valid=pair_passes(arms, include_linear=True),
        constrained_source_sha256=sha(source), gate_margin=.01,
        constrained_phase_rounds=5, constrained_position_iterations=40)
    write(destination, result)
    print(result["name"], "paired_valid", result["paired_valid"], flush=True)


def replay_proposal(record, arm):
    """Replay changed predictive identities as well as curved nominations."""
    from ds23_frequency_events import make_event_problem, attach_event_predictive
    from probe_ds23_frequency_events import cached

    scan, _, saved, _, _ = load()
    changed = copy.copy(scan)
    changed.rx_basis = [fine_receiver_basis(t["times"]) for t in scan.tracks]
    old = context("DS23-0268")[4]
    hyper = old["hyperparameters_from_pre_RF_TLE_only"]
    labels = sorted({r["candidate_index"] for r in record["node"]["seed"]["rows"]})
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, hyper["shrinkage"])
    result = record["arms"][arm]
    p = make_event_problem(changed, record["node"], np.asarray(record["mask"], bool), arm,
        np.asarray(result["phase_reference"]), np.asarray(record["powers"]), means, hyper, saved["events"])
    attach_event_predictive(p, record.get("predictive_entries", old["linear_entries"]), np.asarray(record["powers"]))
    cached(p)
    x = np.asarray(result["endpoint_east_north_km"])
    if abs(p.calculate(x)["negative_twice_elbo"] - result["negative_twice_elbo"]) > 1e-3:
        raise ValueError("changed-identity endpoint does not replay")
    return p, x


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("fit", "constrained", "all_rx1", "constrained_all_rx1"), default="fit")
    stage = parser.parse_args().stage
    with ProcessPoolExecutor(max_workers=2) as pool:
        names = (("selected_split_all_RX1", "selected_split_all_RX1_with_CH2")
                 if stage in ("all_rx1", "constrained_all_rx1") else ("selected_split_RX1", "selected_split_RX1_with_CH2"))
        list(pool.map(constrained_job if stage.startswith("constrained") else job, names))
