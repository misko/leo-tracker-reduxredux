"""Bounded RF diagnostics for DS23-0217; no reference coordinate in this module."""

import argparse
import copy
import time

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_inference_audit import disk_grid
from dsx01_joint_marginal import JointMarginal, integrated_gaussian
from dsx01_radial_restarts import discover_at_start
from investigate_ds23_adaptive_failures import decompose, phase_widths
from investigate_dsx01_localization_failures import DiagnosticNormal, fit
from map_dsx01_clean_region import finite_gradient
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import OUT as SOURCE
from run_algo01_ds23_sample import ROOT, final_scan, read, sha
from run_dsx01_clean_region import zero_state
from run_dsx01_joint_descent import descend, signature

CASE = "DS23-0217"
OUT = ROOT / "reports/2026_10_18_algo01_ds23_0217"
ARMS = ("c0", "fitted_c")
STARTS = sorted(disk_grid(step_km=2)[1], key=lambda x: (float(np.linalg.norm(x)), *x))
DISCOVERY_STARTS = sorted(disk_grid(step_km=5)[1], key=lambda x: (float(np.linalg.norm(x)), *x))


class FixedGaussian(DiagnosticNormal):
    """Mechanism ablation: retain radio noise and priors, fix every precision to1."""

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        features = result["features"]
        raw = self.values - self.q * result["intercept"]
        bound = integrated_gaussian(
            raw[self.keep], features[self.keep], self.point_noise[self.keep]
        )
        normalization = float(np.sum(np.log(2 * np.pi) + 2 * np.log(self.point_noise[self.keep])))
        exact_cost = float(bound["residual"] @ bound["residual"] + normalization)
        bound.update(
            coefficient_prior_precision=np.ones(features.shape[1]),
            conditional_residual_hz=raw - features @ bound["coefficient"],
            noise_precision=np.array([float(self.keep[sl].any()) for sl in self.slices]),
            gamma_cost=0.0,
            noise_gamma_cost=0.0,
            prior_gamma_cost=0.0,
            normalization_constant=normalization,
            negative_twice_elbo=exact_cost,
            precision_iterations=1,
            final_log_precision_change=0.0,
        )
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.noise_volume)]
        result.update(bound)
        return result


def context():
    scan = final_scan(CASE)
    baseline = read(SOURCE / CASE / "result.json")
    return scan, baseline["final_node"], np.asarray(baseline["final_mask"], bool), baseline


def problem(scan, node, arm, keep, reference=None, variant="baseline"):
    control = {
        "bias300": "independent_bias_300",
        "drift1": "drift_1",
        "orbit3": "orbit_3",
        "colored": "colored",
    }.get(variant, "baseline")
    cls = FixedGaussian if variant == "fixed_gaussian" else DiagnosticNormal
    p = cls(
        scan,
        node,
        scan.radio_sigma_hz,
        arm == "fitted_c",
        keep=keep,
        reference=reference,
        control=control,
    )
    cache = getattr(scan, "diagnostic_phase_width_cache", {})
    key = tuple(p.labels)
    if key not in cache:
        cache[key] = phase_widths(scan, p.labels)[0]
    scan.diagnostic_phase_width_cache = cache
    p.phase_sigma = cache[key].copy()
    if variant == "phase_floor3":
        p.phase_sigma = np.maximum(p.phase_sigma, 3)
    elif variant == "phase_x2":
        p.phase_sigma = np.minimum(p.phase_sigma * 2, 15)
    return p


def diagnostics(p, x):
    c = p.calculate(x)
    d = decompose(p, x)
    d.update(
        endpoint_east_north_km=x,
        endpoint_latlon=latlon(x),
        state=p.state(x),
        active_points=int(p.keep.sum()),
        phase_reference=p.reference,
        phases_sigma_s=p.phase_sigma,
        supported_orbit_families=p.supported,
        normalization_constant=c["normalization_constant"],
        weighted_data_cost=c["quadratic"] - sum(d["prior_cost"].values()),
        conditional_residual_hz=c["conditional_residual_hz"],
        noise_precision=c["noise_precision"],
    )
    return d


def fixed(scan, node, keep, arm, point, variant="baseline", rounds=5):
    reference = np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
    for _ in range(rounds):
        p = problem(scan, node, arm, keep, reference, variant)
        phase = p.state(point)["phases"][p.labels]
        change = float(max(abs(phase - reference)))
        reference = np.clip(phase, -15, 15)
    d = diagnostics(p, point)
    d["last_phase_change_s"] = change
    return p, d


