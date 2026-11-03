"""Conditional transfer of the 62811 clock proposal to other curved families."""

import json
from types import SimpleNamespace

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import BRACKET, NORAD, PROTOTYPES, TARGET
from fit_s01_ch2_orbit_timing import DESTINATION, warp
from inventory_clipped_phase_cohort import ROOT, load_study
from run_s01_shared_satellite_prototypes import Prototype
from sgp4.api import Satrec

from leo.analysis.research.shared_satellite_correction import profile_curve


def run():
    results = json.loads((DESTINATION / "results.json").read_text())
    source = json.loads((BRACKET / "bracketing_tles.json").read_text())
    transfers = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        previous = json.loads(
            (PROTOTYPES / "family_extension" / arm / "association.json").read_text()
        )["rows"]
        old = {r["component"]: r for r in previous}
        parameters = json.loads(
            (PROTOTYPES / "family_extension" / arm / "parameters.json").read_text()
        )
        fit = json.loads(
            (
                ROOT / "reports/2026_10_17_s01_phase_sensitivity" / arm / "fit_cap_2.7.json"
            ).read_text()
        )
        phase = dict(zip(map(int, study.sky["norad"]), fit["phases_s"], strict=True))
        target = old[TARGET]
        tracks = [
            t
            for t in study.tracks
            if t["key"] in study.curved_keys
            and old[t["key"]]["candidate_norad"] != NORAD
            and max(min(t["times"]), min(target["times_s"]))
            <= min(max(t["times"]), max(target["times_s"]))
        ]
        for case in ("all_curved", "omit_target"):
            proposal = results[f"{arm}/{case}/rx1_clock_rate_5000ppm"]
            rows = []
            for t in tracks:
                oldrow = old[t["key"]]
                n = oldrow["candidate_norad"]
                sat = Satrec.twoline2rv(*source["past"][str(n)]["lines"])
                p = parameters.get(str(n), dict(theta=[phase[n], 0.0], reference_time_s=150))
                proxy = SimpleNamespace(
                    method="family_extension",
                    origin=source["anchor_utc_ns"],
                    satellites={n: sat},
                    tref={n: p["reference_time_s"]},
                )
                nominal, _ = Prototype.forward(proxy, n, np.array(p["theta"]), t["times"])
                shifted = warp(
                    proposal["model"],
                    proposal["delta"],
                    t["times"],
                    t["receiver"],
                    proposal["timing_reference_s"],
                )
                f, e = Prototype.forward(proxy, n, np.array(p["theta"]), shifted)
                current = np.array(oldrow["residual_hz"]) + oldrow["bias_hz"]
                terms = profile_curve(current, t["rf_hz"] / 11.5e9 * (f - nominal))
                noise = matching.noise_screen(terms["residual"][0], t["times"])
                passing = bool(
                    np.min(e) >= 0
                    and terms["rms"][0] <= 450
                    and abs(terms["bias"][0]) <= 3000
                    and noise["noise_screen_pass"]
                )
                rows.append(
                    dict(
                        component=t["key"],
                        receiver=t["receiver"],
                        norad=n,
                        points=len(t["times"]),
                        old_passes=oldrow["compatible"],
                        old_rms_hz=oldrow["rms_hz"],
                        new_passes=passing,
                        new_rms_hz=float(terms["rms"][0]),
                        diagnostics=noise,
                    )
                )
            key = f"{arm}/{case}"
            transfers[key] = dict(
                clock_delta_ppm=proposal["delta"],
                rows=rows,
                old_accepted=sum(r["old_passes"] for r in rows),
                lost_fragments=sum(r["old_passes"] and not r["new_passes"] for r in rows),
                lost_points=sum(
                    r["points"] for r in rows if r["old_passes"] and not r["new_passes"]
                ),
                gained_fragments=sum(not r["old_passes"] and r["new_passes"] for r in rows),
                orbital_phases_and_hardware_of_other_families_frozen=True,
                no_linear_calibration=True,
                caveat=(
                    "conditional transfer; global joint timing/orbit recalibration not performed"
                ),
            )
            print(json.dumps({key: transfers[key]}), flush=True)
    write(DESTINATION / "clock_transfer.json", transfers)
    pooled = {}
    for key, result in results.items():
        rows = [r for r in result["rows"] if r["active_curvature"] and r["passing"]]
        if not rows:
            continue
        times = np.concatenate([r["times_s"] for r in rows])
        residual = np.concatenate([r["residual_hz"] for r in rows])
        order = np.argsort(times, kind="stable")
        pooled[key] = dict(
            curved_fragments=len(rows),
            points=len(times),
            diagnostics=matching.noise_screen(residual[order], times[order]),
            caveat="pooled fragments may have correlated receiver errors",
        )
    write(DESTINATION / "pooled_curved_residuals.json", pooled)


if __name__ == "__main__":
    run()
