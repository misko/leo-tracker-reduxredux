"""Matched local gamma and continuous-mark ablations from frozen B7 products."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write

from leo.analysis.hard60_dynamic_rf import fit
from leo.analysis.hard60_score import Hard60Objective, likelihood, predict_orbits
from leo.analysis.lnb_band_objective import LnbBandObjective
from leo.analysis.regional_position_score import coordinates
from leo.analysis.shared_track_likelihood import shared_track_terms
from leo.analysis.shared_track_objective import SharedTrackObjective
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_12_band_calibrated_merge"
LOCAL = REPORT / "local"
PREVIOUS = Path(
    "/srv/bulk/leo-dev/leo-track-merge-consistency/reports/2026_10_12_consistent_track_merge"
)
ARMS = ("fitted-c", "zero-c")
GROUP_MODES = {
    "independent": ("joined", 0.0),
    "parents": ("parents", 0.5),
    "joined": ("joined", 0.5),
    "shared": ("joined", 1.0),
}
VARIANTS = {
    f"{calibration}-{name}": {
        "enabled": calibration == "cal",
        "groups": groups,
        "p": p,
        "profile_seed": calibration == "cal",
    }
    for calibration in ("zero", "cal")
    for name, (groups, p) in GROUP_MODES.items()
}
VARIANTS["cal-zero-seed"] = {"enabled": True, "groups": "joined", "p": 0.0, "profile_seed": False}


def load_inputs(parent_case):
    old = json.loads((parent_case / "positions/experiment.json").read_bytes())["original_case"]
    prepared = load_prepared(Path(old) / "baseline.json")
    terminal = json.loads((parent_case / "positions/baseline/terminal.json").read_bytes())
    if terminal["status"] != "complete":
        raise ValueError("stationary numerical baseline required")
    final = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")
    if final["accepted_stage"] != "B7" or not final["fit"]["converged"]:
        raise ValueError("this local study requires a stationary B7 seed")
    with np.load(parent_case / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    return prepared, bank, final


def restore(prepared, bank, final, groups, settings):
    state = final["fit"]["joint_state"]
    nodes, knots = np.array(state["clock_nodes_s"]), np.array(state["clock_knots_hz"])
    obs = prepared.observations
    interpolation = np.column_stack(
        [np.interp(obs.times_s, nodes, row) for row in np.eye(len(nodes))]
    )
    old_clock = np.sum(interpolation * knots[obs.receiver], axis=1)
    lookup = {int(n): i for i, n in enumerate(bank.numbers)}
    base = Hard60Objective(
        obs,
        bank.select([lookup[n] for n in final["satellites"]]),
        RegionalPrior(),
        HARD60_SCORE,
        receiver_baseline_hz=np.array(state["receiver_baseline_hz"]) + old_clock,
    )
    model = LnbBandObjective(
        base,
        nodes,
        knots,
        np.array(state["satellite_centers_s"]),
        groups,
        shared_prior=settings["p"],
        enabled=settings["enabled"],
    )
    return model, np.array(state["vector"]), np.array(state["clock_coefficients"])


def profile_seed(model, vector, parent_clock):
    clock = model.expand_parent_clock(parent_clock)
    _, _, _, original = model.evaluate_joint(vector, clock)
    seen = predict_orbits(
        model.bank,
        model.observations,
        model.prior,
        vector[:2],
        vector[7] + model.basis @ vector[8:],
        derivatives=False,
    )[1]
    offsets = np.zeros(2)
    for receiver in model.active_band_receivers:
        mask = (model.observations.receiver == receiver) & (model.observations.channel >= 5)
        residual, visible = original.residual_hz[mask], seen[mask]

        def score(g, residual=residual, visible=visible, position_score=model.score):
            return (
                likelihood(np.zeros(len(residual)), -residual + g, visible, position_score).nll
                + 0.5 * (g / 25000) ** 2
            )

        def search(grid, scorer=score):
            return min((scorer(float(g)), abs(float(g)), float(g)) for g in grid)

        best = search(np.arange(-50000.0, 50000.001, 500.0))
        best = search(
            np.arange(max(-50000.0, best[2] - 500), min(50000.0, best[2] + 500) + 0.001, 50.0)
        )
        best = search(
            np.arange(max(-50000.0, best[2] - 50), min(50000.0, best[2] + 50) + 0.001, 5.0)
        )
        offsets[receiver] = best[2]
    return offsets


def freeze(dataset, sid):
    parent = PREVIOUS / "local" / dataset / sid
    case = LOCAL / dataset / sid
    if (case / "protocol.json").exists():
        raise ValueError("band-calibrated protocol already exists")
    previous = json.loads((parent / "shared-refinement/protocol.json").read_bytes())
    # Parent bindings must still describe the executed source/input artifacts.
    for path, digest in previous["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("parent shared-refinement authority changed")
    prepared, bank, final = load_inputs(parent)
    groups = previous["groups"]
    control, vector, clock = restore(
        prepared, bank, final, groups["joined"], VARIANTS["zero-independent"]
    )
    value, _, _, terms = control.evaluate_joint(vector, clock)
    state = final["fit"]["joint_state"]
    if (
        abs(value - state["total_objective"]) > 1e-6
        or abs(terms.nll - state["likelihood_nll"]) > 1e-6
    ):
        raise ValueError("reference-free original B7 state did not reproduce")
    calibrated, _, _ = restore(prepared, bank, final, groups["joined"], VARIANTS["cal-independent"])
    offsets = profile_seed(calibrated, vector, clock)
    files = sorted((ROOT / "src/leo/analysis").glob("*.py"))
    files += sorted((ROOT / "src/leo/application").glob("*.py"))
    files += sorted((ROOT / "src/leo/contracts").glob("*.py"))
    files += [
        Path(__file__),
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
    ]
    bindings = {str(p): sha(p) for p in files}
    bindings.update(previous["bindings"])
    bindings[str(parent / "shared-refinement/protocol.json")] = sha(
        parent / "shared-refinement/protocol.json"
    )
    bindings[str(parent / "positions/experiment.json")] = sha(parent / "positions/experiment.json")
    protocol = {
        "dataset": dataset,
        "session_id": sid,
        "role": previous["role"],
        "parent_case": str(parent),
        "bindings": bindings,
        "groups": groups,
        "variants": VARIANTS,
        "arms": ARMS,
        "gamma_seed_hz": offsets,
        "active_band_receivers": calibrated.active_band_receivers,
        "band_prior_sigma_hz": 25000.0,
        "band_numerical_scale": 25.0,
        "maximum_seconds": 90,
        "maximum_iterations": 600,
        "reference_usage": "none in freeze or execute",
        "scope": (
            "Conditional local B7 refinements; same raw windows, RF frequencies, bank, geographic "
            "prior, original clock/timing/slope priors, seed and 25 km box for every condition. "
            "Gamma is an additional receiver-specific high-band prediction intercept with a zero "
            "mean 25 kHz prior. Enabled variants use identical data-only profiled gamma seeds; "
            "an enabled-zero-seed control tests optimization sensitivity. All c arms share the "
            "same upstream fitted-c conditioning and final bank; c=0 locks RF stretch and RF "
            "drift while keeping band gamma independent. The RF grouping and alias labels are "
            "assumed from the recorded evidence, not claimed as a physical hardware diagnosis."
        ),
    }
    write(case / "protocol.json", protocol)
    print(
        json.dumps(
            {
                "dataset": dataset,
                "active_receivers": calibrated.active_band_receivers,
                "gamma_seed_hz": offsets.tolist(),
            }
        )
    )


def execute(case, variant, arm):
    protocol = json.loads((case / "protocol.json").read_bytes())
    for path, digest in protocol["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("bound band-calibrated authority changed: " + path)
    path = case / (variant + "-" + arm + ".json")
    if path.exists():
        print("already recorded")
        return
    prepared, bank, final = load_inputs(Path(protocol["parent_case"]))
    settings = protocol["variants"][variant]
    model, vector, old_clock = restore(
        prepared, bank, final, protocol["groups"][settings["groups"]], settings
    )
    offsets = protocol["gamma_seed_hz"] if settings["profile_seed"] else (0.0, 0.0)
    clock = model.expand_parent_clock(old_clock, offsets)
    result = fit(
        model,
        vector.copy(),
        arm=arm,
        clock_seed=clock,
        maximum_seconds=protocol["maximum_seconds"],
        maximum_iterations=protocol["maximum_iterations"],
    )
    fitted_vector, fitted_clock = np.array(result["vector"]), np.array(result["clock_coefficients"])
    if arm == "zero-c" and (
        abs(fitted_vector[6]) > 1e-8 or np.max(np.abs(fitted_clock[-2:])) > 1e-8
    ):
        raise ValueError("c=0 arm did not preserve its RF locks")
    value, _, _, terms = model.evaluate_joint(fitted_vector, fitted_clock)
    # Original mark likelihood at the same calibrated state; remove correlation only.
    _, _, _, singleton = super(SharedTrackObjective, model).evaluate_joint(
        fitted_vector, fitted_clock
    )
    _, evidence = shared_track_terms(singleton, model.groups, shared_prior=settings["p"])
    mass = float(singleton.responsibilities.sum())
    write(
        path,
        {
            "variant": variant,
            "arm": arm,
            "protocol_sha256": sha(case / "protocol.json"),
            "fit": plain(result),
            "objective": float(value),
            "mark_model_nll": terms.nll,
            "singleton_nll": singleton.nll,
            "singleton_signal_mass": mass,
            "singleton_rms_hz": float(
                np.sqrt(np.sum(singleton.responsibilities * singleton.residual_hz**2) / mass)
            ),
            "band_offsets_hz": model.band_offsets_hz(fitted_clock),
            "group_evidence": [
                {
                    "rows": e.rows,
                    "log_bayes_factor": e.log_bayes_factor,
                    "posterior_shared": e.posterior_shared,
                }
                for e in evidence
            ],
            "reference_usage": "none",
        },
    )
    print(
        json.dumps(
            {
                "variant": variant,
                "arm": arm,
                "stationary": result["converged"],
                "singleton_nll": singleton.nll,
                "signal_mass": mass,
                "band_offsets_hz": model.band_offsets_hz(fitted_clock).tolist(),
            }
        ),
        flush=True,
    )


def evaluate(case):
    protocol = json.loads((case / "protocol.json").read_bytes())
    files = [case / (v + "-" + a + ".json") for v in protocol["variants"] for a in ARMS]
    results = [json.loads(p.read_bytes()) for p in files]
    seal = {str(p): sha(p) for p in files}
    seal_path = case / "evaluation-seal.json"
    if seal_path.exists() and json.loads(seal_path.read_bytes()) != seal:
        raise ValueError("band-calibrated evaluation seal changed")
    write(seal_path, seal)
    authority = Path(protocol["parent_case"]) / "shared-refinement/evaluation.json"
    # The shared study stores a hash of its reference-bearing comparison.
    parent_position = Path(protocol["parent_case"]) / "positions"
    reference_file = next(parent_position.glob("evaluation-baseline-*.json"))
    reference = json.loads(reference_file.read_bytes())["reference"]
    rows = []
    for r in results:
        latitude, longitude = coordinates(RegionalPrior(), r["fit"]["vector"][:2])
        lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *reference))
        h = (
            math.sin((lat - ref_lat) / 2) ** 2
            + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
        )
        rows.append(
            {
                "variant": r["variant"],
                "arm": r["arm"],
                "stationary": r["fit"]["converged"],
                "reference_error_m": 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h)))),
                **{
                    k: r[k]
                    for k in (
                        "objective",
                        "singleton_nll",
                        "singleton_signal_mass",
                        "singleton_rms_hz",
                        "band_offsets_hz",
                    )
                },
            }
        )
    write(
        case / "evaluation.json",
        {
            "rows": rows,
            "seal_sha256": sha(seal_path),
            "reference_authority_sha256": sha(reference_file),
            "shared_evaluation_sha256": sha(authority),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute", "evaluate"))
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--variant", choices=VARIANTS, default="cal-independent")
    parser.add_argument("--arm", choices=ARMS, default="fitted-c")
    args = parser.parse_args()
    case = LOCAL / args.dataset / args.session_id
    if args.command == "freeze":
        freeze(args.dataset, args.session_id)
    elif args.command == "execute":
        execute(case, args.variant, args.arm)
    else:
        evaluate(case)
