"""Fixed-prior acquisition-aware ablation on archived pilot matrices."""

import hashlib  # noqa: F401 - preserved for AST identity with the sealed execution
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PILOT = HERE.parent / "2026_09_28_pilot_split_transfer"
PREVIOUS = HERE.parent / "2026_09_28_pilot_frequency_mixture"
sys.path.insert(0, str(ROOT / "tools"))
from ds789_acquisition_mixture import posterior, predictive_ratio  # noqa: E402
from ds789_frequency_mixture import fit, predict  # noqa: E402

PRIORS = {"acquisition_broad": [0.5, 0.5], "acquisition_broad_null": [0.25, 0.25, 0.5]}


def states(values, times, grid, center):
    zero = fit(values[::2], times[::2], [center])
    broad = fit(values[::2], times[::2], grid)
    evidence = [zero["log_evidence_ratio"], broad["log_evidence_ratio"], 0.0]
    output = {}
    for name, prior in PRIORS.items():
        weights = posterior(evidence[: len(prior)], prior)
        probability = np.exp(weights)
        signal = probability[:2].sum()
        conditional = probability[:2] / signal
        output[name] = {
            "log_weights": weights,
            "weights": probability,
            "signal_probability": float(signal),
            "conditional_component_weights": conditional,
            "mean_hz": float(
                conditional[0] * center + conditional[1] * np.sum(grid * broad["weights"])
            ),
        }
    return zero, broad, output


def prediction(zero, broad, state, values, times):
    ratios = [
        predict(m, values, times, include_null=False)["log_ratio_to_noise"] for m in (zero, broad)
    ] + [0.0]
    return predictive_ratio(state["log_weights"], ratios[: len(state["log_weights"])])


def main(dataset):
    target = HERE / dataset
    target.mkdir(exist_ok=True)
    archive = np.load(PILOT / dataset / "matrices.npz", allow_pickle=False)
    times = archive["times_s"]
    old = json.loads((PREVIOUS / dataset / "result.json").read_text())
    split = json.loads((PILOT / dataset / "result.json").read_text())
    split_rows = {f["matrix_key"]: f for w in split["windows"] for f in w["frames"]}
    grid = np.arange(-2000.0, 2000.1, 10)
    rows = []
    replay_count = 0
    for old_row in old["rows"]:
        key = old_row["matrix_key"]
        values = archive[key]
        zero, broad, original = states(values, times, grid, 0.0)
        frame = split_rows[key]
        (ordinary,) = [m for m in frame["methods"] if m["method"] == "ordinary"]
        point = fit(values[::2], times[::2], [ordinary["fit"]["frequency_hz"]])
        rng = np.random.default_rng(frame["seed"])
        control = values[1::2] * (1j ** rng.integers(0, 4, 75))[:, None]
        for name, model, null in (
            ("fixed_zero", zero, False),
            ("ordinary_point", point, False),
            ("frequency_mixture", broad, False),
            ("fixed_zero_null", zero, True),
            ("frequency_mixture_null", broad, True),
        ):
            for label, held in (("real", values[1::2]), ("scrambled", control)):
                actual = predict(model, held, times[1::2], include_null=null)
                for field in actual:
                    assert abs(actual[field] - old_row["arms"][name][label][field]) <= 1e-8
                replay_count += 1
        arms = {}
        for name, state in original.items():
            arms[name] = {
                "component_weights": state["weights"].tolist(),
                "signal_probability": state["signal_probability"],
                "conditional_mean_hz": state["mean_hz"],
                "real_log_ratio_to_noise": prediction(
                    zero, broad, state, values[1::2], times[1::2]
                ),
                "scrambled_log_ratio_to_noise": prediction(
                    zero, broad, state, control, times[1::2]
                ),
                "injections": [],
            }
        for shift in (-250.0, 250.0):
            moved_values = values * np.exp(2j * np.pi * shift * times[:, None])
            mz, mb, moved = states(moved_values, times, grid + shift, shift)
            _, _, fixed = states(moved_values, times, grid, 0.0)
            for name, state in original.items():
                error = max(
                    float(np.max(np.abs(state["weights"] - moved[name]["weights"]))),
                    abs(moved[name]["mean_hz"] - state["mean_hz"] - shift),
                    abs(
                        prediction(mz, mb, moved[name], moved_values[1::2], times[1::2])
                        - arms[name]["real_log_ratio_to_noise"]
                    ),
                )
                assert error <= 1e-8
                c = state["conditional_component_weights"]
                retained = float(
                    c[0]
                    + c[1]
                    * broad["weights"][(grid + shift >= -2000) & (grid + shift <= 2000)].sum()
                )
                arms[name]["injections"].append(
                    {
                        "shift_hz": shift,
                        "translated_max_error": error,
                        "fixed_signal_probability": fixed[name]["signal_probability"],
                        "original_mass_retained": retained,
                        "fixed_mean_shift_error_hz": fixed[name]["mean_hz"]
                        - state["mean_hz"]
                        - shift,
                        "reliable_pair": state["signal_probability"] > 0.99
                        and fixed[name]["signal_probability"] > 0.99
                        and retained >= 0.99,
                    }
                )
        rows.append(
            {
                "matrix_key": key,
                "window_index": old_row["window_index"],
                "receiver_id": old_row["receiver_id"],
                "visit_index": old_row["visit_index"],
                "training_log_evidence": [
                    float(zero["log_evidence_ratio"]),
                    float(broad["log_evidence_ratio"]),
                    0.0,
                ],
                "old_arms": old_row["arms"],
                "arms": arms,
            }
        )
    with (target / "result.json").open("x") as stream:
        json.dump(
            {"dataset": dataset, "replayed_predictions": replay_count, "rows": rows},
            stream,
            indent=2,
            allow_nan=False,
        )
    print(dataset, len(rows), "frames;", replay_count, "predictions replayed", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
