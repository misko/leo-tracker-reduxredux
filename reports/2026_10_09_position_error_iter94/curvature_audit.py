"""Read-only arithmetic and figure from completed coordinate-polish trials."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    path = HERE / "result.json"
    saved = json.loads(path.read_text())
    fitted = saved["fit"]
    trials = [row for row in fitted["trials"] if row.get("evaluated") and row["round"] == 0]
    coordinate = trials[0]["coordinate"]
    assert coordinate == 20 and all(row["coordinate"] == coordinate for row in trials)
    pairs = {row["scaled_step"]: row for row in trials}
    h = 1e-5
    value, gradient = fitted["objective"], fitted["gradient"][coordinate]
    # Coordinate20 is a timing-basis coordinate with physical scale1 in the
    # existing fitter. It is not an individual satellite/receiver clock error.
    curvature_gradient = (pairs[h]["gradient"][coordinate] - pairs[-h]["gradient"][coordinate]) / (
        2 * h
    )
    curvature_value = (pairs[h]["objective"] + pairs[-h]["objective"] - 2 * value) / h**2
    newton_step = -gradient / curvature_gradient
    expected_decrease = gradient**2 / (2 * curvature_gradient)
    ulp = math.ulp(value)
    result = dict(
        scope="Arithmetic on completed immutable trials; no new objective evaluation or fit",
        source_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        coordinate=coordinate,
        coordinate_name="relative timing basis12 (not an individual clock)",
        objective=value,
        raw_scaled_gradient=gradient,
        h=h,
        gradient_curvature=curvature_gradient,
        scalar_cost_curvature=curvature_value,
        proposed_scalar_newton_step=newton_step,
        predicted_quadratic_decrease=expected_decrease,
        objective_ulp=ulp,
        predicted_decrease_ulps=expected_decrease / ulp,
        proposed_global128ulp_band=128 * ulp,
        smallest_trials=[
            dict(
                step=step,
                cost_delta=pairs[step]["objective"] - value,
                raw_coordinate_gradient=pairs[step]["gradient"][coordinate],
            )
            for step in (-1e-8, 1e-8)
        ],
        limits="Local scalar quadratic estimate; no full-KKT qualification or accuracy benefit",
    )
    (HERE / "curvature.json").write_text(json.dumps(result, indent=2) + "\n")
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for sign, label, color in ((1, "Positive step", "#CC8B35"), (-1, "Negative step", "#147E9C")):
        rows = sorted(
            [row for row in trials if row["scaled_step"] * sign > 0],
            key=lambda row: abs(row["scaled_step"]),
        )
        axes[0].loglog(
            [abs(row["scaled_step"]) for row in rows],
            [row["objective"] - value for row in rows],
            "o-",
            label=label,
            color=color,
        )
    axes[0].axhline(ulp, color="#777777", linestyle=":", label="One objective ULP")
    axes[0].axhline(128 * ulp, color="#777777", linestyle="--", label="Proposed128-ULP band")
    axes[0].set_xlabel("Absolute scaled timing-basis step")
    axes[0].set_ylabel("Measured objective increase")
    axes[0].set_title("All sampled steps lost under strict score decrease")
    small = sorted(
        [row for row in trials if abs(row["scaled_step"]) <= 1e-7],
        key=lambda row: row["scaled_step"],
    )
    axes[1].plot(
        [row["scaled_step"] / 1e-8 for row in small],
        [row["gradient"][coordinate] for row in small],
        "o-",
        color="#147E9C",
    )
    axes[1].scatter([0], [gradient], color="#CC8B35", s=60, label="Original state", zorder=3)
    axes[1].axhspan(-0.001, 0.001, color="#228860", alpha=0.14, label="Coordinate within±0.001")
    axes[1].axvline(
        newton_step / 1e-8, color="#777777", linestyle="--", label="Scalar Newton estimate"
    )
    axes[1].axhline(0, color="#777777", linewidth=0.7)
    axes[1].set_xlabel("Scaled timing-basis step (×10⁻⁸)")
    axes[1].set_ylabel("Raw gradient in coordinate20")
    axes[1].set_title("Coordinate gradient improves below scalar-score resolution")
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(fontsize=8)
    figure.suptitle("Consumed scan ac11: local curvature diagnostic, no new fit", fontsize=13)
    figure.tight_layout()
    figure.savefig(HERE / "curvature.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    main()
