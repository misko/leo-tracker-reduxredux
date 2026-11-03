"""Inspect whole-population transfer of the longest S01 curve's phase proposal."""

import json

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from deep_dive_longest_unassociated_s01 import CURRENT, OUTPUT, TARGET
from evaluate_robust_curve_reassociation import population_association
from inventory_clipped_phase_cohort import load_study


def run():
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, _, _, recording, background = load_study("DSX01-S01", fc)
        fit = json.loads((CURRENT / arm / "fit.json").read_text())
        old = json.loads((CURRENT / arm / "association.json").read_text())
        candidate = next(
            r
            for r in json.loads((OUTPUT / arm / "candidates.json").read_text())
            if r["norad"] == 63474
        )
        phase = candidate["free_phase_passing"]["phase_s"]
        after = dict(fit, phases_s=list(fit["phases_s"]))
        j = int(np.flatnonzero(study.sky["norad"] == 63474)[0])
        after["phases_s"][j] = phase
        before_rows = {r["component"]: r for r in old["association"]["rows"]}
        labels = {key: r["candidate_norad"] for key, r in before_rows.items() if r["compatible"]}
        labels[TARGET] = 63474

        class Bound:
            def __init__(self, experiment, fixed):
                self.experiment, self.fixed = experiment, fixed
                self.tracks, self.sky = experiment.tracks, experiment.sky

            def associate(self, fit):
                return self.experiment.associate(fit, fixed_labels=self.fixed)

        result = population_association(
            Bound(study, labels), after, load_tracks(recording), background
        )
        mapping = {t["key"]: t for t in study.tracks}
        inspected = []
        for r in result["association"]["rows"]:
            if (
                r["candidate_norad"] == 63474
                or before_rows[r["component"]]["candidate_norad"] == 63474
            ):
                t = mapping[r["component"]]
                inspected.append(
                    dict(
                        **r,
                        start_s=float(t["times"][0]),
                        end_s=float(t["times"][-1]),
                        previously_compatible=before_rows[r["component"]]["compatible"],
                    )
                )
        folder = OUTPUT / arm / "target_phase_transfer"
        folder.mkdir()
        write(folder / "fit.json", after)
        write(folder / "association.json", result)
        write(folder / "inspected_family.json", inspected)
        gains = [
            r
            for r in result["association"]["rows"]
            if r["compatible"] and not before_rows[r["component"]]["compatible"]
        ]
        lost = set(old["associated_observation_ids"]) - set(result["associated_observation_ids"])
        summary = dict(
            arm=arm,
            phase_s=phase,
            associated_points=result["compatible_points"],
            gained_points=result["compatible_points"] - old["compatible_points"],
            lost_points=len(lost),
            gained_fragments=[
                dict(
                    component=r["component"],
                    norad=r["candidate_norad"],
                    points=r["points"],
                    curved=r["active_curvature"],
                    rms_hz=r["rms_hz"],
                    bias_hz=r["bias_hz"],
                )
                for r in gains
            ],
            independent_curved_companions=[
                r["component"] for r in gains if r["active_curvature"] and r["component"] != TARGET
            ],
            diagnostic_target_only_phase_not_a_joint_calibration=True,
        )
        write(folder / "summary.json", summary)
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    run()
