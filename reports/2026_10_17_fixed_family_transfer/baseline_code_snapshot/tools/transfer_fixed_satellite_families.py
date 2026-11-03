"""Transfer immutable blind satellite families, keeping all curved measurements."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from search_track_evidence_position import ROOT, prepare

from leo.analysis.research.fixed_assignment_fit import (
    fixed_assignment_score,
    improve_fixed_assignments,
)
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import (
    PERIOD,
    augment_phase_statistics,
    recenter_phases,
)

SOURCE = ROOT / "reports/2026_10_17_noise_gated_position/search"


class FixedFamilies:
    def __init__(self, case, fitted_c, merged):
        original, _, _, binding, _, _ = prepare(case, fitted_c)
        source = SOURCE / case / "c0"
        self.source_fit = json.loads((source / "fit.json").read_text())["endpoint"]
        association = json.loads((source / "association.json").read_text())
        evaluation = json.loads((source / "evaluation.json").read_text())
        if (
            hashlib.sha256((source / "fit.json").read_bytes()).hexdigest()
            != evaluation["fit_sha256"]
        ):
            raise ValueError("blind endpoint is not bound to its evaluation")
        admitted = {
            r["component"]: r
            for r in association["association"]["rows"]
            if r["compatible"] and r["active_curvature"]
        }
        tracks = {t["key"]: t for t in original.tracks}
        if merged:
            families = []
            for group in association["consolidated"]["groups"]:
                members = sorted(set(group["members"]) & admitted.keys())
                if members:
                    families.append(("+".join(members), members, group["candidate_norad"]))
        else:
            families = [
                (key, [key], row["candidate_norad"]) for key, row in sorted(admitted.items())
            ]
        families.sort(key=lambda r: r[0])
        seen = [key for _, members, _ in families for key in members]
        if len(seen) != len(set(seen)) or set(seen) != admitted.keys():
            raise ValueError("family partition changed curved fragment ownership")
        for _, members, norad in families:
            if any(admitted[key]["candidate_norad"] != norad for key in members):
                raise ValueError("merged family changed its candidate label")
        self.groups = [(key, [tracks[m] for m in members]) for key, members, _ in families]
        norads = sorted({n for _, _, n in families})
        lookup = {int(n): i for i, n in enumerate(original.sky["norad"])}
        selected = np.array([lookup[n] for n in norads])
        self.sky = dict(
            time_s=original.sky["time_s"],
            position_km=original.sky["position_km"][selected],
            velocity_km_s=original.sky["velocity_km_s"][selected],
        )
        self.norads, self.labels = norads, np.array([norads.index(n) for _, _, n in families])
        self.sigma, self.bounds = original.sigma[selected], original.bounds[selected]
        self.times = np.unique(np.concatenate([t["times"] for _, ms in self.groups for t in ms]))
        beta = np.asarray(self.source_fit["beta"][:8], float)
        self.initial_beta = np.r_[beta, 0.0] if fitted_c else beta
        self.initial_phase = np.asarray(self.source_fit["phases_s"])[selected]
        self.fitted_c, self.merged, self.binding = fitted_c, merged, binding
        self.observation_ids = sorted(
            oid for _, ms in self.groups for t in ms for oid in t["observation_ids"]
        )
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("duplicated fixed-family point identity")
        expected = {oid for key in admitted for oid in tracks[key]["observation_ids"]}
        if set(self.observation_ids) != expected:
            raise ValueError("fixed-family population changed")
        self.receipt = original.receipt
        self.source_digest = hashlib.sha256((source / "fit.json").read_bytes()).hexdigest()
        self.association_digest = hashlib.sha256(
            (source / "association.json").read_bytes()
        ).hexdigest()

    def statistics(self, latitude, longitude, phase):
        geometry = prepare_phase_geometry(self.sky, self.times, phase)
        f, e, h = phase_linear_frequency(geometry, latitude, longitude)
        stats = matching.statistics(
            self.groups,
            dict(time_s=self.times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for _, ms in self.groups for t in ms},
        )
        stats = recenter_phases(augment_phase_statistics(stats, self.times, f, h), phase)
        return stats, f

    def evaluate(self, latitude, longitude, beta, phase, *, details=False):
        stats, f = self.statistics(latitude, longitude, phase)
        evidence, terms = fixed_assignment_score(stats, beta, phase, self.sigma, self.labels)
        if not details:
            return evidence, stats
        rows, components = [], []
        for ci, (name, members) in enumerate(self.groups):
            j, residuals, times, good_members = self.labels[ci], [], [], []
            for track in members:
                ix = np.searchsorted(self.times, track["times"])
                fi = next(k for k, t in enumerate(stats["fragments"]) if t["key"] == track["key"])
                g = stats["g"][fi]
                hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
                if len(beta) == 9:
                    hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
                r = track["values"] + terms.aliases[fi, j] * PERIOD - hardware
                r -= track["rf_hz"] / 11.5e9 * f[j, ix] + terms.bias_hz[ci, j]
                diagnostic = matching.noise_screen(r, track["times"])
                rms = float(np.sqrt(np.mean(r**2)))
                compatible = bool(
                    stats["visible"][fi, j]
                    and rms <= 450
                    and abs(terms.bias_hz[ci, j]) <= 3000
                    and diagnostic["noise_screen_pass"]
                )
                good_members.append(compatible)
                residuals.extend(r)
                times.extend(track["times"])
                rows.append(
                    dict(
                        component=name,
                        key=track["key"],
                        norad=self.norads[j],
                        points=len(r),
                        rms_hz=rms,
                        compatible=compatible,
                        bias_hz=float(terms.bias_hz[ci, j]),
                        diagnostics=diagnostic,
                        time_s=track["times"],
                        residual_hz=r,
                    )
                )
            residuals, times = np.asarray(residuals), np.asarray(times)
            order = np.argsort(times, kind="stable")
            pooled = matching.noise_screen(residuals[order], times[order])
            if not np.isclose(
                np.mean(residuals**2), terms.residual_mse[ci, j], rtol=1e-7, atol=0.01
            ):
                raise ValueError("point residuals differ from sufficient statistics")
            components.append(
                dict(
                    key=name,
                    members=[t["key"] for t in members],
                    norad=self.norads[j],
                    points=len(residuals),
                    rms_hz=float(np.sqrt(np.mean(residuals**2))),
                    compatible=bool(all(good_members) and pooled["noise_screen_pass"]),
                    pooled_diagnostics=pooled,
                    bias_hz=float(terms.bias_hz[ci, j]),
                )
            )
        return dict(
            evidence=evidence,
            rows=rows,
            components=components,
            overall_rms_hz=float(
                np.sqrt(
                    sum(r["points"] * r["rms_hz"] ** 2 for r in rows)
                    / sum(r["points"] for r in rows)
                )
            ),
            member_compatible_points=sum(r["points"] for r in rows if r["compatible"]),
            family_compatible_points=sum(r["points"] for r in components if r["compatible"]),
            total_points=len(self.observation_ids),
            phase_bound_fraction=np.abs(phase) / self.bounds,
        )

    def fit(self, latitude, longitude, *, iterations=6):
        results = []
        for name, start_phase in (
            ("blind_phase", self.initial_phase),
            ("zero_phase", np.zeros_like(self.initial_phase)),
        ):
            beta, phase = self.initial_beta.copy(), start_phase.copy()
            evidence, stats = self.evaluate(latitude, longitude, beta, phase)
            history = [dict(iteration=0, score=evidence["score"])]
            for iteration in range(iterations):
                proposed = improve_fixed_assignments(
                    stats, beta, phase, self.sigma, self.bounds, self.labels, rounds=2
                )
                step = proposed["beta"] - beta
                step[:4] = (step[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
                accepted = False
                for fraction in (1.0, 0.5, 0.25):
                    b = beta + fraction * step
                    b[:4] = (b[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
                    p = phase + fraction * (proposed["phases_s"] - phase)
                    trial, new_stats = self.evaluate(latitude, longitude, b, p)
                    if trial["score"] < evidence["score"] - 1e-6:
                        beta, phase, evidence, stats = b, p, trial, new_stats
                        history.append(dict(iteration=iteration + 1, score=evidence["score"]))
                        accepted = True
                        break
                if not accepted:
                    break
            results.append(
                dict(
                    beta=beta,
                    phases_s=phase,
                    score=evidence["score"],
                    history=history,
                    initializer=name,
                )
            )
        winner = min(results, key=lambda r: r["score"])
        detail = self.evaluate(
            latitude, longitude, winner["beta"], winner["phases_s"], details=True
        )
        return dict(
            latitude_deg=latitude,
            longitude_deg=longitude,
            beta=winner["beta"],
            phases_s=winner["phases_s"],
            phase_norads=self.norads,
            score=winner["score"],
            fitted_c=self.fitted_c,
            exact_phase_geometry=True,
            detail=detail,
            histories=results,
            observation_ids=self.observation_ids,
            fixed_labels=[self.norads[j] for j in self.labels],
            no_points_rejected=True,
            no_labels_changed=True,
            only_curved_members_calibrate=True,
        )


def run(case, fitted_c, merged, output):
    study = FixedFamilies(case, fitted_c, merged)
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            component_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/fixed_assignment_fit.py").read_bytes()
            ).hexdigest(),
            source_blind_fit_sha256=study.source_digest,
            source_blind_association_sha256=study.association_digest,
            c0_fitted_c_same_c0_labels_population_initial_hardware_phase_and_budgets=True,
            original_graph_partition=study.binding,
            calibration_points=len(study.observation_ids),
            components=len(study.groups),
            curved_members=sum(len(ms) for _, ms in study.groups),
            fitted_c=fitted_c,
            merged=merged,
            scan_local_hardware=True,
            drift_sigma_hz_s=0.5,
            drift_bound_hz_s=1,
            phase_sigma_s=study.sigma,
            phase_bounds_s=study.bounds,
            candidate_norads=study.norads,
            all_selected_curved_observations_costed_without_residual_rejection=True,
            linear_fragments_excluded_from_constants_and_state_ranking=True,
            gaussian_diagnostic_cost_not_noise_gated_clutter_score=True,
            component_point_weight_cap=50,
            scores_across_merged_and_unmerged_not_directly_comparable=True,
            two_initializers=["common_blind_c0_phase", "zero_phase"],
            maximum_nonlinear_iterations=6,
            tangent_updates=2,
            known_position_diagnostic_only=True,
            no_independent_localization_claim=True,
            no_existing_associations_modified=True,
        ),
    )
    started, summary = time.monotonic(), []
    sites = dict(
        blind_source=(study.source_fit["latitude_deg"], study.source_fit["longitude_deg"]),
        supplied_gps=(37.849061591561885, -122.48574968092912),
    )
    for name, (lat, lon) in sites.items():
        result = study.fit(lat, lon)
        write(output / f"{name}.json", result)
        row = dict(
            case=case,
            fitted_c=fitted_c,
            merged=merged,
            site=name,
            score=result["score"],
            rms_hz=result["detail"]["overall_rms_hz"],
            member_compatible_points=result["detail"]["member_compatible_points"],
            family_compatible_points=result["detail"]["family_compatible_points"],
            total_points=len(study.observation_ids),
            components=len(study.groups),
            phase_parameters_at_bounds=int(
                np.sum(result["detail"]["phase_bound_fraction"] > 0.999)
            ),
            drift_hz_s=np.asarray(result["beta"])[4:8] / 150,
        )
        summary.append(row)
        write(output / "progress.json", summary)
        print(json.dumps(row, default=lambda x: x.tolist()), flush=True)
    write(output / "summary.json", dict(rows=summary, elapsed_seconds=time.monotonic() - started))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DSX01-S01", "DS22-001"), required=True)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--merged", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.fitted_c, a.merged, a.output)