def refit(scan, node, keep, arm, variant="baseline", start=(0, 0)):
    reference = np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]}))
    anchor, history = np.asarray(start, float), []
    for epoch in range(5):
        p = problem(scan, node, arm, keep, reference, variant)
        fitted = fit(p, anchor)
        anchor = np.asarray(fitted["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(
            dict(epoch=epoch, fit=fitted, max_phase_change_s=float(max(abs(phase - reference))))
        )
        reference = np.clip(phase, -15, 15)
    d = diagnostics(p, anchor)
    d.update(
        history=history,
        last_phase_change_s=history[-1]["max_phase_change_s"],
        gradient=finite_gradient(lambda xy: float(p.residual(xy) @ p.residual(xy)), anchor),
    )
    return d


def audit(point):
    scan, node, keep, baseline = context()
    arms = {}
    for arm in ARMS:
        saved = baseline["arms"][arm]["record"]
        x = np.asarray(saved["endpoint_east_north_km"])
        p = problem(scan, node, arm, keep, np.asarray(saved["phase_reference"]))
        endpoint = diagnostics(p, x)
        assert abs(endpoint["score"] - saved["score"]) < 1e-5
        _, at_point = fixed(scan, node, keep, arm, point)

        def evaluate(xy, arm=arm):
            return fixed(scan, node, keep, arm, xy)[1]["score"]

        arms[arm] = dict(
            endpoint=endpoint,
            at_diagnostic_point=at_point,
            gradient_at_endpoint=finite_gradient(
                lambda xy, p=p: float(p.residual(xy) @ p.residual(xy)), x
            ),
            refreshed_gradient_at_point=finite_gradient(evaluate, point),
            diagnostic_point_started_refit=refit(scan, node, keep, arm, start=point),
            exact_score_at_endpoint_reference=evaluate(x),
            label="Diagnostic point is externally supplied for evaluation, never a production seed",
        )
    write(OUT / "audit.json", dict(arms=arms, diagnostic_point=point, no_future_TLE=True))


def intervention(kind, index):
    scan, node, keep, _ = context()
    p = problem(scan, node, "c0", keep)
    if kind == "family":
        targets = [
            (
                str(int(scan.norads[j])),
                [k for k, r in enumerate(p.rows) if r["candidate_index"] == j],
            )
            for j in p.labels
        ]
    elif kind == "track":
        targets = [(r["component"], [k]) for k, r in enumerate(p.rows)]
    else:
        names = (
            "baseline",
            "phase_floor3",
            "phase_x2",
            "bias300",
            "drift1",
            "orbit3",
            "colored",
            "fixed_gaussian",
        )
        targets = [(name, []) for name in names]
    target, members = targets[index]
    for k in members:
        keep[p.slices[k]] = False
    pair = {
        arm: refit(scan, node, keep, arm, target if kind == "prior" else "baseline") for arm in ARMS
    }
    write(
        OUT / f"{kind}_{index:02d}.json",
        dict(
            target=target,
            kind=kind,
            arms=pair,
            deleted_points=len(p.values) - int(keep.sum()),
            GPS_used=False,
            fixed_original_nuisance_prior_support=True,
            interpretation="Influence/sensitivity, not a GPS-based rejection rule",
        ),
    )
    print(kind, index, target, flush=True)


def discover(index):
    scan, _, _, _ = context()
    record = discover_at_start(scan, scan.radio_sigma_hz, DISCOVERY_STARTS[index], budget=4)
    node = dict(
        seed=dict(rows=record["seed"]["rows"], state=zero_state(scan)), aliases=record["aliases"]
    )
    write(
        OUT / f"discovery_{index:02d}.json", dict(node=node, receipt=record["discovery_provenance"])
    )


def bank():
    scan, base, keep, _ = context()
    original = read(SOURCE / CASE / "fit_radio_noise.json")
    candidates = [copy.deepcopy(c["node"]) for c in original["choices"]]
    bindings = {}
    for index in range(len(DISCOVERY_STARTS)):
        path = OUT / f"discovery_{index:02d}.json"
        candidates.append(read(path)["node"])
        bindings[path.name] = sha(path)
    nodes, seen = [], set()
    population = {r["component"] for r in base["seed"]["rows"]}
    for candidate in candidates:
        assert {r["component"] for r in candidate["seed"]["rows"]} == population
        candidate["seed"]["state"] = zero_state(scan)
        key = signature(candidate)
        if key not in seen:
            seen.add(key)
            nodes.append(candidate)
    write(
        OUT / "hypothesis_bank.json",
        dict(
            nodes=nodes,
            discovery_bindings=bindings,
            same_observation_population=True,
            candidates=len(scan.norads),
            fitted_state_discarded=True,
            GPS_used=False,
            observations=int(keep.sum()),
        ),
    )
    print("distinct hypotheses", len(nodes), flush=True)


def restart(index):
    scan, _, keep, _ = context()
    nodes = read(OUT / "hypothesis_bank.json")["nodes"]
    arm_results = {}
    selected = None
    # c0 alone selects the branch schedule. Fitted-c follows the same schedule,
    # preserving matched discrete hypotheses/priors/budgets for the c ablation.
    for arm in ARMS:
        references = [
            np.zeros(len({r["candidate_index"] for r in n["seed"]["rows"]})) for n in nodes
        ]
        anchor, history = np.asarray(STARTS[index], float), []
        for epoch in range(5):
            problems = [
                problem(scan, n, arm, keep, ref) for n, ref in zip(nodes, references, strict=True)
            ]
            if arm == "c0":
                descent = descend(problems, anchor, max_steps=48)
                chosen = descent["final_mode"]
            else:
                chosen = selected[epoch]
                fitted = fit(problems[chosen], anchor)
                descent = dict(
                    parameters=fitted["parameters"],
                    score=fitted["score"],
                    final_mode=chosen,
                    trace=[
                        dict(point=s["parameters"], score=s["score"], mode=chosen)
                        for s in fitted["history"]
                    ],
                    switches=[],
                    stopped=fitted["stopped"],
                )
            anchor = np.asarray(descent["parameters"])
            changes = []
            for k, p in enumerate(problems):
                phase = p.state(anchor)["phases"][p.labels]
                changes.append(float(max(abs(phase - references[k]))))
                references[k] = np.clip(phase, -15, 15)
            history.append(
                dict(epoch=epoch, descent=descent, phase_changes_s=changes, selected_mode=chosen)
            )
        if arm == "c0":
            selected = [h["selected_mode"] for h in history]
        d = diagnostics(problems[chosen], anchor)
        d.update(
            history=history,
            final_mode=chosen,
            last_phase_change_s=changes[chosen],
            gradient=finite_gradient(
                lambda xy, p=problems[chosen]: float(p.residual(xy) @ p.residual(xy)),
                anchor,
            ),
        )
        arm_results[arm] = d
    write(
        OUT / f"restart_{index:02d}.json",
        dict(
            start_id=index,
            start=STARTS[index],
            arms=arm_results,
            GPS_used=False,
            finite_branch_reselection_after_each_accepted_c0_step=True,
            c0_selected_schedule_for_fitted_c=True,
            same_curved_observations=True,
        ),
    )
    print("restart", index, flush=True)


def grid_chunk(index):
    scan, node, keep, _ = context()
    points = read(OUT / "surface_request.json")["points"]
    selected = list(enumerate(points))[index::8]
    rows = []
    for k, point in selected:
        arms = {}
        for arm in ARMS:
            _, d = fixed(scan, node, keep, arm, point)
            arms[arm] = {name: d[name] for name in ("score", "RMS_hz", "last_phase_change_s")}
        rows.append(dict(index=k, point=point, arms=arms))
    write(
        OUT / f"grid_{index:02d}.json",
        dict(
            rows=rows,
            conditional_labels_aliases_and_observations=True,
            phase_refreshed_at_each_pixel=True,
            full_pipeline_rerun_at_each_pixel=False,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("audit", "family", "track", "prior", "discover", "bank", "restart", "grid"),
    )
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--point", type=float, nargs=2)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    if args.stage == "audit":
        audit(np.asarray(args.point))
    elif args.stage in ("family", "track", "prior"):
        intervention(args.stage, args.index)
    else:
        {"discover": discover, "bank": lambda _: bank(), "restart": restart, "grid": grid_chunk}[
            args.stage
        ](args.index)
    print(args.stage, "seconds", time.monotonic() - began, flush=True)
