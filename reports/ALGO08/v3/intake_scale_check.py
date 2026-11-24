"""Check two-point intake extrapolation against an already timed full recording."""

import argparse
import gzip
import json
from math import isfinite
from pathlib import Path
from statistics import median

from reports.ALGO08.v3.release_intake_rate import STAGES, required_rate
from reports.ALGO08.v3.release_stage_budget import checked


def check_order(first, longer, full, offered_bytes, intake_allowance_s):
    """Use (original compressed bytes, launch-to-detections seconds) pairs."""
    b1, t1 = first
    b4, t4 = longer
    total_bytes, observed_s = full
    low_bytes, high_bytes = offered_bytes
    if not (0 < b1 < b4 < total_bytes and 0 < low_bytes <= high_bytes):
        raise ValueError("Expected nested prefixes and ordered transfer byte bounds")
    if not all(isfinite(t) and t > 0 for t in (t1, t4, observed_s, intake_allowance_s)):
        raise ValueError("Expected finite positive measured times and intake allowance")
    slope = (t4 - t1) / (b4 - b1)
    intercept = t1 - slope * b1
    result = dict(intercept_s=intercept, seconds_per_MB=slope * 1e6, usable=slope > 0)
    if slope <= 0:
        return result
    predicted = intercept + slope * total_bytes
    bounds = [intercept + slope * b for b in offered_bytes]
    result.update(marginal_MB_s=1e-6 / slope, predicted_full_s=predicted,
                  measured_full_s=observed_s, full_error_s=predicted-observed_s,
                  full_error_percent=100*(predicted-observed_s)/observed_s,
                  projected_transfer_s=bounds, transfer_allowance_s=intake_allowance_s,
                  transfer_headroom_s=[intake_allowance_s-t for t in reversed(bounds)])
    return result


def receipt(name, pin):
    directory = Path(__file__).resolve().parent / "measurements"
    content = checked(directory / name, pin)
    return json.loads(gzip.decompress(content) if name.endswith(".gz") else content)


def combined_blind_trials():
    trials = []
    for case, pin in (("0163", "9c28657f1dd8a8f31b2f564522d47b42e9b83347f9f816e75c435022f6398801"),
                      ("0173", "9e68ac940d14ad404662a6460029dfe2b58a02e4e27e9137e5b32031687dd62a"),
                      ("0359", "e6a627e9cb8c5b8200916e5031ce5b581ae971d274bf9d9eeffb215149a3df31")):
        trial = receipt(f"ds30-{case}-combined.json.gz", pin)
        if (trial["case"] != f"DS30-{case}" or trial["study"]["independent_cases"] != [trial["case"]]
                or trial["admission"]["science_commit"] != "ad319307d" or not trial["checks"]["same_input_and_offer"]):
            raise ValueError("Expected the frozen combined solver on its independently enrolled recording")
        trials.append(trial)
    return trials


def combined_intake_budget():
    originals = receipt("release-intake-rate.json",
                        "97889f708715be74e1036e2c9e5f30a38800658bfe9ecff2be4aacbdb2b13aed")
    original_clocks = {r["case"]: r for r in receipt("release-stage-budget.json", STAGES)["rows"]}
    rows = []
    for trial in combined_blind_trials():
        raw, = (r for r in originals["rows"] if r["case"] == trial["case"])
        if raw["elapsed_s"] != trial["prior_installed_raw"]["elapsed_s"]:
            raise ValueError("Expected the original raw-process clock for each blind recording")
        post = trial["paid_setup_and_time"]["elapsed_s"]["candidate_with_setup"]
        allowance = raw["elapsed_s"] / 2 - post
        elapsed, cpu = raw["elapsed_s"], original_clocks[trial["case"]]["cpu_s"]
        off_cpu = elapsed - cpu
        saved_cpu = trial["paid_setup_and_time"]["cpu_s"]["candidate_with_setup"]
        rows.append(dict(case=raw["case"], elapsed_s=raw["elapsed_s"],
                         byte_low=raw["byte_low"], byte_high=raw["byte_high"],
                         post_s=post, allowance_s=allowance,
                         original_off_cpu_s=off_cpu, min_original_pre_detection_off_cpu_s=max(0, raw["pre_s"] - cpu),
                         saved_cpu_with_setup_s=saved_cpu, free_receiver_fixed_wait_s=saved_cpu + off_cpu,
                         required_MB_s=raw["byte_high"] / 1e6 / allowance if allowance > 0 else None))
    sum_ceiling = sum(r["elapsed_s"] for r in rows) / sum(r["free_receiver_fixed_wait_s"] for r in rows)
    median_ceiling = 1 / median(r["free_receiver_fixed_wait_s"] / r["elapsed_s"] for r in rows)
    return dict(rows=rows, joint=required_rate(rows, "byte_high", post_speedup=1, startup_s=0),
                free_receiver_cpu_original_wait=dict(sum_speedup=sum_ceiling, median_speedup=median_ceiling))


