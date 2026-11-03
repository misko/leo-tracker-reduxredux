"""Oracle-only attribution of blind fixed-family fit bias; no inference reuse."""

import argparse
import json
from collections import defaultdict

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import CENTER, OUTPUT, FixedFamilies

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

REFERENCE = (37.849061591561885, -122.48574968092912)


def run(case):
    directory = OUTPUT / case
    seed = json.loads((directory / "mill_valley_center_seeds.json").read_text())
    endpoints = json.loads((directory / "endpoints.json").read_text())
    scan = Scan(case)
    reference = np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )
    output = directory / "oracle_continuous_bias.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    for method in METHODS:
        for arm in ("c0", "fitted_c"):
            key = f"continuous/{arm}/{method}"
            if key in results or key not in endpoints:
                continue
            p = FixedFamilies(scan, seed[f"c0/{method}"], method, "continuous", arm == "fitted_c")
            endpoint = min(endpoints[key]["fits"], key=lambda r: r["score"])
            blind = np.array(endpoint["parameters"])
            fit = bounded_gauss_newton(
                lambda x, problem=p: problem.residual(np.r_[reference, x]),
                blind[2:],
                p.lower[2:],
                p.upper[2:],
                iterations=32,
            )
            oracle = np.r_[reference, fit["parameters"]]
            r0, d0 = p.residual(oracle, details=True)
            r1, d1 = p.residual(blind, details=True)
            families = defaultdict(
                lambda: dict(
                    points=0,
                    curves=0,
                    oracle_data_cost=0.0,
                    blind_data_cost=0.0,
                    components=[],
                    geographic_gradient=[0.0, 0.0],
                )
            )
            for a, b in zip(d0, d1, strict=True):
                group = families[a["norad"]]
                group["points"] += a["points"]
                group["curves"] += 1
                group["oracle_data_cost"] += a["cost"]
                group["blind_data_cost"] += b["cost"]
                group["components"].append(a["component"])
            for axis in range(2):
                a, b = oracle.copy(), oracle.copy()
                a[axis] -= 0.05
                b[axis] += 0.05
                da = p.residual(a, details=True)[1]
                db = p.residual(b, details=True)[1]
                for u, v in zip(da, db, strict=True):
                    families[u["norad"]]["geographic_gradient"][axis] += (
                        v["cost"] - u["cost"]
                    ) / 0.1
            for v in families.values():
                v["data_loss_delta"] = v["blind_data_cost"] - v["oracle_data_cost"]
            data0, data1 = sum(d["cost"] for d in d0), sum(d["cost"] for d in d1)
            results[key] = dict(
                oracle_only_no_blind_reuse=True,
                blind_position=blind[:2],
                reference_position=reference,
                oracle_profiled_loss=float(r0 @ r0),
                blind_profiled_loss=float(r1 @ r1),
                oracle_data_term=data0,
                blind_data_term=data1,
                oracle_prior_visibility_term=float(r0 @ r0) - data0,
                blind_prior_visibility_term=float(r1 @ r1) - data1,
                oracle_state=p.decode(oracle),
                blind_state=p.decode(blind),
                families=dict(sorted(families.items(), key=lambda r: r[1]["data_loss_delta"])),
                oracle_nuisance_history=fit["history"],
            )
            write(output, results)
            print(case, key, round(float(r0 @ r0), 2), round(float(r1 @ r1), 2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    run(parser.parse_args().case)
