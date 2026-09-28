"""All-frame frequency/null ablation on already archived pilot matrices."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "reports/2026_09_28_pilot_split_transfer"
sys.path.insert(0, str(ROOT / "tools"))
from ds789_frequency_mixture import fit, predict  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(dataset):
    target = HERE / dataset
    target.mkdir(exist_ok=True)
    result = json.loads((SOURCE / dataset / "result.json").read_text())
    assert digest(SOURCE / dataset / "matrices.npz") == result["matrices_sha256"]
    assert digest(SOURCE / dataset / "spec.json") == result["spec_sha256"]
    archive = np.load(SOURCE / dataset / "matrices.npz", allow_pickle=False)
    times = archive["times_s"]
    tt, th = times[::2], times[1::2]
    grid = np.arange(-2000.0, 2000.1, 10.0)
    posterior = {"frequencies_hz": grid}
    rows = []
    for window in result["windows"]:
        for frame in window["frames"]:
            key = frame["matrix_key"]
            values = archive[key]
            training, held = values[::2], values[1::2]
            rng = np.random.default_rng(frame["seed"])
            scrambled = held * (1j ** rng.integers(0, 4, len(held)))[:, None]
            mixture = fit(training, tt, grid)
            zero = fit(training, tt, [0.0])
            (ordinary,) = [m for m in frame["methods"] if m["method"] == "ordinary"]
            point = fit(training, tt, [ordinary["fit"]["frequency_hz"]])
            posterior[key + "_weights"] = mixture["weights"]
            posterior[key + "_log_weights"] = mixture["log_weights"]
            posterior[key + "_variance"] = mixture["variance"]
            posterior[key + "_mean"] = mixture["mean"]
            arms = {}
            for name, model, null in (
                ("fixed_zero", zero, False),
                ("ordinary_point", point, False),
                ("frequency_mixture", mixture, False),
                ("fixed_zero_null", zero, True),
                ("frequency_mixture_null", mixture, True),
            ):
                arms[name] = {
                    "real": predict(model, held, th, include_null=null),
                    "scrambled": predict(model, scrambled, th, include_null=null),
                }
            injections = []
            probability = float(np.exp(mixture["log_signal_probability"]))
            mean = float(np.sum(grid * mixture["weights"]))
            for shift in (-250.0, 250.0):
                shifted = values * np.exp(2j * np.pi * shift * times[:, None])
                moved = fit(shifted[::2], tt, grid + shift)
                weight_error = float(np.max(np.abs(moved["weights"] - mixture["weights"])))
                evidence_error = abs(
                    float(moved["log_evidence_ratio"] - mixture["log_evidence_ratio"])
                )
                density_error = abs(
                    predict(moved, shifted[1::2], th, include_null=True)["log_density"]
                    - arms["frequency_mixture_null"]["real"]["log_density"]
                )
                assert max(weight_error, evidence_error, density_error) <= 1e-8
                fixed = fit(shifted[::2], tt, grid)
                p = float(np.exp(fixed["log_signal_probability"]))
                retained = float(
                    mixture["weights"][(grid + shift >= -2000) & (grid + shift <= 2000)].sum()
                )
                injections.append(
                    {
                        "shift_hz": shift,
                        "translated_weight_error": weight_error,
                        "translated_evidence_error": evidence_error,
                        "translated_density_error": density_error,
                        "fixed_domain_signal_probability": p,
                        "original_mass_retained": retained,
                        "fixed_domain_mean_error_hz": float(
                            np.sum(grid * fixed["weights"]) - mean - shift
                        ),
                        "reliable_pair": probability > 0.99 and p > 0.99 and retained >= 0.99,
                    }
                )
            rows.append(
                {
                    "matrix_key": key,
                    "window_index": window["window_index"],
                    "visit_index": window["visit_index"],
                    "receiver_id": window["receiver_id"],
                    "signal_probability": probability,
                    "fixed_zero_signal_probability": float(np.exp(zero["log_signal_probability"])),
                    "conditional_frequency_mean_hz": mean,
                    "conditional_frequency_sd_hz": float(
                        np.sqrt(np.sum(mixture["weights"] * (grid - mean) ** 2))
                    ),
                    "log_evidence_ratio": float(mixture["log_evidence_ratio"]),
                    "arms": arms,
                    "injections": injections,
                }
            )
    with (target / "posterior.npz").open("xb") as stream:
        np.savez_compressed(stream, **posterior)
    with (target / "result.json").open("x") as stream:
        json.dump(
            {
                "dataset": dataset,
                "source_result_sha256": digest(SOURCE / dataset / "result.json"),
                "posterior_sha256": digest(target / "posterior.npz"),
                "rows": rows,
            },
            stream,
            indent=2,
            allow_nan=False,
        )
    print(dataset, len(rows), "frames complete", flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