def cpu_budget(rows, off_cpu_retained):
    """Price a uniform CPU speedup at a fixed fraction of original off-CPU time."""
    if not rows or not 0 <= off_cpu_retained <= 1:
        raise ValueError("Expected timing rows and a retained fraction from zero to one")
    if not all(0 < r["cpu_s"] <= r["elapsed_s"] and isfinite(r["elapsed_s"]) for r in rows):
        raise ValueError("Expected single-core CPU and wall clocks from each process")
    fractions = {
        "sum": sum(r["cpu_s"] for r in rows) / sum(r["elapsed_s"] for r in rows),
        "median": median(r["cpu_s"] / r["elapsed_s"] for r in rows),
    }
    # Paired ratios are affine in each row's CPU fraction, so the same
    # transformation applies to the median, including an even-sized panel.
    required = {}
    for gate, fraction in fractions.items():
        remaining = .5 - (1 - fraction) * off_cpu_retained
        required[gate] = fraction / remaining if remaining > 0 else None
    return dict(off_cpu_retained=off_cpu_retained, cpu_fractions=fractions,
                required_cpu_speedup=required)


def blind_rows():
    original = receipt("release-intake-rate.json",
                       "97889f708715be74e1036e2c9e5f30a38800658bfe9ecff2be4aacbdb2b13aed")
    rows = []
    for case, pin in (("0419", "acd745a32eedcaad14560e1f32da7b0e761419811780a9ca9dcdfb9eb797e4a1"),
                      ("0289", "78d36df4d6cea5a851ffb344803b965e09f1814c6d068f69c538875359c993fe")):
        trial = receipt(f"nomination-handoff-{case}-local.json.gz", pin)
        raw, = (r for r in original["rows"] if r["case"] == trial["case"])
        if raw["case"] != "DS30-" + case or raw["elapsed_s"] != trial["prior_installed_raw"]["elapsed_s"]:
            raise ValueError("Blind assignment and original raw-process clock must agree")
        worker = trial["time"]["elapsed_s"]["routed"] + trial["admission"]["setup"]["elapsed_s"]
        solve = trial["publication_clocks"]["routed"]["solve"]["elapsed_s"]
        if not 0 < solve <= trial["time"]["elapsed_s"]["routed"]:
            raise ValueError("The numerical solve must be contained in the measured saved worker")
        rows.append(dict(case=raw["case"], byte_low=raw["byte_low"], byte_high=raw["byte_high"],
                         elapsed_s=raw["elapsed_s"], original_post_s=raw["post_s"],
                         post_s=worker, solve_s=solve, allowance_s=raw["elapsed_s"]/2-worker))
    return rows


def solve_intake_tradeoff(rows):
    """Scale only the numerical solve. Keep admission, publication and exit fully charged."""
    scenarios = []
    for speed in (1, 1.25, 1.5, 2, 4, float("inf")):
        modeled = [dict(r, post_s=(r["post_s"] - r["solve_s"]) + r["solve_s"]/speed) for r in rows]
        rates = {bound: required_rate(modeled, bound, post_speedup=1, startup_s=0)
                 for bound in ("byte_low", "byte_high")}
        scenarios.append(dict(solve_speedup=speed if isfinite(speed) else None,
                              numeric_time_eliminated=not isfinite(speed), rates=rates))
    return scenarios


