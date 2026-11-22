"""Translate faces past fixed saved endpoints and audit the observed error bands."""

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path


ARMS = ("c0", "fitted_c")
RULES = (*ARMS, "paired")
FACES = (("west", "east"), ("south", "north"))
MIRROR_DEPTH_KM = 0.100


def local(point, center):
    scale = 111.32 * math.cos(math.radians(center[0]))
    return (point[1] - center[1]) * scale, (point[0] - center[0]) * 111.0


def keep_window(biases, width):
    """Allow both the tested face and the opposite face in a full square."""
    return [-min(biases), width - max(biases)]


def summarize_fit(row):
    original = row["original"]
    width = original["width_km"]
    truth = local(row["reference_latlon"], original["center"])
    normal = max(range(2), key=lambda axis: abs(truth[axis]))
    tangent = 1 - normal
    sign = 1 if truth[normal] > 0 else -1
    face = FACES[normal][sign > 0]
    fitted = row["expanded_fit"]
    if fitted["status"] != "ok":
        raise ValueError("Expected both saved expanded endpoints")
    estimates = {arm: local(fitted["arms"][arm]["latlon"], original["center"]) for arm in ARMS}
    if abs(truth[normal]) == abs(truth[tangent]) or any(
        abs(position[tangent]) > width / 2 for position in (truth, *estimates.values())
    ):
        raise ValueError("Translation must isolate one face and keep the tangential limits satisfied")

    errors = {arm: [a - b for a, b in zip(position, truth, strict=True)]
              for arm, position in estimates.items()}
    bias = {arm: -sign * error[normal] for arm, error in errors.items()}
    windows = {arm: keep_window((bias[arm],), width) for arm in ARMS}
    windows["paired"] = keep_window(tuple(bias.values()), width)
    original_d = width / 2 - abs(truth[normal])
    inside = {arm: window[0] <= original_d <= window[1] for arm, window in windows.items()}
    decision = row["decision"]
    if (decision["inside_original"] != {arm: inside[arm] for arm in ARMS}
            or (decision["publication"] == "published") != inside["paired"]):
        raise ValueError("The analytic sweep must reproduce the original widened decision")
    return dict(
        case=row["case"], face=face, width_km=width, original_truth_clearance_km=original_d,
        tangential_slack_km=width / 2 - max(abs(p[tangent]) for p in (truth, *estimates.values())),
        east_north_error_km=errors, inward_bias_km=dict(bias, paired=min(bias.values())),
        truth_clearance_keep_interval_km=windows,
    )


def error_band(biases, mirror_depth=MIRROR_DEPTH_KM):
    """Conditional near-face guarantees and the threshold interval at ±depth."""
    lower, upper = min(biases), max(biases)
    threshold_lower = upper - mirror_depth
    threshold_upper = lower + mirror_depth
    return dict(
        observed_inward_bias_km=[lower, upper],
        guaranteed_withhold_below_km=-upper,
        guaranteed_keep_from_km=-lower,
        symmetric_depth_must_exceed_km=(upper - lower) / 2,
        mirrored_depth_km=mirror_depth,
        threshold_interval_lower_open_upper_closed_km=[threshold_lower, threshold_upper],
        shared_threshold_exists=threshold_lower < threshold_upper,
    )


def sweep(content):
    rows = [summarize_fit(row) for row in json.loads(content)["cases"]]
    bands = {rule: error_band([row["inward_bias_km"][rule] for row in rows]) for rule in RULES}
    return dict(
        source_sha256=sha256(content).hexdigest(), fits=rows, observed_face_bands=bands,
        common_truth_keep_interval_km={
            rule: [max(row["truth_clearance_keep_interval_km"][rule][0] for row in rows),
                   min(row["truth_clearance_keep_interval_km"][rule][1] for row in rows)]
            for rule in RULES
        },
    )


def plot(receipt, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, sharex=True, sharey=True, figsize=(10.4, 3.7), layout="constrained")
    styles = {"north": ("#096a67", "North · west face"), "india": ("#a74916", "India · north face")}
    ticks = (-1.1, 1.1)
    for ax, rule, title in zip(axes, RULES, ("Fixed zero", "Fitted c", "Both arms"), strict=True):
        ax.axvspan(-MIRROR_DEPTH_KM, MIRROR_DEPTH_KM, color="#ebeef1", zorder=0)
        ax.axhline(0, color="#343b45", lw=0.8)
        ax.axvline(0, color="#838a93", lw=0.8)
        for site, (color, label) in styles.items():
            biases = [row["inward_bias_km"][rule] for row in receipt["fits"]
                      if row["case"].startswith(site + "-")]
            bias = sum(biases) / len(biases)
            ax.plot(ticks, [x + bias for x in ticks], lw=2, color=color, label=label)
            ax.scatter([-bias], [0], s=30, color=color, zorder=3)
        ax.set(xlim=ticks, ylim=(-1.8, 1.8), title=title)
        ax.grid(axis="y", color="#edf0f2", lw=0.7)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Estimated clearance (km)")
    axes[1].set_xlabel("True clearance from the translated face (km)")
    axes[2].legend(loc="lower right", fontsize=8, frameon=False)
    fig.savefig(output, dpi=175)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saved", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--figure", type=Path)
    args = parser.parse_args()
    evidence = sweep(args.saved.read_bytes())
    args.receipt.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    if args.figure is not None:
        plot(evidence, args.figure)
