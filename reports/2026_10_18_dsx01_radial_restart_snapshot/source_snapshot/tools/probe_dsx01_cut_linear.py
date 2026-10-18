"""Blind curved-calibration transfer: diagnose previously unused linear evidence."""

import argparse
import hashlib
import json
import time

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_prior_bias_iterations import problem_for
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_cut_linear import curve_posterior, predictive_gaussian, transfer_design
from dsx01_smooth_background import background_logprob
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import reference_xy
from run_dsx01_clock_transfer import measurement_path

from leo.analysis.research.retained_track_likelihood import PERIOD

OUTPUT = ROOT / "reports/2026_10_18_dsx01_cut_linear"
VARIANTS = ("joint", "shape", "continuation")


def dense_cost(raw, design, mean, root, bias_sigma):
    y = raw - design @ mean
    v = design @ root
    covariance = v @ v.T + 150**2 * np.eye(len(y)) + bias_sigma**2
    chol = np.linalg.cholesky(covariance)
    z = np.linalg.solve(chol, y)
    return float(z @ z + 2 * np.log(np.diag(chol)).sum() + len(y) * np.log(2 * np.pi))


def prepare(case):
    scan = Scan(case)
    apply_measurements(scan, json.loads(measurement_path(case).read_text())["points"], "glrt300")
    source = (
        ROOT / "reports/2026_10_18_dsx01_satellite_prior_controls" / case / "normal/endpoints.json"
    )
    fits = json.loads(source.read_text())["fits"]
    problems = {arm: problem_for(scan, fit, "normal") for arm, fit in fits.items()}
    details = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_prior_bias_iterations/frequency_details.json").read_text()
    )
    accepted = {
        r["component"]
        for r in details[f"{case}/normal/c0"]["native_gate"]["tracks"]
        if r["compatible"]
    }
    p = problems["c0"]
    owners, groups, anchors = {}, set(), {}
    for i, row in zip(p.members, p.rows, strict=True):
        t, j = scan.tracks[i], row["candidate_index"]
        if t["key"] in accepted:
            owners.setdefault(j, set()).add((t["receiver"], t["channel"]))
            groups.add((t["receiver"], t["channel"] > 4))
            anchors.setdefault(j, []).append(t)
    candidates = [j for j in p.supported if len(owners.get(j, set())) >= 2]
    x = np.array(fits["c0"]["parameters"])
    result, root = curve_posterior(p, x)
    nominations = []
    for i, t in enumerate(scan.tracks):
        if i in scan.curved or len(t["times"]) < 6 or np.ptp(t["times"]) <= 0:
            continue
        supported_group = (t["receiver"], t["channel"] > 4) in groups
        choices = []
        for j in candidates if supported_group else []:
            intercept, design, elevation = transfer_design(p, t, j, x)
            if elevation.min() < 0:
                continue
            alias = int(
                np.rint(np.mean(intercept + design @ result["coefficient"] - t["values"]) / PERIOD)
            )
            raw = t["values"] + alias * PERIOD - intercept
            cost = dense_cost(raw, design, result["coefficient"], root, 1000)
            same_channel = [
                a
                for a in anchors[j]
                if (a["receiver"], a["channel"]) == (t["receiver"], t["channel"])
            ]
            gap = min(
                (
                    max(
                        0.0,
                        float(t["times"].min() - a["times"].max()),
                        float(a["times"].min() - t["times"].max()),
                    )
                    for a in same_channel
                ),
                default=float("inf"),
            )
            choices.append(
                dict(
                    candidate_index=j,
                    norad=int(scan.norads[j]),
                    alias=alias,
                    cost=cost,
                    same_channel_gap_s=gap if np.isfinite(gap) else None,
                )
            )
        choices.sort(key=lambda r: r["cost"])
        background = background_logprob(t["values"], t["times"], 150.0)["log_probability"]
        if choices:
            best = choices[0]
            # Equal prior over the frozen family pool, plus 5% smooth background.
            log_signal = -best["cost"] / 2 - np.log(max(1, len(candidates)))
            odds = np.log(0.95 / 0.05) + log_signal - background
            margin = (choices[1]["cost"] - best["cost"]) / 2 if len(choices) > 1 else float("inf")
            accepted_linear = odds >= np.log(99) and margin >= np.log(10)
        else:
            best, odds, margin, accepted_linear = {}, -float("inf"), 0.0, False
        nominations.append(
            dict(
                index=i,
                component=t["key"],
                points=len(t["times"]),
                accepted=accepted_linear,
                log_signal_background_odds=odds if np.isfinite(odds) else None,
                log_identity_margin=margin if np.isfinite(margin) else None,
                **best,
            )
        )
    return scan, fits, problems, nominations, source