def load():
    prefix = receipt("original-prefix-scaling-0016.json.gz",
                     "eeb29fff0ac4b3608dc0023e1f2684a5e14f1451ada9b782d74de85a9c27bdbe")
    full = receipt("legacy-verify-original.json.gz",
                   "29100eb3d9222b7a62f43df8928d3051005aca8837c9d88d1d474e88d5449b55")["checked"]["DS30-0016"]
    case, = (r for r in blind_rows() if r["case"] == "DS30-0419")
    offered = case["byte_low"], case["byte_high"]
    allowance = case["allowance_s"]
    members = full["original"]["members"]
    options = prefix["scope"]["candidate_options"]
    if (prefix["scope"]["case"] != "DS30-0016" or len(members) != 13
            or full["original"]["authority_mode"] != "verified-once"
            or full["clock"]["command"][-len(options):] != options):
        raise ValueError("The complete recording and prefix must share the input and receiver settings")
    for count in (1, 4):
        signed = prefix["scope"]["scopes"][str(count)]["inventory"]["prefix_members"]
        if len(signed) != count or any((a["member_sha256"], a["raw_sha256"], a["index_sha256"], a["encoded"])
            != (b["compressed_sha256"], b["uncompressed_sha256"], b["index_sha256"], b["compressed_bytes"])
            for a, b in zip(members[:count], signed, strict=True)):
            raise ValueError("Each prefix must be nested in the original recorded order")
    total = sum(m["encoded"] for m in members)
    result = []
    for order, trial in zip(prefix["launches"]["order"], prefix["times"], strict=True):
        one, four = (trial["scopes"][k] for k in ("1", "4"))
        scopes = {}
        for label, key, full_time in (
            ("through_detections", "detection", full["science"]["detector_file_s"]),
            ("authenticated_acquisition", "inner_wall", full["science"]["phases"]["authenticated_raw_acquisition"]["elapsed_s"]),
        ):
            fit = check_order((one["bytes"], one[key]), (four["bytes"], four[key]),
                              (total, full_time), offered, allowance)
            if label == "authenticated_acquisition":
                # Only launch-to-detections is comparable to the full intake budget.
                fit = {k: v for k, v in fit.items() if "transfer" not in k}
            scopes[label] = fit
        result.append(dict(order=order, scopes=scopes))
    return result


def render(output):
    import matplotlib.pyplot as plt

    prefix = receipt("original-prefix-scaling-0016.json.gz",
                     "eeb29fff0ac4b3608dc0023e1f2684a5e14f1451ada9b782d74de85a9c27bdbe")
    full = receipt("original-full-detector-boundary-0016.json.gz",
                   "1824686722e7c3e3d6bb074a65262b5ec8a60ae201348ba7216c44edd1a372a8")
    if not full["complete_bytes_equal"]:
        raise ValueError("Require matching detector publications")
    size = full["bytes"] / 1e6
    fig, ax = plt.subplots(figsize=(7.9, 4.6))
    fig.subplots_adjust(top=.79, left=.10, right=.95, bottom=.16)
    fig.suptitle("Four files underpredicted intake time for the whole recording",
                 x=.025, y=.97, ha="left", weight="bold", fontsize=14)
    fig.text(.025, .87, "DS30-0016  ·  Fresh processes on one core  ·  Original waveform files in memory",
             fontsize=9, color="#435064")
    predictions = []
    for trial, order in zip(prefix["times"], load(), strict=True):
        measured = [trial["scopes"][key] for key in ("1", "4")]
        x = [s["bytes"] / 1e6 for s in measured]
        y = [s["detection"] for s in measured]
        ax.plot(x, y, "o-", color="#00796d", lw=1.4, markersize=5)
        predicted = order["scopes"]["through_detections"]["predicted_full_s"]
        predictions.append(predicted)
        ax.plot([x[-1], size], [y[-1], predicted], "--", lw=1.2, color="#778693")
    labels = [(full["timing"]["detection_s"], "Detection-only worker", "#00796d", 9),
              (full["normal"]["detection_s"], "Integrated worker", "#394f77", -11)]
    for y, label, color, dy in labels:
        ax.scatter(size, y, s=43, color=color)
        ax.annotate(f"{y:.2f} s   {label}", (size, y), xytext=(-10, dy), textcoords="offset points",
                    ha="right", fontsize=9, color=color)
    ax.annotate(f"{min(predictions):.2f}–{max(predictions):.2f} s   Extrapolated",
                (size, min(predictions)), xytext=(-8,-32),
                textcoords="offset points", ha="right", fontsize=9, color="#596675")
    ax.set(xlim=(0, 1040), ylim=(0,5.65), xlabel="Original compressed data (MB)",
           ylabel="Seconds to publish detections")
    ax.set_axisbelow(True)
    ax.grid(color="#e0e6ea", lw=.7)
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0)
    fig.savefig(output, dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure", type=Path)
    args = parser.parse_args()
    if args.figure:
        render(args.figure)
    rows = blind_rows()
    gates = {bound: required_rate(rows, bound, post_speedup=1, startup_s=0)
             for bound in ("byte_low", "byte_high")}
    original = receipt("release-stage-budget.json", STAGES)["rows"]
    print(json.dumps(dict(prefix_orders=load(), blind_rows=rows, blind_intake_gates=gates,
                          combined_blind_intake=combined_intake_budget(),
                          release_cpu_scenarios=[cpu_budget(original, kept) for kept in (0, .5, 1)],
                          numerical_solve_scenarios=solve_intake_tradeoff(rows)),
                     indent=2, allow_nan=False))
