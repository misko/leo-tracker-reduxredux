"""Recheck final orbital MAP residuals with actual perturbed SGP4 elements."""

import hashlib
import json

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import OUTPUT, PARTITION, ROOT
from fit_s01_69333_tle_parameter import perturb
from sgp4.api import Satrec

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening
from leo.sky.propagation import ElementSetCatalogue


def run():
    elements = json.loads((OUTPUT / "causal_tles.json").read_text())
    results = {}
    for case in [f"DSX01-S{i:02d}" for i in range(1, 6)]:
        directory = OUTPUT / case
        path = directory / "refined_endpoints.json"
        if not path.exists():
            raise RuntimeError("all refined endpoints must finish first")
        fits = json.loads(path.read_text())
        bank_path = (
            ROOT
            / (
                "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs"
                if case.endswith("S01")
                else "reports/2026_10_17_robust_curve_reassociation/frozen_inputs"
            )
            / case
        )
        with np.load(bank_path / "bank.npz") as bank:
            sky = {k: bank[k] for k in bank.files}
        tracks = json.loads((PARTITION / case / "curves.json").read_text())
        track = {t["key"]: t for t in tracks}
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        for arm in ["c0", "fitted_c"]:
            fit = fits[f"{arm}/orbit_em"]
            state = fit["state"]
            beta = np.array(state["beta"])
            phases = np.array(state["phases"])
            chosen = sorted({r["candidate_index"] for r in fit["rows"]})
            sats = []
            for j in chosen:
                n = int(sky["norad"][j])
                sat = Satrec.twoline2rv(*elements[case]["satellites"][str(n)]["lines"])
                correction = state["extra"].get(str(j))
                if correction is not None:
                    sat = perturb(
                        perturb(sat, "e_cos_omega", correction[0]), "e_sin_omega", correction[1]
                    )
                sats.append(sat)
            numbers = tuple(int(sky["norad"][j]) for j in chosen)
            cat = ElementSetCatalogue(tuple(map(str, numbers)), numbers, tuple(sats))
            p, v, good = matching.ecef_states(cat, elements[case]["origin_utc_ns"], sky["time_s"])
            assert good.all()
            prepared = prepare_phase_geometry(
                dict(time_s=sky["time_s"], position_km=p, velocity_km_s=v), times, phases[chosen]
            )
            f, e, _ = phase_linear_frequency(prepared, fit["latitude_deg"], fit["longitude_deg"])
            lookup = {j: k for k, j in enumerate(chosen)}
            rows = []
            for row in fit["rows"]:
                t = track[row["component"]]
                tt = np.array(t["times"])
                y = np.array(t["values"])
                g = matching.group(t)
                hw = beta[g] + beta[g + 4] * (tt - 150) / 150
                if len(beta) == 9:
                    hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
                ix = np.searchsorted(times, tt)
                j = lookup[row["candidate_index"]]
                w, volume = whitening(tt)
                terms = profile(y - hw, t["rf_hz"] / 11.5e9 * f[j, ix], w, volume)
                noise = batch_noise_screen(terms["innovations"], tt)
                passing = bool(
                    e[j, ix].min() >= 0
                    and terms["rms"][0] <= 450
                    and abs(terms["bias"][0]) <= 3000
                    and noise["noise_screen_pass"][0]
                )
                rows.append(
                    dict(
                        component=row["component"],
                        previously_accepted=row["compatible"],
                        exact_frequency_gates_pass=passing,
                        exact_native_rms_hz=float(terms["rms"][0]),
                        approximate_native_rms_hz=row["rms_hz"],
                        exact_noise_diagnostics={k: v[0] for k, v in noise.items()},
                        maximum_residual_difference_hz=float(
                            np.max(abs(terms["residual"][0] - row["residual_hz"]))
                        ),
                    )
                )
                row.update(
                    tangent_compatible=row["compatible"],
                    compatible=row["compatible"] and passing,
                    rms_hz=float(terms["rms"][0]),
                    bias_hz=float(terms["bias"][0]),
                    cost=float(terms["cost"][0]),
                    residual_hz=terms["residual"][0],
                    innovations_hz=terms["innovations"][0],
                )
            invalid = [
                r for r in rows if r["previously_accepted"] and not r["exact_frequency_gates_pass"]
            ]
            # Dropping a curved owner can remove support for an extra satellite
            # correction or a linear transfer. Apply conservative closure; never
            # promote an old rejection merely because its exact residual passes.
            cascaded = []
            while True:
                owners, hardware = {}, set()
                for row in fit["rows"]:
                    if row["compatible"] and row["active_curvature"]:
                        t = track[row["component"]]
                        owners.setdefault(row["candidate_index"], set()).add(t["channel"])
                        hardware.add(matching.group(t))
                changed = False
                for row in fit["rows"]:
                    if not row["compatible"]:
                        continue
                    j, t = row["candidate_index"], track[row["component"]]
                    unsupported = str(j) in state["extra"] and len(owners.get(j, set())) < 2
                    if not row["active_curvature"]:
                        unsupported |= matching.group(t) not in hardware
                        unsupported |= abs(phases[j]) > 0.001 and j not in owners
                    if unsupported:
                        row["compatible"] = False
                        cascaded.append(row["component"])
                        changed = True
                if not changed:
                    break
            passing_lookup = {r["component"]: r["exact_frequency_gates_pass"] for r in rows}
            final_invalid = [
                r["component"]
                for r in fit["rows"]
                if r["compatible"] and not passing_lookup[r["component"]]
            ]
            results[f"{case}/{arm}"] = dict(
                endpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                rows=rows,
                accepted_rows_failing_exact_recheck=invalid,
                support_cascade_rejections=cascaded,
                final_accepted_rows_failing_exact_recheck=final_invalid,
                dropped_points=sum(
                    r["points"]
                    for r in fit["rows"]
                    if r["tangent_compatible"] and not r["compatible"]
                ),
                maximum_residual_difference_hz=max(
                    r["maximum_residual_difference_hz"] for r in rows
                ),
                location_frozen_no_reference_used=True,
            )
            print(
                case,
                arm,
                "exact accepted failures",
                len(invalid),
                "max residual difference",
                results[f"{case}/{arm}"]["maximum_residual_difference_hz"],
                flush=True,
            )
            fit["exact_recheck"] = dict(
                fitted_position_and_parameters_frozen=True,
                score_is_tangent_search_score=True,
                rejected_assignments_never_promoted=True,
                original_endpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        write(directory / "exact_validated_endpoints.json", fits)
    write(OUTPUT / "exact_orbit_validation.json", results)
    assert not any(r["final_accepted_rows_failing_exact_recheck"] for r in results.values())


if __name__ == "__main__":
    run()
