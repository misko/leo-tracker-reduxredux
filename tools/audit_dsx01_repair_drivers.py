"""Explicit GPS-only oracle audit; never imported by blind repair fitters."""

import argparse
import json
from collections import defaultdict

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import CENTER
from prototype_dsx01_receiver_geometry import OUTPUT as BASELINE
from prototype_dsx01_receiver_geometry import geometry_problem
from report_dsx01_model_iterations import REFERENCE

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton


def run(case):
    path = OUTPUT / "oracle_only" / case / "baseline_drivers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    results = json.loads(path.read_text()) if path.exists() else {}
    scan = Scan(case)
    target = np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )
    for method in METHODS:
        if method in results:
            continue
        fit = json.loads((BASELINE / case / method / "endpoints.json").read_text())[
            "mean_10_height_0/fitted_c"
        ]
        p = geometry_problem(
            scan,
            dict(rows=fit["rows"], state=fit["state"]),
            method,
            True,
            fit["east_north_km"],
            mean_sigma=10,
            height_sigma=0,
        )
        p.problem.alias = list(fit["aliases"])
        x = np.array(min(fit["fits"], key=lambda r: r["score"])["parameters"])
        rb, db = p.residual(x, details=True)

        def residual(z, problem=p):
            return problem.residual(np.r_[target, z])

        oracle = bounded_gauss_newton(residual, x[2:], p.lower[2:], p.upper[2:], iterations=24)
        xo = np.r_[target, oracle["parameters"]]
        ro, do = p.residual(xo, details=True)
        groups = defaultdict(
            lambda: dict(points=0, fragments=0, blind_cost=0.0, oracle_cost=0.0, components=[])
        )
        for a, b in zip(db, do, strict=True):
            r = groups[int(a["norad"])]
            r["points"] += a["points"]
            r["fragments"] += 1
            r["blind_cost"] += a["cost"]
            r["oracle_cost"] += b["cost"]
            r["components"].append(a["component"])
        for r in groups.values():
            r["blind_minus_oracle_cost"] = r["blind_cost"] - r["oracle_cost"]
        results[method] = dict(
            diagnostic_only_never_reuse_in_blind_initialization=True,
            blind_east_north_km=x[:2],
            oracle_east_north_km=target,
            blind_loss=float(rb @ rb),
            oracle_loss=float(ro @ ro),
            blind_data_cost=sum(r["cost"] for r in db),
            oracle_data_cost=sum(r["cost"] for r in do),
            blind_prior_and_visibility=float(rb @ rb) - sum(r["cost"] for r in db),
            oracle_prior_and_visibility=float(ro @ ro) - sum(r["cost"] for r in do),
            families=dict(
                sorted(groups.items(), key=lambda pair: pair[1]["blind_minus_oracle_cost"])
            ),
            oracle_fit=oracle,
        )
        write(path, results)
        print(case, method, "blind/oracle", float(rb @ rb), float(ro @ ro), flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    run(p.parse_args().case)
