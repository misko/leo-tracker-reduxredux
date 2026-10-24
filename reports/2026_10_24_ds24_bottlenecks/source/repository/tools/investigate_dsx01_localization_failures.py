"""Causal, GPS-blind interventions on DSX01's graph localization failures.

GPS is deliberately absent. Family/track deletions are influence diagnostics,
not a production rejection rule or cross-validation estimate. Their original
nuisance design and prior support remain fixed to avoid confounding removal
with loss of the two-channel orbital-support rule.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_frame_joint import conditional_gate
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_exact_mean import exact_conditional_frequency
from dsx01_joint_marginal import JointMarginal
from dsx01_native_drift import smooth_columns
from dsx01_satellite_prior_controls import SatellitePriorControls
from dsx01_structured_joint import eccentricity_bank
from map_dsx01_clean_region import finite_gradient
from prototype_dsx01_continuous_position import latlon
from run_dsx01_clean_region import OUTPUT as CLEAN
from run_dsx01_clean_region import load_scan
from run_dsx01_joint_descent import ARMS, CASES, JointReadGuard, hypothesis_bank

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_dsx01_joint_descent"
OUTPUT = ROOT / "reports/2026_10_18_dsx01_localization_root_cause"
VARIANTS = ("baseline", "drift_1", "phase_3", "bias_3", "orbit_3", "eccentric",
            "native_band", "colored", "independent_bias_300")


class InvestigationGuard(JointReadGuard):
    def check_path(self, path):
        if isinstance(path, (str, bytes)):
            name = str(path)
            if (name.startswith(str(SOURCE) + "/") and Path(name).name == "start_00.json"
                    or name.startswith(str(OUTPUT) + "/") and Path(name).name == "core.json"):
                self.read_paths.add(name)
                return
        super().check_path(path)


def context(case):
    guard = InvestigationGuard(CLEAN)
    guard.install()
    scan, sigma = load_scan(case)
    path = SOURCE / case / "start_00.json"
    record = json.loads(path.read_text())
    nodes, bindings = hypothesis_bank(scan, sigma)
    if record["input_audit"] != json.loads(json.dumps(scan.inference_input_audit)):
        raise ValueError("baseline input audit differs")
    if record["arms"]["c0"]["final_mode"] != record["arms"]["fitted_c"]["final_mode"]:
        raise ValueError("controlled investigation requires matched baseline identities")
    node = nodes[record["arms"]["c0"]["final_mode"]]
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return scan, sigma, node, record, bindings, guard


def covariance_blocks(times, noise, slices, amplitude=150.0, correlation=10.0):
    matrices, volume = [], 0.0
    for sl in slices:
        t = times[sl]
        cov = np.diag(noise[sl] ** 2) + amplitude**2 * np.exp(
            -abs(t[:, None] - t[None, :]) / correlation)
        root = np.linalg.cholesky(cov)
        matrices.append(np.linalg.solve(root, np.eye(len(t))))
        volume += 2 * np.log(np.diag(root) / 40).sum()
    return matrices, float(volume)


class DiagnosticNormal(SatellitePriorControls):
    """Keep the baseline noise law while changing one declared model ingredient."""

    def __init__(self, scan, node, sigma, fitted_c, *, control="baseline", reference=None,
                 keep=None):
        super().__init__(scan, node["seed"], fitted_c, variant="normal", sigma=sigma,
                         reference=reference, aliases=node["aliases"])
        if control not in VARIANTS:
            raise ValueError("unknown controlled intervention")
        self.control = control
        self.keep = (np.ones(len(self.values), dtype=bool) if keep is None
                     else np.asarray(keep, bool))
        if self.keep.shape != self.values.shape or not self.keep.any():
            raise ValueError("nonempty observation mask matching full design required")
        self.ecc_bank, self.ecc_metadata = None, {}
        if control == "eccentric":
            self.ecc_bank, self.ecc_metadata = eccentricity_bank(scan, self.labels, self.supported)
        if control == "native_band":
            rx = np.concatenate([np.full(sl.stop - sl.start, scan.tracks[i]["receiver"])
                                 for i, sl in zip(self.members, self.slices, strict=True)])
            band = np.concatenate([np.full(sl.stop - sl.start, int(scan.tracks[i]["channel"] > 4))
                                   for i, sl in zip(self.members, self.slices, strict=True)])
            self.smooth = smooth_columns(self.flat_times, rx, band, self.q, "native_band")
        self.whiteners, self.noise_volume = [], self.diagonal_logvolume
        if control == "colored":
            if not self.keep.all():
                raise ValueError("colored deletion controls require rebuilding covariance")
            self.whiteners, self.noise_volume = covariance_blocks(
                self.flat_times, self.point_noise, self.slices)
        else:
            self.noise_volume = float(2 * np.log(self.point_noise[self.keep] / 40).sum())

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        features = result["features"]
        if self.ecc_bank is not None:
            modes = paired_frequency_modes(self.sky, self.ecc_bank, self.flat_times,
                                           self.flat_labels, self.reference, *latlon(x[:2]))
            extra = np.zeros((len(self.values), 2 * len(self.supported)))
            for k, j in enumerate(self.supported_local):
                use = self.flat_labels == j
                extra[use, 2 * k:2 * k + 2] = self.q[use, None] * modes[use]
            stop = features.shape[1] - len(self.members)
            features = np.column_stack((features[:, :stop], extra, features[:, stop:]))
        scales = np.ones(features.shape[1])
        nb, ns = self.hardware.shape[1], self.smooth.shape[1]
        if self.control == "drift_1":
            scales[[4, 6]] = 0.1  # 1 Hz/s mean drift, instead of 10 Hz/s.
        elif self.control == "phase_3":
            scales[nb + ns:nb + ns + len(self.labels)] = 3
        elif self.control in ("bias_3", "independent_bias_300"):
            scales[-len(self.members):] = 3 if self.control == "bias_3" else 0.3
        elif self.control == "orbit_3":
            scales[nb + ns + len(self.labels):-len(self.members)] = 3
        raw = self.values - self.q * result["intercept"]
        design, response, noise = features * scales, raw, self.point_noise
        if self.whiteners:
            design, response = design.copy(), raw.copy()
            for sl, w in zip(self.slices, self.whiteners, strict=True):
                design[sl], response[sl] = w @ design[sl], w @ raw[sl]
            noise = np.ones(len(raw))
        bound = hierarchical_bound(response[self.keep], design[self.keep], noise[self.keep],
                                   self.noise_groups[self.keep])
        bound["coefficient"] *= scales
        bound["coefficient_prior_precision"] /= scales**2
        present = np.unique(self.noise_groups[self.keep])
        weights = np.zeros(len(self.members))
        weights[present] = bound["noise_precision"]
        bound["noise_precision"] = weights
        bound["conditional_residual_hz"] = raw - features @ bound["coefficient"]
        if self.whiteners:
            bound["negative_twice_elbo"] += self.noise_volume + 2 * len(raw) * np.log(40)
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.noise_volume)]
        result.update(bound, features=features)
        return result

    def residual(self, x):
        result = self.calculate(x)
        return np.r_[result["residual"], np.maximum(0, -result["elevation"][self.keep]) / 2]


def fit(problem, start=(0.0, 0.0), iterations=48):
    result = bounded_gauss_newton(problem.residual, start, problem.lower, problem.upper,
                                 iterations=iterations)
    calculated = problem.calculate(result["parameters"])
    return dict(result, residual_rms_hz=float(np.sqrt(np.mean(
        calculated["conditional_residual_hz"][problem.keep] ** 2))),
                active_points=int(problem.keep.sum()),
                normalization_constant=calculated["normalization_constant"],
                negative_twice_elbo=calculated["negative_twice_elbo"])


def refreshed(scan, sigma, node, arm, control="baseline", rounds=5):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    reference = np.zeros(len(labels))
    anchor = np.zeros(2)
    history = []
    for epoch in range(rounds):
        p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", control=control,
                             reference=reference)
        result = fit(p, anchor)
        anchor = np.array(result["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(dict(epoch=epoch, fit=result, phase_reference=reference.copy(),
                            posterior_phase_s=phase,
                            max_reference_change_s=float(np.max(abs(phase - reference)))))
        reference = np.clip(phase, -15, 15)
    return p, result, history


def polynomial_fit(times, values, noise, max_degree=4):
    t = np.asarray(times, float)
    z = (t - t.mean()) / max(float(np.ptp(t)), 1)
    choices = []
    for degree in range(1, min(max_degree, len(t) - 3) + 1):
        design = np.polynomial.polynomial.polyvander(z, degree)
        coefficient = np.linalg.lstsq(design / noise[:, None], values / noise, rcond=None)[0]
        r = (values - design @ coefficient) / noise
        choices.append(dict(degree=degree, bic=float(r @ r + (degree + 1) * np.log(len(t))),
                            rms_hz=float(np.sqrt(np.mean((r * noise) ** 2)))))
    return min(choices, key=lambda a: a["bic"])


def track_audit(p, calculated):
    rows = []
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        t = p.scan.tracks[i]
        times, y, noise = t["times"], t["values"], p.point_noise[sl]
        best = polynomial_fit(times, y, noise)
        cuts = []
        # Test archived joins by original observation ownership, never by GPS.
        for piece in t["pieces"][:-1]:
            cut = int(np.searchsorted(times, piece["end_s"], side="right"))
            if min(cut, len(times) - cut) >= 8:
                left = polynomial_fit(times[:cut], y[:cut], noise[:cut])
                right = polynomial_fit(times[cut:], y[cut:], noise[cut:])
                cuts.append(dict(cut=cut, time_s=float(times[cut]),
                                 split_bic=left["bic"] + right["bic"] + 2 * np.log(len(y)),
                                 left_degree=left["degree"], right_degree=right["degree"]))
        r = calculated["conditional_residual_hz"][sl]
        step_tests = []
        centered = r - np.average(r, weights=1 / noise**2)
        rss = float(np.sum((centered / noise) ** 2))
        for cut in range(8, len(r) - 7):
            parts = (slice(0, cut), slice(cut, None))
            means = [float(np.average(r[s], weights=1 / noise[s]**2)) for s in parts]
            energy = sum(float(np.sum(((r[s] - m) / noise[s]) ** 2))
                         for s, m in zip(parts, means, strict=True))
            step_tests.append(dict(cut=cut, time_s=float(times[cut]),
                                   jump_hz=means[1] - means[0],
                                   bic_gain=rss - energy - 3 * np.log(len(r))))
        rows.append(dict(component=t["key"], norad=int(p.rows[k]["candidate_norad"]),
                         receiver=t["receiver"], channel=t["channel"], points=len(times),
                         span_s=float(np.ptp(times)), pieces=len(t["pieces"]),
                         polynomial=best, archived_join_tests=cuts,
                         strongest_residual_step=max(step_tests, key=lambda a: a["bic_gain"])
                         if step_tests else None,
                         rms_hz=float(np.sqrt(np.mean(r**2))),
                         noise_precision=float(calculated["noise_precision"][k]),
                         conditional_gate=conditional_gate(r, times)))
    return rows


def core(case):
    scan, sigma, node, original, bindings, guard = context(case)
    arms, tracks = {}, {}
    for arm in ARMS:
        p, fitted, history = refreshed(scan, sigma, node, arm)
        calculated = p.calculate(fitted["parameters"])
        first = history[0]["fit"]
        replay = abs(first["score"] - original["arms"][arm]["score"])
        if replay > 1e-5:
            raise ValueError(f"baseline did not replay: {replay}")
        exact, _, parameters = exact_conditional_frequency(p, fitted["parameters"])
        tangent, _ = p.conditional_frequency(fitted["parameters"])
        family = []
        for local, j in enumerate(p.labels):
            members = [k for k, r in enumerate(p.rows) if r["candidate_index"] == j]
            use = p.flat_labels == local
            family.append(dict(
                candidate_index=int(j), norad=int(scan.norads[j]),
                points=int(use.sum()), fragments=len(members),
                components=[p.rows[k]["component"] for k in members],
                owners=sorted({(scan.tracks[p.members[k]]["receiver"],
                                scan.tracks[p.members[k]]["channel"]) for k in members}),
                phase_s=float(p.state(fitted["parameters"])["phases"][j]),
                phase_sigma_s=float(p.phase_sigma[local]),
                orbital_parameters=parameters.get(j),
                exact_minus_tangent_rms_hz=float(np.sqrt(np.mean(
                    ((exact - tangent)[use] * p.q[use]) ** 2))),
                residual_rms_hz=float(np.sqrt(np.mean(
                    calculated["conditional_residual_hz"][use] ** 2))),
                TLE_age_hours=(scan.receipt["origin_utc_ns"]
                               - scan.elements[str(int(scan.norads[j]))]["provenance"][
                                   "element_epoch_utc_ns"]) / 3.6e12))
        arms[arm] = dict(baseline=first, refreshed=fitted, phase_rounds=history,
                         families=family, state=p.state(fitted["parameters"]),
                         reference=p.reference,
                         exact_minus_tangent_hz=(exact - tangent) * p.q,
                         residual_hz=calculated["conditional_residual_hz"],
                         noise_precision=calculated["noise_precision"],
                         features=calculated["features"], coefficient=calculated["coefficient"],
                         prior_penalty=calculated["coefficient"]**2,
                         profile_gradient=finite_gradient(
                             lambda x, problem=p: float(problem.residual(x) @ problem.residual(x)),
                             fitted["parameters"]))
        tracks[arm] = track_audit(p, calculated)
    result = dict(case=case, sigma_hz=sigma, arms=arms, track_audits=tracks,
                  tracks=[dict(key=scan.tracks[i]["key"], times=scan.tracks[i]["times"],
                               values=scan.tracks[i]["values"],
                               pieces=scan.tracks[i]["pieces"],
                               receiver=scan.tracks[i]["receiver"],
                               channel=scan.tracks[i]["channel"],
                               observation_ids=scan.tracks[i]["observation_ids"])
                          for i in p.members],
                  rows=p.rows, aliases=p.alias, input_audit=scan.inference_input_audit,
                  bindings=bindings, GPS_used=False, read_paths=sorted(guard.read_paths))
    return result


def ablations(case, kind):
    scan, sigma, node, _, bindings, _ = context(case)
    data = json.loads((OUTPUT / case / "core.json").read_text())
    p0 = DiagnosticNormal(scan, node, sigma, False)
    if kind == "family":
        targets = [(str(int(scan.norads[j])), [k for k, r in enumerate(p0.rows)
                                             if r["candidate_index"] == j]) for j in p0.labels]
    elif kind == "track":
        targets = [(row["component"], [k]) for k, row in enumerate(p0.rows)]
    elif kind == "group":
        targets = [(f"RX{rx}_B{b}", [k for k, i in enumerate(p0.members)
                                     if scan.tracks[i]["receiver"] == rx
                                     and int(scan.tracks[i]["channel"] > 4) == b])
                   for rx in (1, 2) for b in (0, 1)]
        targets += [(f"time_{start}_{start + 100}", []) for start in (0, 100, 200)]
    else:
        raise ValueError("unknown ablation unit")
    rows = []
    for key, members in targets:
        keep = np.ones(len(p0.values), bool)
        for k in members:
            keep[p0.slices[k]] = False
        if key.startswith("time_"):
            _, lo, hi = key.split("_")
            keep[(p0.flat_times >= float(lo)) & (p0.flat_times < float(hi))] = False
        for arm in ARMS:
            for phase in (("zero", "refreshed") if kind == "family" else ("refreshed",)):
                reference = None if phase == "zero" else data["arms"][arm]["reference"]
                p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c",
                                     reference=reference, keep=keep)
                result = fit(p)
                full_reference = (data["arms"][arm]["baseline"] if phase == "zero"
                                  else data["arms"][arm]["refreshed"])
                rows.append(dict(target=key, kind=kind, arm=arm, phase=phase,
                                 deleted_points=int((~keep).sum()),
                                 deleted_components=[p.rows[k]["component"] for k in members],
                                 fit=result,
                                 shift_km=float(np.linalg.norm(np.array(result["parameters"])
                                                              - full_reference["parameters"])),
                                 full_design_prior_support_preserved=True))
        print(case, kind, key, flush=True)
    return dict(case=case, kind=kind, interventions=rows, bindings=bindings, GPS_used=False,
                scores_across_different_observation_masks_not_comparable=True)


def variants(case):
    scan, sigma, node, _, bindings, _ = context(case)
    rows = []
    for name in VARIANTS:
        for arm in ARMS:
            p, result, history = refreshed(scan, sigma, node, arm, name)
            calculated = p.calculate(result["parameters"])
            rows.append(dict(control=name, arm=arm, fit=result, history=history,
                             state=p.state(result["parameters"]) if name != "native_band" else None,
                             conditional_noise_gate_points=sum(
                                 len(scan.tracks[i]["times"])
                                 for i, sl in zip(p.members, p.slices, strict=True)
                                 if conditional_gate(calculated["conditional_residual_hz"][sl],
                                                     scan.tracks[i]["times"])["compatible"]),
                             reference=p.reference))
        print(case, name, flush=True)
    return dict(case=case, interventions=rows, bindings=bindings, GPS_used=False,
                labels_aliases_observations_candidates_matched_across_controls=True)


def numerical_checks(case):
    """Replay endpoint precision updates with 4x budget, without any evaluation site."""
    global hierarchical_bound
    scan, sigma, node, _, bindings, _ = context(case)
    core_record = json.loads((OUTPUT / case / "core.json").read_text())
    bound = hierarchical_bound
    checks = []
    for arm in ARMS:
        saved = core_record["arms"][arm]
        p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", reference=saved["reference"])
        x = saved["refreshed"]["parameters"]
        first = p.calculate(x)
        try:
            hierarchical_bound = partial(bound, iterations=1024)
            second = p.calculate(x)
        finally:
            hierarchical_bound = bound
        checks.append(dict(
            arm=arm, default_precision_iterations=first["precision_iterations"],
            default_log_precision_change=first["final_log_precision_change"],
            extended_precision_iterations=second["precision_iterations"],
            extended_log_precision_change=second["final_log_precision_change"],
            extended_minus_default_ELBO=(second["negative_twice_elbo"]
                                         - first["negative_twice_elbo"]),
            max_noise_precision_change=float(np.max(abs(second["noise_precision"]
                                                        - first["noise_precision"]))),
            outer_stop=saved["refreshed"]["stopped"],
            final_phase_reference_change_s=saved["phase_rounds"][-1]["max_reference_change_s"],
            profile_gradient=saved["profile_gradient"]))
    return dict(case=case, GPS_used=False, checks=checks, source_bindings=bindings,
                default_budget=256, extended_budget=1024)


def job(case, stage):
    out = OUTPUT / case / f"{stage}.json"
    if out.exists():
        return
    mark = time.monotonic()
    result = (core(case) if stage == "core" else variants(case) if stage == "variants"
              else numerical_checks(case) if stage == "numerical_checks"
              else ablations(case, stage))
    result.update(seconds=time.monotonic() - mark, source_sha256=hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest(), status="complete")
    out.parent.mkdir(parents=True, exist_ok=True)
    write(out, result)


def campaign(stages, workers):
    OUTPUT.mkdir(parents=True, exist_ok=True)

    def one(case, stage):
        log = OUTPUT / f"{case}_{stage}.log"
        with log.open("w") as handle:
            p = subprocess.run([sys.executable, __file__, "--case", case, "--stage", stage],
                               stdout=handle, stderr=subprocess.STDOUT, check=False,
                               env=dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                                        PYTHONPATH="src:tools"))
        return dict(case=case, stage=stage, returncode=p.returncode, log=str(log))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, case, stage) for stage in stages for case in CASES]
        for f in as_completed(futures):
            row = f.result()
            print(json.dumps(row), flush=True)
            if row["returncode"]:
                raise RuntimeError(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--stage", choices=("core", "family", "track", "group", "variants",
                                           "numerical_checks"),
                        default="core")
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    if args.case:
        job(args.case, args.stage)
    else:
        campaign((args.stage,), args.workers)
