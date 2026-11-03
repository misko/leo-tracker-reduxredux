"""Empirical-Bayes fragment-offset scale, selected by RF evidence without GPS."""

import argparse
import hashlib
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from investigate_dsx01_localization_failures import OUTPUT, DiagnosticNormal, context, fit
from run_dsx01_joint_descent import ARMS, CASES

SCALES_HZ = (50., 100., 200., 300., 600., 1000.)


def run(case):
    scan, sigma, node, _, bindings, _ = context(case)
    rows = []
    for scale in SCALES_HZ:
        pair = {}
        for arm in ARMS:
            reference = np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
            anchor, history = np.zeros(2), []
            for epoch in range(5):
                p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", reference=reference)
                p.constants *= scale / 1000
                result = fit(p, anchor)
                anchor = np.array(result["parameters"])
                reference = np.clip(p.state(anchor)["phases"][p.labels], -15, 15)
                history.append(dict(epoch=epoch, fit=result))
            pair[arm] = dict(fit=result, reference=p.reference, history=history)
        rows.append(dict(sigma_hz=scale, arms=pair))
        print(case, "bias sigma", scale, pair["c0"]["fit"]["score"], flush=True)
    selected = min(rows, key=lambda r: r["arms"]["c0"]["fit"]["score"])
    n = selected["arms"]["c0"]["fit"]["active_points"]
    return dict(case=case, choices=rows, selected_sigma_hz=selected["sigma_hz"],
                selection="lowest same-data full c0 frequency/prior bound, never GPS",
                parameters_added=1, extra_hyperparameter_BIC_penalty=float(np.log(n)),
                caveat="finite-grid empirical Bayes, not a marginalized hyperparameter posterior",
                same_grid_observations_labels_aliases_other_priors_budgets_for_c_pair=True,
                GPS_used=False, source_bindings=bindings,
                code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    path = OUTPUT / args.case / "bias_scale.json"
    if not path.exists():
        write(path, dict(run(args.case), status="complete"))
