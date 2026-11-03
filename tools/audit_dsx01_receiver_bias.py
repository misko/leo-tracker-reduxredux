"""Oracle-only family attribution after receiver-drift relaxation.

The supplied GPS enters only this audit. Nuisance fits and gradients saved here
must never initialize the blind experiments.
"""

import argparse
import json
from collections import defaultdict

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from prototype_dsx01_continuous_position import CENTER
from prototype_dsx01_receiver_geometry import OUTPUT, geometry_problem
from report_dsx01_model_iterations import REFERENCE

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton


def run(case, method, *, mean=10.0, height=0.0):
    source = OUTPUT / case / method / "endpoints.json"
    data = json.loads(source.read_text())
    variant = f"mean_{mean:g}_height_{height:g}"
    directory = OUTPUT / "oracle_only" / case
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{method}_{variant}.json"
    results = {}
    scan = Scan(case)
    reference = np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )
    for arm in ("c0", "fitted_c"):
        fit = data[f"{variant}/{arm}"]
        p = geometry_problem(
            scan,
            dict(rows=fit["rows"], state=fit["state"]),
            method,
            arm == "fitted_c",
            fit["east_north_km"],
            mean_sigma=mean,
            height_sigma=height,
        )
        p.alias = fit["aliases"]
        blind = np.array(min(fit["fits"], key=lambda f: f["score"])["parameters"])
        oracle_fit = bounded_gauss_newton(
            lambda x, problem=p: problem.residual(np.r_[reference, x]),
            blind[2:],
            p.lower[2:],
            p.upper[2:],
            iterations=32,
        )
        oracle = np.r_[reference, oracle_fit["parameters"]]
        ro, do = p.residual(oracle, details=True)
        rb, db = p.residual(blind, details=True)
        families = defaultdict(
            lambda: dict(points=0, fragments=0, oracle_cost=0.0, blind_cost=0.0, components=[])
        )
        for a, b in zip(do, db, strict=True):
            f = families[a["norad"]]
            f["points"] += a["points"]
            f["fragments"] += 1
            f["oracle_cost"] += a["cost"]
            f["blind_cost"] += b["cost"]
            f["components"].append(a["component"])
        for f in families.values():
            f["blind_minus_oracle"] = f["blind_cost"] - f["oracle_cost"]
        results[arm] = dict(
            oracle_only_never_reuse_for_initialization=True,
            blind_position=blind[:2],
            reference_position=reference,
            blind_loss=float(rb @ rb),
            oracle_loss=float(ro @ ro),
            blind_data_cost=sum(r["cost"] for r in db),
            oracle_data_cost=sum(r["cost"] for r in do),
            blind_prior_and_visibility=float(rb @ rb) - sum(r["cost"] for r in db),
            oracle_prior_and_visibility=float(ro @ ro) - sum(r["cost"] for r in do),
            families=dict(sorted(families.items(), key=lambda f: f[1]["blind_minus_oracle"])),
            oracle_state=p.decode(oracle),
            blind_state=p.decode(blind),
            oracle_nuisance_history=oracle_fit["history"],
        )
        print(
            case, method, arm, results[arm]["blind_loss"], results[arm]["oracle_loss"], flush=True
        )
    write(path, results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--method", default="shared_phase")
    args = parser.parse_args()
    run(args.case, args.method)
