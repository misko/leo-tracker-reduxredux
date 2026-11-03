"""Controlled diagnostics on two frozen adaptive scans; never rewrite the pilot.

Reference coordinates enter only labelled diagnostic evaluations. Influence
deletions retain the full nuisance design and causal orbital prior support.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from evaluate_ds23_phase_refreshed import FreshScan
from investigate_dsx01_localization_failures import DiagnosticNormal, fit, refreshed, track_audit
from map_dsx01_clean_region import finite_gradient
from prototype_dsx01_continuous_position import CENTER, latlon
from prototype_s01_causal_shape import previous_bank

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
OUTPUT = ROOT / "reports/2026_10_18_ds23_adaptive_failures"
PRIOR_INPUTS = OUTPUT / "genuine_prior_inputs"
USE_GENUINE_PRIOR = False
REFERENCE = (37.849061591561885, -122.48574968092912)
REFERENCE_XY = np.array([(REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
                         (REFERENCE[0] - CENTER[0]) * 111.0])
ARMS = ("c0", "fitted_c")


def context(case, mode="radio"):
    scan = FreshScan(SOURCE / case, noise_mode=mode)
    if USE_GENUINE_PRIOR:
        scan.previous_tle_path = PRIOR_INPUTS / case / "previous.tle"
        scan.receipt = json.loads((PRIOR_INPUTS / case / "receipt.json").read_text())
    filename = "fit_radio_noise.json" if mode == "radio" else "fit.json"
    original = json.loads((SOURCE / case / filename).read_text())
    winner = next(c for c in original["choices"]
                  if c["hypothesis"] == original["selected_hypothesis"])
    return scan, original, winner


def error_km(x):
    lat, lon = latlon(x)
    a, b = np.deg2rad([lat, REFERENCE[0]])
    h = np.sin((a - b) / 2)**2 + np.cos(a) * np.cos(b) * np.sin(
        np.deg2rad(lon - REFERENCE[1]) / 2)**2
    return float(12742 * np.arcsin(np.sqrt(h)))


def decompose(p, x):
    c = p.calculate(x)
    a = c["coefficient"]
    nb, ns, nl = p.hardware.shape[1], p.smooth.shape[1], len(p.labels)
    prior = a**2 * c["coefficient_prior_precision"]
    blocks = {"offset": slice(0, 4), "drift": slice(4, 8),
              "c": slice(8, nb), "smooth": slice(nb, nb + ns),
              "phase": slice(nb + ns, nb + ns + nl),
              "orbit": slice(nb + ns + nl, len(a) - len(p.members)),
              "fragment": slice(len(a) - len(p.members), len(a))}
    residual = p.residual(x)
    return dict(score=float(residual @ residual), quadratic=c["quadratic"],
                logvolume=c["logvolume"], gamma_cost=c["gamma_cost"],
                prior_cost={k: float(prior[v].sum()) for k, v in blocks.items()},
                RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][p.keep]**2))),
                phase_s=p.state(x)["phases"][p.labels],
                precision_iterations=c["precision_iterations"],
                final_log_precision_change=c["final_log_precision_change"])


def fixed_position(scan, node, arm, point, rounds=5, control="baseline"):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    reference = np.zeros(len(labels))
    for _ in range(rounds):
        p = DiagnosticNormal(scan, node, scan.radio_sigma_hz, arm == "fitted_c",
                             control=control, reference=reference)
        phase = p.state(point)["phases"][p.labels]
        change = float(np.max(abs(phase - reference)))
        reference = np.clip(phase, -15, 15)
    return dict(decompose(p, point), last_phase_change_s=change)


def audit(case):
    started = time.monotonic()
    scan, original, winner = context(case)
    arms = {}
    for arm in ARMS:
        saved = winner["arms"][arm]
        p = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, arm == "fitted_c",
                             reference=np.array(saved["reference"]))
        x = saved["fit"]["parameters"]
        replay = decompose(p, x)
        assert abs(replay["score"] - saved["fit"]["score"]) < 1e-5
        recalculated = p.calculate(x)
        families = []
        for local, j in enumerate(p.labels):
            use = p.flat_labels == local
            rows = [r for r in p.rows if r["candidate_index"] == j]
            n = int(scan.norads[j])
            families.append(dict(norad=n, candidate_index=int(j), points=int(use.sum()),
                                 fragments=len(rows), components=[r["component"] for r in rows],
                                 phase_s=float(p.state(x)["phases"][j]),
                                 TLE_age_hours=(scan.receipt["origin_utc_ns"]
                                     - scan.elements[str(n)]["provenance"]
                                     ["element_epoch_utc_ns"]) / 3.6e12))
        arms[arm] = dict(endpoint=x, error_km=error_km(x), replay=replay,
                         reference=saved["reference"], families=families,
                         gradient_at_endpoint=finite_gradient(
                             lambda xy, problem=p: float(
                                 problem.residual(xy) @ problem.residual(xy)), x),
                         fixed_reference_at_reference_position=decompose(p, REFERENCE_XY),
                         phase_refreshed_at_reference_position=fixed_position(
                             scan, winner["node"], arm, REFERENCE_XY),
                         diagnostic_refit_started_at_reference=fit(p, REFERENCE_XY),
                         track_audit=track_audit(p, recalculated),
                         conditional_residual_hz=recalculated["conditional_residual_hz"],
                         flat_times=p.flat_times, flat_labels=p.flat_labels,
                         original_track_members=p.members,
                         slices=[[s.start, s.stop] for s in p.slices])
    write(OUTPUT / case / "audit.json", dict(case=case, arms=arms, seconds=time.monotonic()-started,
                                            reference_position_diagnostic_only=True))
    print(case, "audit", time.monotonic()-started, flush=True)


def influences(case, kind):
    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    if kind == "family":
        targets = [(str(int(scan.norads[j])), [k for k, r in enumerate(base.rows)
                                              if r["candidate_index"] == j]) for j in base.labels]
    elif kind == "track":
        targets = [(r["component"], [k]) for k, r in enumerate(base.rows)]
    elif kind == "group":
        targets = [(f"RX{rx}", [k for k, i in enumerate(base.members)
                                 if scan.tracks[i]["receiver"] == rx]) for rx in (1, 2)]
        targets += [(f"CH{ch}", [k for k, i in enumerate(base.members)
                                  if scan.tracks[i]["channel"] == ch]) for ch in range(1, 5)]
        targets += [(f"time_{s}", []) for s in (0, 100, 200)]
        failed = {r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"]
                  if not r["compatible"]}
        targets += [("failed_gate", [k for k, r in enumerate(base.rows)
                                     if r["component"] in failed])]
    else:
        raise ValueError(kind)
    results = []
    for target, members in targets:
        keep = np.ones(len(base.values), bool)
        for k in members:
            keep[base.slices[k]] = False
        if target.startswith("time_"):
            s = float(target.split("_")[1])
            keep[(base.flat_times >= s) & (base.flat_times < s + 100)] = False
        if keep.all() or not keep.any():
            continue
        for arm in ARMS:
            saved = winner["arms"][arm]
            p = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, arm == "fitted_c",
                                 reference=np.array(saved["reference"]), keep=keep)
            fitted = fit(p, iterations=32)
            results.append(dict(target=target, arm=arm, deleted_points=int((~keep).sum()),
                                fit=fitted, error_km=error_km(fitted["parameters"]),
                                endpoint_shift_km=float(np.linalg.norm(
                                    np.array(fitted["parameters"]) - saved["fit"]["parameters"])),
                                full_design_prior_support_preserved=True))
        print(case, kind, target, flush=True)
    write(OUTPUT / case / f"{kind}_influence.json", dict(case=case, kind=kind, results=results,
          scores_across_masks_not_comparable=True, labels_and_aliases_fixed=True,
          phase_reference_fixed_to_baseline=True, reference_position_evaluation_only=True))


def controls(case):
    scan, original, winner = context(case)
    results = []
    for name in ("baseline", "drift_1", "phase_3", "orbit_3", "eccentric", "native_band",
                 "colored", "independent_bias_300"):
        for arm in ARMS:
            p, fitted, history = refreshed(scan, scan.radio_sigma_hz, winner["node"], arm, name)
            results.append(dict(control=name, arm=arm, fit=fitted,
                                error_km=error_km(fitted["parameters"]),
                                decomposition=decompose(p, fitted["parameters"]),
                                reference=p.reference,
                                last_phase_change_s=history[-1]["max_reference_change_s"]))
            write(OUTPUT / case / "controls.json", dict(case=case, results=results,
                  observations_labels_aliases_candidates_and_budgets_matched=True,
                  reference_position_evaluation_only=True))
        print(case, "control", name, flush=True)
    write(OUTPUT / case / "controls.json", dict(case=case, results=results,
          observations_labels_aliases_candidates_and_budgets_matched=True,
          reference_position_evaluation_only=True))


def causal_phase_sigma(alignment_s, age_s, epoch_gap_s):
    """Conservative disagreement proxy, not a calibrated probability interval."""
    if not np.isfinite([alignment_s, age_s, epoch_gap_s]).all() or age_s < 0 or epoch_gap_s <= 0:
        raise ValueError("finite causal ages and strictly ordered epochs required")
    return float(np.clip(np.hypot(1., alignment_s * age_s / epoch_gap_s), 1., 15.))


def radio_tail_screen(residual, noise, maximum=6.):
    r, sigma = np.asarray(residual, float), np.asarray(noise, float)
    if (r.ndim != 1 or sigma.shape != r.shape or not len(r)
            or not np.isfinite(r).all() or not np.isfinite(sigma).all()
            or np.any(sigma <= 0) or not np.isfinite(maximum) or maximum <= 0):
        raise ValueError("matching finite residuals and positive independent noise required")
    maximum_z = float(np.max(abs(r) / sigma))
    return dict(passes=maximum_z <= maximum, maximum_standardized_residual=maximum_z)


def polynomial_partition_bic(times, values, noise):
    """Use one common N and an explicit breakpoint parameter penalty."""
    t, y, sigma = np.asarray(times), np.asarray(values), np.asarray(noise)
    n = len(t)

    def part(a, b):
        tt, yy, ss = t[a:b], y[a:b], sigma[a:b]
        z = (tt-tt.mean()) / max(float(np.ptp(tt)), 1.)
        choices = []
        for degree in range(1, min(4, len(tt)//4-1)+1):
            x = np.vander(z, degree+1, increasing=True)
            coefficient = np.linalg.lstsq(x/ss[:, None], yy/ss, rcond=None)[0]
            r = (yy-x@coefficient)/ss
            choices.append(dict(degree=degree, chi2=float(r@r),
                                bic=float(r@r+(degree+1)*np.log(n))))
        return min(choices, key=lambda c: c["bic"])

    rows = []
    for cut in range(8, n-7):
        if min(t[cut-1]-t[0], t[-1]-t[cut]) < 6:
            continue
        left, right = part(0, cut), part(cut, n)
        rows.append(dict(cut=cut, before_s=float(t[cut-1]), after_s=float(t[cut]),
                         left=left, right=right,
                         bic=float(left["bic"]+right["bic"]+np.log(n))))
    return dict(full=part(0, n), splits=sorted(rows, key=lambda r: r["bic"]),
                independent_of_GPS_and_satellites=True, global_N=n,
                one_breakpoint_parameter_penalty="log N", points_per_coefficient=4)


def polynomial_split(case):
    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    k = next(k for k, r in enumerate(base.rows) if "RX1-CH2-T002-" in r["component"])
    track, sl = scan.tracks[base.members[k]], base.slices[k]
    result = polynomial_partition_bic(track["times"], track["values"], base.point_noise[sl])
    result["noise_frozen_from_radio_only_polynomials"] = True
    write(OUTPUT / case / "polynomial_split_bic.json", result)


def phase_widths(scan, labels):
    _, _, alignments = previous_bank(scan, labels, previous_path=scan.previous_tle_path)
    old = json.loads((scan.previous_tle_path.parent / "previous_receipt.json")
                     .read_text())["sources"]
    result, receipt = [], []
    for j in labels:
        norad = str(int(scan.norads[j]))
        epoch = scan.elements[norad]["provenance"]["element_epoch_utc_ns"]
        age = (scan.receipt["origin_utc_ns"] - epoch) / 1e9
        gap = (epoch - old[norad]["epoch_utc_ns"]) / 1e9 if norad in old else None
        alignment = alignments.get(int(norad))
        width = causal_phase_sigma(alignment, age, gap) if alignment is not None else 1.
        result.append(width)
        receipt.append(dict(norad=int(norad), age_s=age, previous_epoch_gap_s=gap,
                            old_new_alignment_s=alignment, sigma_s=width))
    return np.array(result), receipt


class TailDiagnostic(DiagnosticNormal):
    def calculate(self, x):
        from dsx01_hierarchical_bound import hierarchical_bound
        from dsx01_satellite_prior_controls import orbital_prior_groups

        result = super().calculate(x)
        features = result["features"]
        prior = orbital_prior_groups(features.shape[1],
            self.hardware.shape[1] + self.smooth.shape[1], self.labels, self.supported_local)
        raw = self.values - self.q * result["intercept"]
        bound = hierarchical_bound(raw[self.keep], features[self.keep], self.point_noise[self.keep],
                                   self.noise_groups[self.keep], prior_groups=prior, prior_nu=4.)
        present = np.unique(self.noise_groups[self.keep])
        weights = np.zeros(len(self.members))
        weights[present] = bound["noise_precision"]
        bound["noise_precision"] = weights
        bound["conditional_residual_hz"] = raw - features @ bound["coefficient"]
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.noise_volume)]
        result.update(bound)
        return result


def repaired_fit(scan, node, arm, kind, keep, control="baseline"):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    widths, receipt = phase_widths(scan, labels)
    reference, anchor, history = np.zeros(len(labels)), np.zeros(2), []
    for _ in range(5):
        cls = TailDiagnostic if kind == "tail4" else DiagnosticNormal
        p = cls(scan, node, scan.radio_sigma_hz, arm == "fitted_c", reference=reference,
                keep=keep, control=control)
        if kind in ("phase3", "causal"):
            p.phase_sigma = np.full(len(labels), 3.) if kind == "phase3" else widths
        fitted = fit(p, anchor)
        anchor = np.array(fitted["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(float(np.max(abs(phase - reference))))
        reference = np.clip(phase, -15, 15)
    return p, fitted, history, receipt


def repairs(case):
    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    failed = {r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"]
              if not r["compatible"]}
    results = []
    for name, kind, remove in (("unit_all", "unit", False),
                               ("remove_failed", "unit", True),
                               ("phase3_quality", "phase3", True),
                               ("causal_phase", "causal", False),
                               ("causal_phase_quality", "causal", True),
                               ("tail4", "tail4", False),
                               ("tail4_quality", "tail4", True)):
        keep = np.ones(len(base.values), bool)
        if remove:
            for row, sl in zip(base.rows, base.slices, strict=True):
                if row["component"] in failed:
                    keep[sl] = False
        for arm in ARMS:
            p, fitted, history, receipt = repaired_fit(scan, winner["node"], arm, kind, keep)
            results.append(dict(variant=name, arm=arm, fit=fitted,
                                removed_points=int((~keep).sum()),
                                removed_components=sorted(failed) if remove else [],
                                error_km=error_km(fitted["parameters"]),
                                decomposition=decompose(p, fitted["parameters"]),
                                phase_reference=p.reference, phase_sigma_s=p.phase_sigma,
                                phase_width_receipt=receipt, last_phase_changes=history))
            write(OUTPUT / case / "repairs.json", dict(case=case, results=results,
                GPS_evaluation_only=True, no_future_TLE=True, matched_c0_fitted_c=True,
                same_labels_and_aliases=True, excluded_by_residual_gate_not_GPS=True))
        print(case, "repair", name, flush=True)


def combinations(case):
    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    failed = {r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"]
              if not r["compatible"]}
    keep = np.ones(len(base.values), bool)
    for row, sl in zip(base.rows, base.slices, strict=True):
        if row["component"] in failed:
            keep[sl] = False
    results = []
    for control in ("drift_1", "independent_bias_300", "native_band", "eccentric"):
        for arm in ARMS:
            p, fitted, history, _ = repaired_fit(scan, winner["node"], arm, "causal", keep, control)
            results.append(dict(control=control, arm=arm, fit=fitted,
                                removed_points=int((~keep).sum()),
                                error_km=error_km(fitted["parameters"]),
                                phase_reference=p.reference, last_phase_changes=history))
            write(OUTPUT / case / "combinations.json", dict(case=case, results=results,
                causal_phase_prior=True, failed_gate_removed=True, matched_c_pair=True,
                reference_position_evaluation_only=True))
        print(case, "combination", control, flush=True)


def failed_candidates(case):
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.phase_linear_geometry import (
        phase_linear_frequency,
        prepare_phase_geometry,
    )
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile

    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    failed = {r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"]
              if not r["compatible"]}
    keep = np.ones(len(base.values), bool)
    for row, sl in zip(base.rows, base.slices, strict=True):
        if row["component"] in failed:
            keep[sl] = False
    if not failed:
        return
    p, fitted, _, _ = repaired_fit(scan, winner["node"], "c0", "unit", keep)
    x, state, results = fitted["parameters"], p.state(fitted["parameters"]), []
    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
        track = scan.tracks[i]
        if track["key"] not in failed:
            continue
        times, values = track["times"], track["values"]
        q = track["rf_hz"] / 11.5e9
        radio = scan.hardware(track, state["beta"])
        radio += q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
        y = values - radio
        inverse = np.diag(1 / p.point_noise[sl])
        geometry = prepare_phase_geometry(scan.sky, times)
        frequency, elevation, derivative = phase_linear_frequency(geometry, *latlon(x))
        phases = np.linspace(-10, 10, 81)
        prediction = q * (frequency[:, None] + derivative[:, None] * phases[None, :, None])
        terms = profile(y, prediction.reshape(-1, len(times)), inverse)
        cost = terms["cost"].reshape(len(scan.norads), -1) + phases[None, :]**2 / 3**2
        cost[elevation.max(axis=1) < 0] = np.inf
        shortlist = set(map(int, np.argsort(cost.min(axis=1))[:30]))
        segment_masks = [(times >= lo) & (times < lo + 20)
                         for lo in np.arange(times[0], times[-1], 20)]
        segment_masks = [m for m in segment_masks if m.sum() >= 8]
        for mask in segment_masks:
            terms = profile(y[mask], prediction[:, :, mask].reshape(-1, int(mask.sum())),
                            np.diag(1 / p.point_noise[sl][mask]))
            costs = terms["cost"].reshape(len(scan.norads), -1) + phases[None, :]**2 / 3**2
            costs[elevation[:, mask].max(axis=1) < 0] = np.inf
            shortlist.update(map(int, np.argsort(costs.min(axis=1))[:10]))
        shortlist.add(p.rows[k]["candidate_index"])
        candidates, segments = [], [[] for _ in segment_masks]
        for j in shortlist:
            grid = np.linspace(-15, 15, 121)
            bank = dict(time_s=scan.sky["time_s"],
                        position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
                        velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0))
            f, elev = paired_phase_frequency(bank, np.tile(times, len(grid)),
                np.repeat(np.arange(len(grid)), len(times)), grid, *latlon(x))
            f, elev = f.reshape(len(grid), -1), elev.reshape(len(grid), -1)
            terms = profile(y, q * f, inverse)
            score = terms["cost"] + grid**2 / 3**2
            score[elev.min(axis=1) < 0] = np.inf
            best = int(np.argmin(score))
            residual = terms["residual"][best]
            diagnostics = batch_noise_screen(residual[None], times)
            n = int(scan.norads[j])
            candidates.append(dict(norad=n, candidate_index=int(j), phase_s=float(grid[best]),
                rms_hz=float(terms["rms"][best]), bias_hz=float(terms["bias"][best]),
                cost=float(score[best]), alias=int(terms["alias"][best]),
                passes_rms_bias_structure=bool(terms["rms"][best] <= 450
                    and abs(terms["bias"][best]) <= 3000
                    and diagnostics["noise_screen_pass"][0]),
                existing_calibration_family=bool(j in p.labels),
                shared_family_phase_s=float(state["phases"][j]) if j in p.labels else None,
                residual_hz=residual, prediction_hz=q * f[best] + radio,
                observation_alias_lift_hz=float(terms["alias"][best] / 4.4e-6)))
            for mask, rows in zip(segment_masks, segments, strict=True):
                part = profile(y[mask], q * f[:, mask], np.diag(1 / p.point_noise[sl][mask]))
                score = part["cost"] + grid**2 / 3**2
                score[elev[:, mask].min(axis=1) < 0] = np.inf
                b = int(np.argmin(score))
                residual = part["residual"][b]
                diagnostics = batch_noise_screen(residual[None], times[mask])
                rows.append(dict(norad=n, candidate_index=int(j), phase_s=float(grid[b]),
                    rms_hz=float(part["rms"][b]), bias_hz=float(part["bias"][b]),
                    cost=float(score[b]), residual_hz=residual,
                    passes=bool(part["rms"][b] <= 450 and abs(part["bias"][b]) <= 3000
                                and diagnostics["noise_screen_pass"][0])))
        results.append(dict(component=track["key"], point_count=len(times), times=times,
            values=values, retained_only_calibration_endpoint=x,
            original_norad=p.rows[k]["candidate_norad"],
            candidates=sorted(candidates, key=lambda r: r["cost"]),
            segments=[dict(times=times[m], values=values[m],
                           candidates=sorted(rows, key=lambda r: r["cost"]))
                      for m, rows in zip(segment_masks, segments, strict=True)]))
    write(OUTPUT / case / "failed_candidate_search.json", dict(case=case, results=results,
          reference_GPS_used=False, all_causal_satellites_screened=True,
          finite_phase_grid=True, no_linear_calibration=True,
          observation_population_and_calibration_fixed=True))


def frozen_frequency(p, x, labels, times):
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.orbit_uncertainty import paired_frequency_modes

    state, c, scan = p.state(x), p.calculate(x), p.scan
    begin = p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels)
    predictions = []
    for j in labels:
        phase = np.array([state["phases"][j]])
        bank = dict(time_s=scan.sky["time_s"], position_km=scan.sky["position_km"][[j]],
                    velocity_km_s=scan.sky["velocity_km_s"][[j]])
        f, _ = paired_phase_frequency(bank, times, np.zeros(len(times), int), phase, *latlon(x))
        if j in p.supported:
            local, k = p.labels.index(j), p.supported.index(j)
            modes = dict(time_s=p.mode_bank["time_s"],
                         position_km=p.mode_bank["position_km"][3*local:3*local+3],
                         velocity_km_s=p.mode_bank["velocity_km_s"][3*local:3*local+3])
            derivative = paired_frequency_modes(bank, modes, times,
                np.zeros(len(times), int), phase, *latlon(x))
            f += derivative @ c["coefficient"][begin + 3*k:begin + 3*k+3]
        predictions.append(f)
    return np.array(predictions)


def split_failed(case):
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile

    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    failed = {r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"]
              if not r["compatible"]}
    keep = np.ones(len(base.values), bool)
    for row, sl in zip(base.rows, base.slices, strict=True):
        if row["component"] in failed:
            keep[sl] = False
    p, fitted, _, _ = repaired_fit(scan, winner["node"], "c0", "unit", keep)
    x, state, results = fitted["parameters"], p.state(fitted["parameters"]), []
    labels = sorted({row["candidate_index"] for row in p.rows if row["component"] not in failed})
    for i, sl in zip(p.members, p.slices, strict=True):
        track = scan.tracks[i]
        if track["key"] not in failed:
            continue
        times, values, q = track["times"], track["values"], track["rf_hz"] / 11.5e9
        radio = scan.hardware(track, state["beta"])
        radio += q * scan.rx_basis[i] @ state["smooth"][track["receiver"]-1]
        y = values - radio
        predictions = q * frozen_frequency(p, x, labels, times)
        noise = p.point_noise[sl]

        def score_part(start, stop, times=times, y=y, predictions=predictions, noise=noise):
            tt = times[start:stop]
            terms = profile(y[start:stop], predictions[:, start:stop],
                            np.diag(1 / noise[start:stop]))
            screen = batch_noise_screen(terms["residual"], tt)
            good = ((terms["rms"] <= 450) & (abs(terms["bias"]) <= 3000)
                    & screen["noise_screen_pass"])
            j = int(np.argmin(np.where(good, terms["cost"], np.inf))) if good.any() else int(
                np.argmin(terms["cost"]))
            return dict(start_index=start, stop_index=stop, start_s=float(tt[0]),
                        end_s=float(tt[-1]), points=len(tt), norad=int(scan.norads[labels[j]]),
                        candidate_index=int(labels[j]), cost=float(terms["cost"][j]),
                        passes=bool(good[j]), rms_hz=float(terms["rms"][j]),
                        bias_hz=float(terms["bias"][j]), residual_hz=terms["residual"][j])

        full = score_part(0, len(times))
        cuts = []
        for cut in range(8, len(times)-7):
            left, right = score_part(0, cut), score_part(cut, len(times))
            cost = left["cost"] + right["cost"] + 3 * np.log(len(times))
            cuts.append(dict(cut=cut, before_s=float(times[cut-1]), after_s=float(times[cut]),
                             penalized_cost=float(cost),
                             all_pass=left["passes"] and right["passes"],
                             left=left, right=right))
        results.append(dict(component=track["key"], full=full,
                            splits=sorted(cuts, key=lambda c: c["penalized_cost"])))
    write(OUTPUT / case / "split_failed.json", dict(case=case, results=results,
          satellite_phases_orbits_and_receiver_calibration_frozen=True,
          candidates_only_other_calibrated_families=True, GPS_used=False,
          linear_segments_never_calibrate=True, split_penalty="3 log N"))


def trim_failed(case):
    from copy import deepcopy

    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile

    scan, original, winner = context(case)
    base = DiagnosticNormal(scan, winner["node"], scan.radio_sigma_hz, False)
    failed = {r["component"] for r in winner["arms"]["c0"]["metrics"]["tracks"]
              if not r["compatible"]}
    mask = np.ones(len(base.values), bool)
    for row, sl in zip(base.rows, base.slices, strict=True):
        if row["component"] in failed:
            mask[sl] = False
    p, fitted, _, _ = repaired_fit(scan, winner["node"], "c0", "unit", mask)
    x, state = fitted["parameters"], p.state(fitted["parameters"])
    # This shortlist was generated without GPS from all causal candidates,
    # using both the whole track and each >=8-point 20-second section.
    search = json.loads((ROOT / "reports/2026_10_18_ds23_adaptive_failures" / case
                         / "failed_candidate_search.json").read_text())
    result = []
    for item in search["results"]:
        k = next(k for k, row in enumerate(p.rows) if row["component"] == item["component"])
        i, sl = p.members[k], p.slices[k]
        track = scan.tracks[i]
        times, values, q = track["times"], track["values"], track["rf_hz"] / 11.5e9
        radio = scan.hardware(track, state["beta"])
        radio += q * scan.rx_basis[i] @ state["smooth"][track["receiver"]-1]
        y, noise = values-radio, p.point_noise[sl]
        alternatives = []
        supports = {(0, len(times))}
        supports.update((a, len(times)) for a in range(1, len(times)-11))
        supports.update((0, b) for b in range(12, len(times)))
        for candidate in item["candidates"]:
            j = candidate["candidate_index"]
            grid = np.linspace(-15, 15, 121)
            bank = dict(time_s=scan.sky["time_s"],
                        position_km=np.repeat(scan.sky["position_km"][[j]], len(grid), axis=0),
                        velocity_km_s=np.repeat(scan.sky["velocity_km_s"][[j]], len(grid), axis=0))
            f, elev = paired_phase_frequency(bank, np.tile(times, len(grid)),
                np.repeat(np.arange(len(grid)), len(times)), grid, *latlon(x))
            f, elev = f.reshape(len(grid), -1), elev.reshape(len(grid), -1)
            for start, stop in sorted(supports):
                t = times[start:stop]
                if t[-1]-t[0] < 20:
                    continue
                terms = profile(y[start:stop], q*f[:, start:stop],
                                np.diag(1/noise[start:stop]))
                score = terms["cost"] + grid**2 / 3**2
                score[elev[:, start:stop].min(axis=1) < 0] = np.inf
                b = int(np.argmin(score))
                residual = terms["residual"][b]
                screen = batch_noise_screen(residual[None], t)
                if (terms["rms"][b] > 450 or abs(terms["bias"][b]) > 3000
                        or not screen["noise_screen_pass"][0]
                        or not radio_tail_screen(residual, noise[start:stop])["passes"]):
                    continue
                alternatives.append(dict(start_index=start, stop_index=stop, points=stop-start,
                    candidate_index=j, norad=candidate["norad"], phase_s=float(grid[b]),
                    start_s=float(t[0]), end_s=float(t[-1]), rms_hz=float(terms["rms"][b]),
                    bias_hz=float(terms["bias"][b]), cost=float(score[b]),
                    alias=int(terms["alias"][b]), residual_hz=residual,
                    maximum_radio_standardized_residual=float(
                        np.max(abs(residual) / noise[start:stop]))))
        alternatives.sort(key=lambda a: (-a["points"], a["cost"]))
        if not alternatives:
            result.append(dict(component=track["key"], no_passing_trim=True))
            continue
        selected = alternatives[0]
        node = deepcopy(winner["node"])
        node["seed"]["rows"][k].update(candidate_index=selected["candidate_index"],
                                      candidate_norad=selected["norad"])
        node["aliases"][k] = selected["alias"]
        keep = mask.copy()
        keep[sl.start+selected["start_index"]:sl.start+selected["stop_index"]] = True
        refits = []
        for kind in ("unit", "phase3", "causal"):
            for arm in ARMS:
                pp, ff, hh, _ = repaired_fit(scan, node, arm, kind, keep)
                refits.append(dict(kind=kind, arm=arm, fit=ff, error_km=error_km(ff["parameters"]),
                                   last_phase_changes=hh, phase_reference=pp.reference))
        result.append(dict(component=track["key"], selected=selected,
                           alternatives=alternatives[:20], refits=refits,
                           removed_points=int((~keep).sum()), position_for_selection=x))
    write(OUTPUT / case / "trim_failed.json", dict(case=case, results=result,
          GPS_used_for_trim_or_identity=False, independent_calibration_frozen_for_selection=True,
          rule="maximum retained points passing RMS, bias and structure; RF score breaks ties",
          minimum_retained_points=12, minimum_retained_span_s=20,
          maximum_external_radio_standardized_residual=6,
          causal_shortlist_and_phase_grid=True, same_retained_data_and_labels_in_c_pair=True,
          adaptive_selection_requires_independent_validation=True))


def validate_prefix(case):
    from copy import deepcopy

    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile

    scan, original, winner = context(case)
    saved = json.loads((OUTPUT / case / "trim_failed.json").read_text())["results"][0]
    choice = saved["selected"]
    node = deepcopy(winner["node"])
    base = DiagnosticNormal(scan, node, scan.radio_sigma_hz, False)
    k = next(k for k, r in enumerate(base.rows) if r["component"] == saved["component"])
    i, sl = base.members[k], base.slices[k]
    node["seed"]["rows"][k].update(candidate_index=choice["candidate_index"],
                                  candidate_norad=choice["norad"])
    node["aliases"][k] = choice["alias"]
    keep = np.ones(len(base.values), bool)
    keep[sl] = False
    keep[sl.start+choice["start_index"]:sl.start+choice["stop_index"]] = True
    results = []
    for arm in ARMS:
        p, fitted, _, _ = repaired_fit(scan, node, arm, "causal", keep)
        x, state, n = fitted["parameters"], p.state(fitted["parameters"]), choice["start_index"]
        t = scan.tracks[i]
        q = t["rf_hz"] / 11.5e9
        radio = scan.hardware(t, state["beta"])
        radio += q*scan.rx_basis[i] @ state["smooth"][t["receiver"]-1]
        labels = [j for j in p.labels if j != choice["candidate_index"]]
        prediction = q*frozen_frequency(p, x, labels, t["times"][:n])
        terms = profile((t["values"]-radio)[:n], prediction,
                        np.diag(1/p.point_noise[sl][:n]))
        screen = batch_noise_screen(terms["residual"], t["times"][:n])
        candidates = []
        for j in np.argsort(terms["cost"])[:5]:
            tail = radio_tail_screen(terms["residual"][j], p.point_noise[sl][:n])
            candidates.append(dict(norad=int(scan.norads[labels[j]]),
                rms_hz=float(terms["rms"][j]), bias_hz=float(terms["bias"][j]),
                diagnostics={key: float(v[j]) for key, v in screen.items()},
                passes=bool(screen["noise_screen_pass"][j] and terms["rms"][j] <= 450
                            and abs(terms["bias"][j]) <= 3000 and tail["passes"]),
                maximum_radio_z=tail["maximum_standardized_residual"],
                residual_hz=terms["residual"][j]))
        results.append(dict(arm=arm, candidates=candidates, fitted_endpoint=x,
                            error_km=error_km(x), prefix_points=n,
                            retained_suffix_residual_hz=p.calculate(x)[
                                "conditional_residual_hz"][sl][n:],
                            retained_suffix_diagnostics={key: float(v[0]) for key, v in
                                batch_noise_screen(p.calculate(x)["conditional_residual_hz"][sl]
                                                   [n:][None], t["times"][n:]).items()},
                            prefix_was_not_used_for_calibration=True))
    write(OUTPUT / case / "prefix_validation.json", dict(results=results,
          satellite_orbit_phase_receiver_calibration_frozen_for_prefix=True,
          GPS_used_for_selection=False, association_tentative_not_ground_truth=True))


def surfaces(case):
    from copy import deepcopy

    scan, original, winner = context(case)
    repairs = json.loads((OUTPUT / case / "repairs.json").read_text())["results"]
    base_scan = FreshScan(SOURCE / case, noise_mode="radio")
    east, north = np.linspace(-5, 7, 25), np.linspace(-5, 5, 21)
    maps, diagnostics = {}, []
    for arm in ARMS:
        saved = winner["arms"][arm]
        baseline = DiagnosticNormal(base_scan, winner["node"], base_scan.radio_sigma_hz,
                                    arm == "fitted_c", reference=np.array(saved["reference"]))
        node = deepcopy(winner["node"])
        keep = np.ones(len(baseline.values), bool)
        if case == "DS23-0342":
            trimmed = json.loads((OUTPUT / case / "trim_failed.json").read_text())["results"][0]
            choice = trimmed["selected"]
            k = next(k for k, r in enumerate(baseline.rows)
                     if r["component"] == trimmed["component"])
            sl = baseline.slices[k]
            keep[sl] = False
            keep[sl.start+choice["start_index"]:sl.start+choice["stop_index"]] = True
            node["seed"]["rows"][k].update(candidate_index=choice["candidate_index"],
                                          candidate_norad=choice["norad"])
            node["aliases"][k] = choice["alias"]
            fitted = next(r for r in trimmed["refits"] if r["kind"] == "causal" and r["arm"] == arm)
        else:
            fitted = next(r for r in repairs if r["variant"] == "causal_phase" and r["arm"] == arm)
        ref = fitted.get("phase_reference", fitted.get("reference"))
        corrected = DiagnosticNormal(scan, node, scan.radio_sigma_hz, arm == "fitted_c",
                                     reference=np.array(ref), keep=keep)
        corrected.phase_sigma, _ = phase_widths(scan, corrected.labels)
        for name, p, endpoint in (("baseline", baseline, saved["fit"]["parameters"]),
                                  ("corrected", corrected, fitted["fit"]["parameters"])):
            def score(point, problem=p):
                r = problem.residual(point)
                return float(r @ r)

            center_score = score(endpoint)
            h = .1
            x = np.array(endpoint)
            directions = np.eye(2) * h
            diagonal = [(score(x+d) - 2*center_score + score(x-d))/h**2 for d in directions]
            cross = (score(x+directions.sum(axis=0)) + score(x-directions.sum(axis=0))
                     - score(x+directions[0]-directions[1])
                     - score(x-directions[0]+directions[1]))/(4*h**2)
            matrix = np.array([[diagonal[0], cross], [cross, diagonal[1]]])
            eigenvalues = np.linalg.eigvalsh(matrix)
            maps[name+"_"+arm] = np.array([[score(REFERENCE_XY + [e, n]) for e in east]
                                          for n in north])
            diagnostics.append(dict(model=name, arm=arm, endpoint=endpoint,
                endpoint_score=center_score, error_km=error_km(endpoint),
                at_reference_position=decompose(p, REFERENCE_XY),
                Hessian=matrix, Hessian_eigenvalues=eigenvalues,
                local_quadratic_scales_km=np.sqrt(2/np.maximum(eigenvalues, 1e-12))))
        print(case, "surfaces", arm, flush=True)
    np.savez_compressed(OUTPUT / case / "surfaces.npz", east_from_reference_km=east,
                        north_from_reference_km=north, **maps)
    write(OUTPUT / case / "surface_diagnostics.json", dict(case=case, results=diagnostics,
        grid_step_km=.5, satellite_IDs_aliases_phase_references_fixed=True,
        nuisance_coefficients_and_noise_precisions_reprofiled_at_every_grid_point=True,
        full_pipeline_rerun_at_each_grid_point=False, GPS_diagnostic_only=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("DS23-0342", "DS23-0039"))
    parser.add_argument("--stage", required=True,
                        choices=("audit", "family", "track", "group", "controls", "repairs",
                                 "failed_candidates", "split_failed", "combinations", "trim_failed",
                                 "validate_prefix", "surfaces", "polynomial_split"))
    parser.add_argument("--prior", choices=("frozen", "genuine"), default="frozen")
    args = parser.parse_args()
    if args.prior == "genuine":
        USE_GENUINE_PRIOR = True
        OUTPUT = OUTPUT / "genuine_causal_prior"
    (OUTPUT / args.case).mkdir(parents=True, exist_ok=True)
    if args.stage == "audit":
        audit(args.case)
    elif args.stage == "controls":
        controls(args.case)
    elif args.stage == "repairs":
        repairs(args.case)
    elif args.stage == "failed_candidates":
        failed_candidates(args.case)
    elif args.stage == "split_failed":
        split_failed(args.case)
    elif args.stage == "combinations":
        combinations(args.case)
    elif args.stage == "trim_failed":
        trim_failed(args.case)
    elif args.stage == "validate_prefix":
        validate_prefix(args.case)
    elif args.stage == "surfaces":
        surfaces(args.case)
    elif args.stage == "polynomial_split":
        polynomial_split(args.case)
    else:
        influences(args.case, args.stage)
