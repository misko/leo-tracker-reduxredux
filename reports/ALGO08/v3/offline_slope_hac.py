"""Offline slope variance on ordered residual times and a fixed synthetic stress test."""

import argparse
from collections import defaultdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import numpy as np


STOCK_SOURCE = "8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5"
TRACES = {
    "0220": ("09866aab40a2a083c99c22763382400e3f09e4819dd525f7dc70989a0b1f115f",
             "6e2d1e2a663de2f936297884f7a7524883d21ebf7a59b8545ac1ba8164f3838b"),
    "0086": ("41d1d808bfe657375581bb5083f7b42e4069fca54e9acb945cd54825ee31fa60",
             "80cf9bdba526c0fab14ada5c27ea9fddffc0ac1492a41915ead2c32a58603c80"),
}
COUNTS = (21, 28, 34, 56)
NOISE = {"iid": 0., "independent_contamination": 0., "ar_negative": -.35,
         "ar_moderate": .45, "ar_strong": .75}
SEED, REPEATS = 821109, 2048
SIGMA, FLOOR, CUTOFF = 150., 75., 3.


class BartlettSlope:
    """HAC slope statistic with a fixed elapsed-time kernel and stock noise floor."""

    def __init__(self, times):
        t = np.asarray(times, dtype=float)
        if t.ndim != 1 or len(t) < 4 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
            raise ValueError("At least four strictly increasing finite times required")
        self.n = len(t)
        self.x = t-t.mean()
        self.xx = float(self.x @ self.x)
        self.lag = int(np.floor(np.cbrt(self.n)))
        self.bandwidth_s = (self.lag+1)*float(np.median(np.diff(t)))
        if not np.isfinite(self.xx) or self.xx <= 0 or not np.isfinite(self.bandwidth_s) or self.bandwidth_s <= 0:
            raise ValueError("Finite positive slope design and bandwidth required")
        self.kernel = np.maximum(0., 1-np.abs(t[:, None]-t)/self.bandwidth_s)

    def statistic(self, residual):
        r = np.atleast_2d(np.asarray(residual, dtype=float))
        if r.ndim != 2 or r.shape[1] != self.n or not np.isfinite(r).all():
            raise ValueError("Matching finite residuals required")
        numerator = r @ self.x
        slope = numerator/self.xx
        detrended = r-r.mean(axis=1, keepdims=True)-slope[:, None]*self.x
        score = detrended*self.x
        raw_variance = (self.n/(self.n-2))*np.einsum("bi,ij,bj->b", score, self.kernel, score, optimize=True)
        variance = np.maximum(FLOOR**2*self.xx, raw_variance)
        return dict(slope_hz_per_s=slope, signed_z=numerator/np.sqrt(variance), numerator_variance=variance)


def simulate_noise(rng, ticks, family, rho):
    noise = rng.standard_normal((REPEATS, len(ticks)))
    if family == "independent_contamination":
        sigma = np.where(rng.random(noise.shape) < .05, 3.25, .7)
        noise *= sigma/np.sqrt(.05*3.25**2+.95*.7**2)
    if rho:
        for i, persistence in enumerate(np.power(rho, np.diff(ticks)), start=1):
            noise[:, i] = persistence*noise[:, i-1]+np.sqrt(1-persistence**2)*noise[:, i]
    return SIGMA*noise


def assess(stock_screen, slope, ticks, times, noise, rho, sign):
    observed = noise + sign*4*SIGMA/np.sqrt(slope.xx)*slope.x
    stock = stock_screen(observed, times)
    hac = slope.statistic(observed)["signed_z"]
    numerator = observed @ slope.x
    covariance = np.power(rho, np.abs(ticks[:, None]-ticks))
    oracle = numerator/(SIGMA*np.sqrt(slope.x @ covariance @ slope.x))
    reference = np.copysign(stock["slope_z"], numerator)
    other = ((stock["mean_z"] <= 3.) & (stock["maximum_step_z"] <= 4.) &
             (stock["quadratic_bic_gain"] <= 10.) & (np.abs(stock["lag1_acf"]) <= 4/np.sqrt(slope.n)))
    if not np.array_equal(stock["noise_screen_pass"], other & (np.abs(reference) <= CUTOFF)):
        raise ValueError("Released compatibility is not the pinned gate intersection")
    other &= np.mean(observed**2, axis=1) <= 450.**2
    before, after = np.abs(reference) > CUTOFF, np.abs(hac) > CUTOFF
    count = lambda x: int(np.count_nonzero(x))
    report = dict(n=len(observed), other_eligible=count(other), stock_whole_rejected=count(~other | before),
                  bartlett_whole_rejected=count(~other | after), stock_only_slope_block=count(other & before & ~after),
                  bartlett_only_slope_block=count(other & after & ~before))
    for label, values in (("stock", reference), ("bartlett", hac), ("known_covariance", oracle)):
        report[label+"_slope_flags"] = count(np.abs(values) > CUTOFF)
        report[label+"_correct_direction_flags"] = count(sign*values > CUTOFF) if sign else 0
    return report


