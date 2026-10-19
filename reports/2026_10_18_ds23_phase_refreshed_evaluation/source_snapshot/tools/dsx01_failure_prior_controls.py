"""Small, location-independent prior controls; no GPS enters this module."""

import argparse
import hashlib
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from investigate_dsx01_localization_failures import OUTPUT, DiagnosticNormal, context, fit
from run_dsx01_joint_descent import ARMS, CASES

CONTROLS = ("smooth_20", "linear_radio_only", "independent_band_drift_2",
            "phase_orbit_3", "smooth20_independent2", "hierarchical_clock_300")


class ExtraControl(DiagnosticNormal):
    def __init__(self, scan, node, sigma, fitted_c, *, extra, reference):
        super().__init__(scan, node, sigma, fitted_c, reference=reference)
        if extra not in CONTROLS:
            raise ValueError("unknown general prior control")
        self.extra = extra
        if extra == "hierarchical_clock_300":
            self.clock = np.column_stack([(self.flat_labels == j) * self.q * 1000
                                          for j in self.supported_local])
            self.clock_reference_scale_hz = 1000.

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        features = result["features"]
        nb, ns = self.hardware.shape[1], self.smooth.shape[1]
        if self.clock.shape[1]:
            stop = features.shape[1] - len(self.members)
            features = np.column_stack((features[:, :stop], self.clock, features[:, stop:]))
        scale = np.ones(features.shape[1])
        if self.extra in ("smooth_20", "smooth20_independent2", "linear_radio_only"):
            scale[nb:nb + ns] = 0 if self.extra == "linear_radio_only" else .1
        if self.extra in ("independent_band_drift_2", "smooth20_independent2"):
            scale[[4, 6]], scale[[5, 7]] = np.sqrt(2) / 10, 2 * np.sqrt(2)
        if self.extra == "phase_orbit_3":
            scale[nb + ns:-len(self.members)] = 3
        if self.extra == "hierarchical_clock_300":
            scale[-len(self.members):] = .3
        raw = self.values - self.q * result["intercept"]
        bound = hierarchical_bound(raw, features * scale, self.point_noise, self.noise_groups)
        bound["coefficient"] *= scale
        use = scale > 0
        bound["coefficient_prior_precision"][use] /= scale[use]**2
        bound["conditional_residual_hz"] = raw - features @ bound["coefficient"]
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.noise_volume)]
        result.update(bound, features=features)
        return result


def run(case):
    scan, sigma, node, _, bindings, _ = context(case)
    rows = []
    for name in CONTROLS:
        for arm in ARMS:
            reference = np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
            anchor, history = np.zeros(2), []
            for epoch in range(5):
                p = ExtraControl(scan, node, sigma, arm == "fitted_c", extra=name,
                                 reference=reference)
                result = fit(p, anchor)
                anchor = np.array(result["parameters"])
                phase = p.state(anchor)["phases"][p.labels]
                history.append(dict(epoch=epoch, fit=result, phase_reference=reference.copy()))
                reference = np.clip(phase, -15, 15)
            rows.append(dict(control=name, arm=arm, fit=result, history=history,
                             reference=p.reference))
        print(case, name, flush=True)
    return dict(case=case, interventions=rows, source_bindings=bindings, GPS_used=False,
                parameters_added_by_nonclock_controls=0,
                controls_fixed_before_evaluation_not_tuned_to_GPS=True,
                common_labels_aliases_observations_other_priors_starts_budgets_for_c_pair=True,
                code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    path = OUTPUT / args.case / "prior_controls.json"
    if not path.exists():
        result = run(args.case)
        write(path, dict(result, status="complete"))
