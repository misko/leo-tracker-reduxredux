"""Cold phase-refreshed graph localization on a presealed random DS23 sample.

Only existing GLRT CFO contracts are used: no IQ collection, result-driven
sample changes, GPS inputs or following elements. A fixed 150-Hz control and
radio-only learned noise are paired; DSX01's GLRT300 scatter is unavailable.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_frame_joint import actual_metrics
from compare_dsx01_retention_localization import Scan
from dsx01_inference_audit import InferenceReadGuard, validate_elements
from evaluate_ds22_merged_tracks import CONFIG, TrackConfig, winners
from evaluate_ds22_public_tracks import graph_rf_lanes
from investigate_dsx01_localization_failures import DiagnosticNormal, fit, refreshed
from iterate_dsx01_profiled_identity import explore
from localize_merged_track_catalogue import raw_curvature
from prototype_dsx01_continuous_position import CENTER, latlon
from run_dsx01_clean_region import fresh_discovery, zero_state
from run_dsx01_joint_descent import ARMS, signature
from sgp4.exporter import export_tle

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.public_tracking_points import public_tracking_points
from leo.analysis.research.retained_track_likelihood import (
    profile,
    projected_receiver_basis,
    whitening,
)
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
DATASET = ROOT / "reports/2026_10_18_ds23_post_ds22"
PROPOSAL_POINTS = ((0., 0.), (-12.5, -12.5), (-12.5, 12.5), (12.5, -12.5), (12.5, 12.5))
NOISE_HZ = 150.


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_bank(directory, tracks, metadata):
    """Broad regional latest/previous causal catalogue; no identity whitelist."""
    import analyze_dsx01_fixed_site as matching

    cutoff, origin = metadata["causal_cutoff_utc_ns"], metadata["anchor_utc_ns"]
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = [s for s in reader.list_snapshots("space-track")
                 if cutoff - 172800_000_000_000 <= s.collected_utc_ns <= cutoff]

    class Recent:
        def list_snapshots(self, provider):
            return tuple(snapshots)

        def read(self, snapshot):
            return reader.read(snapshot)

    causal = causal_catalogue(Recent(), cutoff)
    catalogue = causal.catalogue
    duration = max(300., max(float(t["times"][-1]) for t in tracks))
    grid = np.arange(-17., np.ceil(duration) + 18)
    coarse = np.arange(0., duration + 5, 5.)
    p, v, good = matching.ecef_states(catalogue, origin, coarse)
    _, elevation, _, _ = look_angles(p, v, geodetic_to_ecef_km(37.5, -122., 0.),
                                     ecef_to_enu_matrix(37.5, -122.))
    selected = np.flatnonzero(good & (elevation.max(axis=1) >= -12))
    if not len(selected):
        raise ValueError("no regional causal candidates")
    chosen = ElementSetCatalogue(tuple(catalogue.names[i] for i in selected),
                                 tuple(catalogue.satellite_numbers[i] for i in selected),
                                 tuple(catalogue.satellites[i] for i in selected))
    p, v, good = matching.ecef_states(chosen, origin, grid)
    if not good.all():
        raise ValueError("causal state bank propagation failed")
    np.savez_compressed(directory / "bank.npz", time_s=grid, position_km=p, velocity_km_s=v,
                        norad=np.array(chosen.satellite_numbers),
                        phase_sigma_s=np.ones(len(chosen)))
    elements = {}
    latest_text = ""
    for local, original in enumerate(selected):
        name, satellite = chosen.names[local], chosen.satellites[local]
        lines = export_tle(satellite)
        record = dict(lines=list(lines), provenance=causal.provenance[int(original)])
        validate_elements(record, cutoff)
        elements[str(chosen.satellite_numbers[local])] = record
        latest_text += f"0 {name}\n{lines[0]}\n{lines[1]}\n"
    (directory / "selected.tle").write_text(latest_text)
    # Select an earlier distinct epoch for each candidate, using only the same
    # pre-scan archive. It sets an uncertainty direction, never a future mean.
    lookup, old = set(chosen.satellite_numbers), {}
    for snapshot in snapshots:
        cat = parse_element_sets(reader.read(snapshot))
        for name, n, satellite, epoch in zip(cat.names, cat.satellite_numbers, cat.satellites,
                                              cat.element_epoch_utc_ns(), strict=True):
            if n not in lookup or epoch >= elements[str(n)]["provenance"]["element_epoch_utc_ns"]:
                continue
            if epoch > cutoff:
                continue
            key = (int(epoch), snapshot.collected_utc_ns)
            if n not in old or key > old[n][0]:
                old[n] = key, name, satellite, snapshot
    text, provenance = "", {}
    for n, (key, name, satellite, snapshot) in sorted(old.items()):
        lines = export_tle(satellite)
        text += f"0 {name}\n{lines[0]}\n{lines[1]}\n"
        provenance[str(n)] = dict(epoch_utc_ns=key[0], collected_utc_ns=key[1],
                                  snapshot_digest=snapshot.digest)
    if not old:
        raise ValueError("no previous causal catalogue; cannot replay declared orbit priors")
    (directory / "previous.tle").write_text(text)
    write(directory / "previous_receipt.json", dict(
        sources=provenance, catalogue_sha256=sha(directory / "previous.tle")))
    receipt = dict(origin_utc_ns=origin, cutoff_utc_ns=cutoff, regional_center=[37.5, -122.],
                   radius_km=250., reference_position_used=False, candidate_count=len(chosen),
                   bank_sha256=sha(directory / "bank.npz"),
                   latest_tle_sha256=sha(directory / "selected.tle"),
                   previous_tle_sha256=sha(directory / "previous.tle"),
                   latest_max_epoch_utc_ns=max(r["provenance"]["element_epoch_utc_ns"]
                                               for r in elements.values()),
                   latest_max_collection_utc_ns=max(r["provenance"]["collected_utc_ns"]
                                                    for r in elements.values()),
                   previous_count=len(old),
                   candidate_filter="regional elevation >= -12deg; no whitelist",
                   search_center=CENTER, search_box_width_km=25., snapshot_count=len(snapshots))
    write(directory / "nominal_elements.json", elements)
    write(directory / "receipt.json", receipt)


def prepare(case):
    directory = OUTPUT / case
    if (directory / "prepared.json").exists():
        return
    source = json.loads((directory / "input_receipt.json").read_text())
    if source["status"] != "exported":
        write(directory / "prepared.json", dict(case=case, status="input_unavailable",
                                                source=source))
        return
    raw = (directory / "tracking.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["tracking_sha256"]:
        raise ValueError("tracking snapshot changed")
    document = json.loads(raw)
    rows, metadata = (winners(document) if source["adapter"] == "fast_tracking_contract"
                      else public_tracking_points(document))
    cfg = TrackConfig(**json.loads(CONFIG.read_text())["config"])
    tracks, count = graph_rf_lanes(rows, case, cfg)
    write(directory / "observations.json", rows)
    write(directory / "tracks.json", tracks)
    ncurved = sum(raw_curvature(dict(times=np.array(t["times"]), values=np.array(t["values"])))
                  for t in tracks)
    if not ncurved:
        write(directory / "prepared.json", dict(case=case, status="no_active_curvature",
                                                points=len(rows), graph_tracks=len(tracks)))
        return
    prepare_bank(directory, tracks, metadata)
    write(directory / "prepared.json", dict(
        case=case, status="prepared", GLRT_points=len(rows), graph_points=count,
        graph_tracks=len(tracks), curved_tracks=ncurved, metadata=metadata,
        graph_config_sha256=sha(CONFIG), tracking_sha256=source["tracking_sha256"],
        noise_sigma_hz=NOISE_HZ,
        measurement_transfer="existing fractional GLRT CFO; no DSX01 GLRT300 remeasurement",
        source_sha256=sha(Path(__file__))))
    print(case, "prepared", len(rows), len(tracks), ncurved, flush=True)


class FreshScan(Scan):
    """Same mathematical scan interface, initialized only from this scan's inputs."""

    def __init__(self, directory, noise_mode="fixed150"):
        self.case, self.bank_path, self.recording = directory.name, directory, directory
        self.receipt = json.loads((directory / "receipt.json").read_text())
        if sha(directory / "bank.npz") != self.receipt["bank_sha256"]:
            raise ValueError("state bank changed")
        self.sky = dict(np.load(directory / "bank.npz"))
        self.tracks = json.loads((directory / "tracks.json").read_text())
        for t in self.tracks:
            t["times"], t["values"] = np.array(t["times"]), np.array(t["values"])
        self.curved = [i for i, t in enumerate(self.tracks) if raw_curvature(t)]
        self.times = np.unique(np.concatenate([t["times"] for t in self.tracks]))
        self.index = [np.searchsorted(self.times, t["times"]) for t in self.tracks]
        self.groups = [(self.tracks[i]["key"], [self.tracks[i]]) for i in self.curved]
        self.geometry = prepare_phase_geometry(self.sky, self.times)
        self.norads, self.sigma = self.sky["norad"], self.sky["phase_sigma_s"]
        self.initial = np.zeros(8)
        self.center = self.receipt["regional_center"]
        self.scale = 111.32 * np.cos(np.deg2rad(self.center[0]))
        self.white = [whitening(t["times"]) for t in self.tracks]
        self.ou = [whitening(t["times"], correlated_sigma_hz=150., correlation_seconds=10.)
                   for t in self.tracks]
        self.rx_basis = [projected_receiver_basis(t["times"]) for t in self.tracks]
        self.reference, self.element_derivatives = {}, {}
        self.elements = json.loads((directory / "nominal_elements.json").read_text())
        self.previous_tle_path = directory / "previous.tle"
        for record in self.elements.values():
            validate_elements(record, self.receipt["cutoff_utc_ns"])
        self.fixed_window_noise = dict(extra_parameter_BIC_gain=0,
            per_observation_noise_sigma_hz={oid: NOISE_HZ for t in self.tracks
                                           for oid in t["observation_ids"]})
        self.fixed_window_noise_sha256 = sha(directory / "tracking.json")
        self.radio_sigma_hz = NOISE_HZ
        if noise_mode == "radio":
            self.fixed_window_noise = json.loads((directory / "radio_noise.json").read_text())
            self.radio_sigma_hz = self.fixed_window_noise["constant_radio_sigma_hz"]
            self.fixed_window_noise_sha256 = sha(directory / "radio_noise.json")