def synthetic(stock_screen):
    rng, cells = np.random.default_rng(SEED), []
    for n in COUNTS:
        for layout in ("regular", "gapped"):
            gaps = np.ones(n-1, dtype=int) if layout == "regular" else np.resize([1, 1, 2, 1, 8, 1, 3, 1], n-1)
            ticks = np.r_[0, gaps.cumsum()]
            times = .5*ticks
            model = BartlettSlope(times)
            for family, rho in NOISE.items():
                noise = simulate_noise(rng, ticks, family, rho)
                covariance = np.power(rho, np.abs(ticks[:, None]-ticks))
                true_ratio = float(model.x @ covariance @ model.x / model.xx)
                for sign in (0, -1, 1):
                    metrics = assess(stock_screen, model, ticks, times, noise, rho, sign)
                    cells.append(dict(n_points=n, layout=layout, family=family, slope_sign=sign,
                                      bandwidth_s=model.bandwidth_s, known_variance_vs_white=true_ratio, metrics=metrics))
    aggregate = defaultdict(lambda: defaultdict(int))
    for cell in cells:
        key = cell["family"], cell["slope_sign"]
        for k, value in cell["metrics"].items():
            aggregate[key][k] += value
    return dict(seed=SEED, repeats_per_cell=REPEATS, cells=cells,
                aggregate=[dict(family=family, slope_sign=sign, metrics=metrics)
                           for (family, sign), metrics in aggregate.items()])


def checked(path, digest):
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError(f"Sealed source or record changed: {path.name}")
    return body


def physical_summary(trace_root):
    summary = {}
    for case, (stage_pin, gate_pin) in TRACES.items():
        root = trace_root / f"leo-v3-second-gate-{case}-run01/run"
        stage = json.loads(checked(root / "stage-result.json", stage_pin))
        gate = json.loads(checked(root / "after_salvage.json", gate_pin))
        if stage["masks"]["after_salvage"] != gate_pin or gate["screen"] != "after_salvage":
            raise ValueError("The stored rows are from a different screen")
        rows = []
        for row in gate["tracks"]:
            conditional = row["conditional"]
            n, diag = row["points"], conditional["diagnostics"]
            if len(row["observation_ids"]) != n:
                raise ValueError("Unexpected archived active point count")
            if (conditional["rms_hz"] <= 450 and diag["mean_z"] <= 3
                    and diag["maximum_step_z"] <= 4 and diag["quadratic_bic_gain"] <= 10
                    and abs(diag["lag1_acf"]) <= 4/np.sqrt(n) and diag["slope_z"] > CUTOFF):
                competing_blocks = [key for key, passed in row["actual_tests"].items()
                                    if key != "conditional" and passed is False]
                rows.append(dict(component=row["component"], points=n, slope_z=diag["slope_z"],
                                 lag1=diag["lag1_acf"], lag1_limit=4/np.sqrt(n),
                                 variance_ratio_needed_for_slope_gate=(diag["slope_z"]/CUTOFF)**2,
                                 competing_blocks=competing_blocks))
        # These scalar traces preserve ordered observation IDs, not the
        # released gate's time/residual inputs for a counterfactual.
        summary[case] = dict(gate_sha256=gate_pin, stage_sha256=stage_pin, slope_only_rows=rows,
                             slope_only_points=sum(r["points"] for r in rows),
                             points_blocked_by_conditional_slope_alone=sum(r["points"] for r in rows if not r["competing_blocks"]),
                             vector_scores=0)
    return summary


def load_stock(path):
    checked(path, STOCK_SOURCE)
    spec = importlib.util.spec_from_file_location("frozen_noise_screen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.batch_noise_screen


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stock_source", type=Path)
    cli.add_argument("trace_root", type=Path)
    args = cli.parse_args()
    receipt = dict(stock_source_sha256=STOCK_SOURCE, physical=physical_summary(args.trace_root),
                   synthetic=synthetic(load_stock(args.stock_source)))
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
