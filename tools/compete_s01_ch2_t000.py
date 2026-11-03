"""All-candidate phase competition for the remaining curved CH2 fragment."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import BRACKET, OUTPUT, TARGET, hardware
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.shared_satellite_correction import profile_curve


def run():
    arms = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        track = next(t for t in study.tracks if t["key"] == TARGET)
        fit = json.loads(
            (
                ROOT / "reports/2026_10_17_s01_phase_sensitivity" / arm / "fit_cap_2.7.json"
            ).read_text()
        )
        arms[arm] = track["values"] - hardware(track, np.array(fit["beta"]))
    assert TARGET in study.curved_keys
    phases = np.linspace(-15, 15, 601)
    for kind in ("past", "first_future_epoch"):
        with np.load(BRACKET / f"bank_{kind}.npz") as bank:
            sky = {k: bank[k] for k in bank.files}
        matrices = {
            arm: dict(
                rms=np.zeros((len(phases), len(sky["norad"]))),
                bias=np.zeros((len(phases), len(sky["norad"]))),
                passing=np.zeros((len(phases), len(sky["norad"])), bool),
                score=np.zeros((len(phases), len(sky["norad"]))),
            )
            for arm in arms
        }
        visible = None
        for i, phase in enumerate(phases):
            geom = prepare_phase_geometry(sky, track["times"], np.full(len(sky["norad"]), phase))
            f, e, _ = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
            visible = e.min(axis=1) >= 0
            for arm, y in arms.items():
                terms = profile_curve(y, track["rf_hz"] / 11.5e9 * f)
                noise = batch_noise_screen(terms["residual"], track["times"])
                m = matrices[arm]
                m["rms"][i], m["bias"][i], m["score"][i] = (
                    terms["rms"],
                    terms["bias"],
                    terms["score"],
                )
                m["passing"][i] = (
                    visible
                    & (terms["rms"] <= 450)
                    & (abs(terms["bias"]) <= 3000)
                    & noise["noise_screen_pass"]
                )
            if (i + 1) % 100 == 0:
                print(json.dumps(dict(tle=kind, phases=i + 1)), flush=True)
        for arm, m in matrices.items():
            best = np.argmin(m["rms"], axis=0)
            indexes = np.arange(len(sky["norad"]))
            ranking = np.argsort(m["rms"][best, indexes])
            shortlist = []
            for j in ranking[:20]:
                k = best[j]
                shortlist.append(
                    dict(
                        norad=int(sky["norad"][j]),
                        phase_s=float(phases[k]),
                        rms_hz=float(m["rms"][k, j]),
                        bias_hz=float(m["bias"][k, j]),
                        any_phase_passes=bool(m["passing"][:, j].any()),
                    )
                )
            passing = [int(sky["norad"][j]) for j in indexes if m["passing"][:, j].any()]
            write(
                OUTPUT / arm / f"{kind}_identity.json",
                dict(
                    candidate_count=len(indexes),
                    phases=len(phases),
                    top20_by_rms=shortlist,
                    passing_candidates=passing,
                ),
            )
            np.savez_compressed(
                OUTPUT / arm / f"{kind}_identity.npz", norad=sky["norad"], phase_s=phases, **m
            )
            print(
                json.dumps(dict(tle=kind, arm=arm, passing=passing, top3=shortlist[:3])), flush=True
            )


if __name__ == "__main__":
    run()