class CutScore:
    def __init__(self, problem, nominations, variant):
        self.problem, self.variant = problem, variant
        self.selected = [
            n
            for n in nominations
            if n["accepted"]
            and (
                variant != "continuation"
                or (n["same_channel_gap_s"] is not None and n["same_channel_gap_s"] <= 10)
            )
        ]
        self.cache = {}

    def score(self, x):
        key = tuple(np.asarray(x, float))
        if key in self.cache:
            return self.cache[key]
        p = self.problem
        result, root = curve_posterior(p, x)
        curved = float(
            result["residual"] @ result["residual"]
            + np.sum((np.maximum(0, -result["elevation"]) / 2) ** 2)
        )
        raw, designs, groups = [], [], []
        for k, row in enumerate(self.selected):
            t = p.scan.tracks[row["index"]]
            intercept, design, elevation = transfer_design(p, t, row["candidate_index"], x)
            raw.append(t["values"] + row["alias"] * PERIOD - intercept)
            designs.append(design)
            groups.extend([k] * len(t["times"]))
        linear = 0.0
        if raw:
            pred = predictive_gaussian(
                np.concatenate(raw),
                np.vstack(designs),
                result["coefficient"],
                root,
                sigma=150.0,
                bias_sigma=1e6 if self.variant == "shape" else 1000.0,
                groups=np.array(groups),
            )
            linear = pred["negative_twice_log_probability"]
        value = dict(curved=curved, linear=linear, total=curved + linear)
        self.cache[key] = value
        return value


def run(case):
    mark = time.monotonic()
    scan, fits, problems, nominations, source = prepare(case)
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    write(directory / "nominations.json", nominations)
    rows = []
    truth = reference_xy()  # Used only after nominations are frozen.
    for variant in VARIANTS:
        for arm, p in problems.items():
            score = CutScore(p, nominations, variant)
            x = np.asarray(fits[arm]["parameters"])
            at_fit, at_truth = score.score(x), score.score(truth)
            step = 0.1
            gradients = {
                key: [
                    (
                        score.score(x + np.eye(2)[k] * step)[key]
                        - score.score(x - np.eye(2)[k] * step)[key]
                    )
                    / (2 * step)
                    for k in range(2)
                ]
                for key in ("curved", "linear", "total")
            }
            delta = truth - x
            rows.append(
                dict(
                    variant=variant,
                    arm=arm,
                    selected_tracks=len(score.selected),
                    selected_points=sum(n["points"] for n in score.selected),
                    endpoint=at_fit,
                    evaluation_GPS=at_truth,
                    GPS_minus_endpoint={k: at_truth[k] - at_fit[k] for k in at_fit},
                    gradient_east_north=gradients,
                    direction_to_evaluation_GPS=delta.tolist(),
                    linear_descent_alignment=float(-np.dot(gradients["linear"], delta)),
                )
            )
            print(json.dumps(dict(case=case, **rows[-1])), flush=True)
    write(
        directory / "diagnostic.json",
        dict(
            case=case,
            curved_points=sum(len(scan.tracks[i]["times"]) for i in scan.curved),
            other_polynomial_points=sum(
                len(t["times"]) for i, t in enumerate(scan.tracks) if i not in scan.curved
            ),
            nominations_sha256=hashlib.sha256(
                (directory / "nominations.json").read_bytes()
            ).hexdigest(),
            source_endpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            no_GPS_in_nominations=True,
            rows=rows,
            seconds=time.monotonic() - mark,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    run(parser.parse_args().case)
