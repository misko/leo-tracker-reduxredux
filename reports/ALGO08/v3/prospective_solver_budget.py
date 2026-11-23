"""Score a held recording against the previously published solver-time assumptions."""

from hashlib import sha256
import json

from solver_transfer_budget import DATA, interpolate, receipt


MODEL = "solver-transfer-budget.json"
MODEL_SHA = "9ada781c4cd94272c134c9ea9794cfd59ff7bf79efdaba48bf1b3ecfa6cfe52c"


def predictions(model, stock_s):
    measured = model["stock_candidate_solve_cpu_s"]
    if "DS30-0316" in measured:
        raise ValueError("The evaluated recording must be outside the calibration cases")
    dense_stock = measured["DS30-0008"][0]
    dense_candidate = model["dense_reused_cpu_s"]
    anchors = [(0., 0.), measured["DS30-0016"], measured["DS30-0057"], (dense_stock, dense_candidate)]
    return dict(dense_only_s=stock_s * dense_candidate / dense_stock,
                three_sizes_s=interpolate(stock_s, anchors))


def allowance(original_s, compressed_mb, solve_s, render_s, diagnostic_rate):
    if min(original_s, compressed_mb, solve_s, render_s, diagnostic_rate) <= 0:
        raise ValueError("Expected positive recording clocks, rate and size")
    target = original_s / 2
    available = target - solve_s - render_s
    acquire = compressed_mb / diagnostic_rate
    return dict(target_s=target, available_for_acquisition_and_all_other_work_s=available,
                minimum_acquisition_MB_s=compressed_mb / available if available > 0 else None,
                acquisition_at_diagnostic_rate_s=acquire,
                maximum_solve_at_diagnostic_rate_s=target - acquire - render_s,
                elapsed_before_other_work_at_diagnostic_rate_s=acquire + solve_s + render_s)


def assess():
    if sha256((DATA / MODEL).read_bytes()).hexdigest() != MODEL_SHA:
        raise ValueError("The transfer model must precede the new comparison")
    model = receipt(MODEL)
    pair = receipt("prospective-0316-solver.json.gz")
    admission = receipt("prospective-small-physical-admission.json")
    row, = [r for r in receipt("acquisition-throughput.json")["rows"] if r["case"] == pair["case"]]
    candidate = pair["runs"]["cumulative"]["worker"]
    stock = pair["runs"]["stock"]["worker"]
    if (pair["case"] != "DS30-0316" or pair["raw_admission"] != "closed" or pair["waveform_calls"] != 0
            or row["inventory_sha256"] != pair["inputs"]["inventory"] or admission["inventory"] != row["inventory_sha256"]
            or admission["pair_sha256"] != pair["inputs"]["original_pair_sha256"]
            or candidate["detector"] != stock["detector"] or candidate["native_sha256"] != stock["native_sha256"]
            or row["compressed_MB"] != admission["compressed_bytes"] / 1e6):
        raise ValueError("Saved solve and historical admission must identify the same full receiver and recording")
    old = sum(row["stages"])
    actual = candidate["solve"]["cpu_s"]
    checks = {}
    for name, seconds in (("historical_detections_to_terminal", row["stages"][1]),
                          ("fresh_stock_solve_cpu", stock["solve"]["cpu_s"])):
        predicted = predictions(model, seconds)
        checks[name] = dict(stock_s=seconds, predictions=predicted,
                            actual_minus_predicted_s={k: actual - v for k, v in predicted.items()})
    return dict(case=pair["case"], historical_v3_elapsed_s=old, compressed_MB=row["compressed_MB"],
                fresh_solve_cpu_s=actual, fresh_solve_elapsed_s=candidate["solve"]["elapsed_s"],
                fresh_render_elapsed_s=candidate["layout"]["render"]["elapsed_s"], transfer=checks,
                weak_effective_MB_s=model["warm_weak_MB_s"],
                half_time=allowance(old, row["compressed_MB"], candidate["solve"]["elapsed_s"],
                                    candidate["layout"]["render"]["elapsed_s"], model["warm_weak_MB_s"]))


def plot(result, output):
    from matplotlib.figure import Figure

    fig = Figure(figsize=(9.4, 3.5), layout="constrained")
    pred, budget = fig.subplots(1, 2)
    values = result["transfer"]["historical_detections_to_terminal"]["predictions"]
    bars = pred.barh(["Dense fraction", "Three recording sizes", "Measured on DS30-0316"],
                     [values["dense_only_s"], values["three_sizes_s"], result["fresh_solve_cpu_s"]],
                     color=["#acb7c8", "#778ba7", "#167367"])
    pred.bar_label(bars, fmt="%.2f s", padding=3)
    pred.invert_yaxis()
    pred.set(xlim=(0, 10.7), title="Numerical solve", xlabel="CPU seconds")
    half = result["half_time"]
    for i, (label, amount, color) in enumerate([
        ("Acquisition at warm weak rate", half["acquisition_at_diagnostic_rate_s"], "#8193aa"),
        ("Measured solve and render", result["fresh_solve_elapsed_s"] + result["fresh_render_elapsed_s"], "#167367"),
    ]):
        left = 0 if i == 0 else half["acquisition_at_diagnostic_rate_s"]
        budget.barh(["Timing sensitivity"], [amount], left=left, color=color, height=.34, label=label)
        budget.text(left + amount / 2, 0, f"{amount:.2f} s", ha="center", va="center", color="white")
    target = half["target_s"]
    budget.axvline(target, color="#7f3b23", linewidth=2)
    budget.text(target, .30, f"Half of v3\n{target:.2f} s", ha="center", color="#7f3b23")
    budget.legend(loc="lower left", frameon=False, fontsize=8)
    budget.set(xlim=(0, 25), ylim=(-.75, .75), yticks=[], title="Time through publication", xlabel="Elapsed seconds")
    for ax in (pred, budget):
        ax.spines[["left", "top", "right"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e3e6e9")
        ax.set_axisbelow(True)
    fig.savefig(output, dpi=160)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--plot", type=Path)
    args = cli.parse_args()
    result = assess()
    if args.plot:
        plot(result, args.plot)
    print(json.dumps(result, indent=2, allow_nan=False))