class PilotGuard(InferenceReadGuard):
    def check_path(self, path):
        if isinstance(path, (str, bytes)) and str(path).startswith(self.output_root + "/"):
            allowed = {"receipt.json", "bank.npz", "tracks.json", "nominal_elements.json",
                       "previous.tle", "previous_receipt.json", "tracking.json", "radio_noise.json"}
            if Path(str(path)).name not in allowed:
                raise ValueError("inference attempted to read an outcome or undeclared input")
            self.read_paths.add(str(path))
            return
        super().check_path(path)


def extend_associations(p, x, metrics):
    """Attach remaining graph tracks using frozen calibration, never linear votes."""
    scan, state = p.scan, p.state(x)
    accepted = {r["component"]: dict(r, association_source="curved_calibration")
                for r in metrics["tracks"] if r["compatible"]}
    labels = sorted({r["candidate_index"] for r in accepted.values()})
    supported_groups = {(scan.tracks[i]["receiver"], int(scan.tracks[i]["channel"] > 4))
                        for i in p.members if scan.tracks[i]["key"] in accepted}
    predictions, elevations, available = [], [], []
    result = p.calculate(x)
    begin = p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels)
    for j in labels:
        phase = np.array([state["phases"][j]])
        if abs(phase[0]) > 15:
            continue
        bank = dict(time_s=scan.sky["time_s"],
                    position_km=scan.sky["position_km"][[j]],
                    velocity_km_s=scan.sky["velocity_km_s"][[j]])
        local = p.labels.index(j)
        f, e = paired_phase_frequency(bank, scan.times, np.zeros(len(scan.times), int),
                                      phase, *latlon(x))
        if j in p.supported:
            k = p.supported.index(j)
            modes = dict(time_s=p.mode_bank["time_s"],
                         position_km=p.mode_bank["position_km"][3 * local:3 * local + 3],
                         velocity_km_s=p.mode_bank["velocity_km_s"][3 * local:3 * local + 3])
            derivative = paired_frequency_modes(bank, modes, scan.times,
                np.zeros(len(scan.times), int), phase, *latlon(x))
            f += derivative @ result["coefficient"][begin + 3 * k:begin + 3 * k + 3]
        available.append(j)
        predictions.append(f)
        elevations.append(e)
    f, elevation = np.array(predictions), np.array(elevations)
    for i, t in enumerate(scan.tracks):
        if t["key"] in accepted or not available:
            continue
        group = t["receiver"], int(t["channel"] > 4)
        if group not in supported_groups:
            continue
        ix = scan.index[i]
        y = (t["values"] - scan.hardware(t, state["beta"])
             - t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1])
        terms = profile(y, t["rf_hz"] / 11.5e9 * f[:, ix], *scan.white[i])
        noise = batch_noise_screen(terms["innovations"], t["times"])
        good = ((terms["rms"] <= 450) & (abs(terms["bias"]) <= 3000)
                & noise["noise_screen_pass"] & (elevation[:, ix].min(axis=1) >= 0))
        if not good.any():
            continue
        k = int(np.argmin(np.where(good, terms["cost"], np.inf)))
        j = available[k]
        accepted[t["key"]] = dict(component=t["key"], norad=int(scan.norads[j]),
            candidate_index=j, points=len(y), native_rms_hz=float(terms["rms"][k]),
            compatible=True, active_curvature=i in scan.curved,
            association_source="frozen_calibration_extension", bias_hz=float(terms["bias"][k]))
    points = sum(r["points"] for r in accepted.values())
    return dict(accepted_points=points, accepted_tracks=len(accepted),
                accepted_satellites=len({r["candidate_index"] for r in accepted.values()}),
                tracks=list(accepted.values()), linear_tracks_never_calibrate=True,
                original_curved_gate_points=metrics["accepted_points"],
                added_points=points - metrics["accepted_points"])


