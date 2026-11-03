"""Training-only optimizer scaling audit; preserve the frozen primary result."""

import hashlib
import json
from pathlib import Path

import numpy as np
from model import objective, prediction
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    old = json.loads((HERE / "results.json").read_text())
    for p, h in old["hashes"].items():
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == h, p
    prior = json.loads((REPORTS / "2026_09_29_frequency_peak_tracking/results.json").read_text())
    groups, rows = [], []
    for group in old["groups"]:
        name, rx = group["signal"], group["receiver"]
        with np.load(
            REPORTS / f"2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz",
            allow_pickle=False,
        ) as archive:
            values = archive[f"rx{rx}"]
        series = sorted(
            [r for r in prior["series"] if r["signal"] == name and r["receiver"] == rx],
            key=lambda r: r["frame"],
        )
        coarse = np.array([r["frequencies"]["global_peak"] for r in series])
        mhz = np.array(group["mhz"])
        scale = np.r_[np.full(30, 1000.0), 100.0]
        initial = np.r_[group["fit"]["frequency_corrections_hz"], group["fit"]["drift_ppm"]]

        def fun(z, scale=scale, values=values, mhz=mhz, coarse=coarse):
            value, gradient = objective(z * scale, values[:30], mhz, coarse[:30])
            return value, gradient * scale

        fit = minimize(
            fun,
            initial / scale,
            jac=True,
            method="L-BFGS-B",
            bounds=[(-1.5, 1.5)] * 30 + [(-3.0, 3.0)],
            options=dict(maxiter=400, ftol=1e-13, gtol=1e-8, maxls=30),
        )
        physical = fit.x * scale
        qualified = bool(
            fit.success
            and max(abs(fit.jac)) < 1e-5
            and max(abs(physical[:-1])) < 1499
            and abs(physical[-1]) < 299
        )
        drift = float(physical[-1]) if qualified else 0.0
        groups.append(
            dict(
                signal=name,
                receiver=rx,
                dataset=group["dataset"],
                qualified=qualified,
                drift_ppm=float(physical[-1]),
                applied_drift_ppm=drift,
                success=bool(fit.success),
                max_scaled_gradient=float(max(abs(fit.jac))),
                objective=float(fit.fun),
                training_objective_gain=float(group["fit"]["objective"] - fit.fun),
                initial_drift_ppm=group["fit"]["drift_ppm"],
            )
        )
        for frame in range(30, 80):
            rows.append(
                dict(
                    signal=name,
                    receiver=rx,
                    dataset=group["dataset"],
                    frame=frame,
                    arms={
                        arm: prediction(values[frame], mhz, coarse[frame], d)
                        for arm, d in (("zero", 0.0), ("shared", drift), ("reversed", -drift))
                    },
                )
            )
    with (HERE / "scaled-results.json").open("x") as out:
        json.dump(
            dict(
                groups=groups,
                rows=rows,
                primary_sha256=hashlib.sha256((HERE / "results.json").read_bytes()).hexdigest(),
                audit_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            ),
            out,
            indent=2,
            allow_nan=False,
        )
    for g in groups:
        print(g, flush=True)


if __name__ == "__main__":
    main()