def fit_case(case, noise_mode="fixed150"):
    directory = OUTPUT / case
    suffix = "_radio_noise" if noise_mode == "radio" else ""
    if (directory / f"fit{suffix}.json").exists():
        return
    prepared = json.loads((directory / "prepared.json").read_text())
    if prepared["status"] != "prepared":
        write(directory / f"fit{suffix}.json", dict(case=case, status=prepared["status"],
                                                   GPS_used=False))
        return
    mark = time.monotonic()
    guard = PilotGuard(directory)
    guard.install()
    scan = FreshScan(directory, noise_mode=noise_mode)
    sigma = scan.radio_sigma_hz
    candidates = fresh_discovery(scan, sigma, budget=4)
    best = min(candidates, key=lambda r: r["center_score"])
    nodes, seen = [], set()
    for candidate in candidates:
        key = signature(candidate)
        if key not in seen:
            nodes.append(candidate)
            seen.add(key)
    for point in PROPOSAL_POINTS[1:]:
        seed, detail = explore(scan, best["seed"]["state"], point, "receiver_smooth",
                               compact_update=False)
        # Fix the native alias at this actual RF-only geographic proposal anchor.
        from iterate_dsx01_position_nominations import AnchoredFamilies

        anchor = AnchoredFamilies(scan, seed, "receiver_smooth", False, point)
        node = dict(seed=seed, aliases=anchor.alias, proposal_point=point,
                    candidate_hypotheses=detail["candidate_hypotheses"])
        key = signature(node)
        if key not in seen:
            nodes.append(node)
            seen.add(key)
    # Bound pilot work using the same c0 center objective, never GPS. Preserve
    # every candidate in the receipt, but fully fit the best three branches.
    scored = []
    for node in nodes:
        cold = dict(seed=dict(rows=node["seed"]["rows"], state=zero_state(scan)),
                    aliases=node["aliases"])
        p = DiagnosticNormal(scan, cold, sigma, False, reference=np.zeros(len({
            r["candidate_index"] for r in cold["seed"]["rows"]})))
        residual = p.residual(np.zeros(2))
        scored.append((float(residual @ residual), cold))
    selected = sorted(scored, key=lambda r: r[0])[:3]
    choices = []
    for index, (score, node) in enumerate(selected):
        pair = {}
        for arm in ARMS:
            p, result, history = refreshed(scan, sigma, node, arm)
            x = result["parameters"]
            legacy = dict(rows=p.rows, state=p.state(x), aliases=p.alias,
                          east_north_km=x, fits=[result])
            metrics = actual_metrics(p, legacy, arm, x)
            extended = extend_associations(p, x, metrics)
            pair[arm] = dict(fit=result, phase_rounds=history, state=p.state(x),
                              reference=p.reference, metrics=metrics,
                              all_graph_associations=extended,
                              profile_gradient=None,
                              conditional_residual_hz=p.calculate(x)["conditional_residual_hz"])
        choices.append(dict(hypothesis=index, center_score=score, node=node, arms=pair))
        write(directory / f"progress{suffix}.json", dict(case=case, choices=choices,
                                                 GPS_used=False, status="running"))
        print(case, "paired phase branch", index, flush=True)
    winner = min(choices, key=lambda r: r["arms"]["c0"]["fit"]["score"])
    zero = {}
    for arm in ARMS:
        p = DiagnosticNormal(scan, winner["node"], sigma, arm == "fitted_c",
                             reference=np.zeros(len({r["candidate_index"]
                                                     for r in winner["node"]["seed"]["rows"]})))
        zero[arm] = fit(p)
    write(directory / f"fit{suffix}.json", dict(
        case=case, status="complete", GPS_used=False, choices=choices,
        selected_hypothesis=winner["hypothesis"], zero_phase_control=zero,
        selection="minimum refreshed c0 full frequency/prior bound; matched branch for fitted c",
        unique_RF_hypotheses=len(scored), fully_fitted_hypotheses=len(selected),
        same_observations_candidates_priors_bounds_and_budgets_in_c_pair=True,
        fresh_radio_seed_budget=4, RF_proposal_points=PROPOSAL_POINTS,
        region_center=CENTER, box_width_km=25., noise_sigma_hz=sigma, noise_mode=noise_mode,
        noise_features_sha256=scan.fixed_window_noise_sha256,
        physical_prior_previous_tle_path=str(scan.previous_tle_path),
        input_read_paths=sorted(guard.read_paths), seconds=time.monotonic() - mark,
        source_sha256=sha(Path(__file__))))


def run(stage, workers, noise_mode="fixed150"):
    entries = json.loads((OUTPUT / "coverage.json").read_text())

    def one(row):
        case = row["case"]
        with (OUTPUT / f"{case}_{stage}_{noise_mode}.log").open("w") as handle:
            process = subprocess.run([sys.executable, __file__, "--case", case, "--stage", stage,
                                      "--noise-mode", noise_mode],
                stdout=handle, stderr=subprocess.STDOUT, check=False,
                env=dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                         PYTHONPATH="src:tools"))
        return dict(case=case, stage=stage, returncode=process.returncode)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in as_completed([pool.submit(one, row) for row in entries]):
            print(json.dumps(result.result()), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case")
    parser.add_argument("--stage", choices=("prepare", "fit"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--noise-mode", choices=("fixed150", "radio"), default="fixed150")
    args = parser.parse_args()
    if args.case:
        if args.stage == "prepare":
            prepare(args.case)
        else:
            fit_case(args.case, args.noise_mode)
    else:
        run(args.stage, args.workers, args.noise_mode)
