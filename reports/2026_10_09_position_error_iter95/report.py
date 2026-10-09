"""Read persisted continuation only; no objective evaluation or fitting."""
# ruff: noqa: E501

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    result_path = HERE / "result.json"
    result = json.loads(result_path.read_text())
    assert result["status"] == "calibration-unqualified"
    postfit = result["calibration"]["result"]["postfit"]
    diagnostics = result["calibration"]["result"]["diagnostics"]
    inventory = result["prefit_selection"]["inventory"]
    selected = next(
        row for row in inventory if row["path"] == result["prefit_selection"]["selected_path"]
    )
    assert selected["qualified"] and not postfit["converged"]
    original_path = HERE.parent / "2026_10_09_position_error_iter93/published-v3.json"
    document = json.loads(original_path.read_text())["manifest"]["document"]
    baseline = []
    for arm in document["methods"][0]["arms"]:
        fit = arm["selected"]
        baseline.append(
            dict(
                arm=arm["name"],
                error_km=fit["horizontal_error_m"] / 1000,
                objective=fit["objective"],
                posterior_rms_hz=fit["posterior_rms_hz"],
                signal_windows=fit["signal_windows"],
                accepted_stage=fit["accepted_stage"],
                source_basin=fit["source_basin"],
            )
        )
    summary = dict(
        status=result["status"],
        prefit_selection=result["prefit_selection"],
        postfit=postfit,
        solver_success=diagnostics["solver_success"],
        archived_baseline=baseline,
        fresh_baseline_parity="Not measured: stopped before baseline replay",
        candidate_position_results="Neither c arm reached regional finals or B7",
        source_sha256={
            str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (result_path, original_path, Path(__file__))
        },
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    values = [inventory[-2]["stationarity"], selected["stationarity"], postfit["stationarity"]]
    axes[0].bar(
        ["Original prefit", "Polished prefit", "Corrected postfit"],
        values,
        color=["#B37834", "#238668", "#B37834"],
    )
    axes[0].axhline(0.001, color="#333333", linestyle="--", label="Unchanged qualification gate")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Independent stationarity residual")
    axes[0].set_title("A second qualification failure")
    axes[0].legend(fontsize=8)
    axes[1].bar(
        [row["arm"] for row in baseline], [row["error_km"] for row in baseline], color="#53758E"
    )
    axes[1].set_ylabel("Published position error (km)")
    axes[1].set_title("Archived B7; candidate unavailable")
    for index, row in enumerate(baseline):
        axes[1].text(index, row["error_km"] + 1, f"{row['error_km']:.3f}", ha="center")
    axes[1].set_ylim(0, 65)
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle("ac11 continuation: numerical prefit recovery has not fixed localization")
    figure.savefig(HERE / "qualification.png", dpi=160)
    plt.close(figure)
    lines = [
        "# Iteration95: rescued prefit meets a second calibration bottleneck",
        "",
        "The continuation did **not** produce a new position. The ordinary lowest-score failed region's "
        "prefit qualified after iteration96, but its corrected fixed-position postfit failed the unchanged "
        "stationarity check. Association, both c finals, ordinary-only B7 replay, and candidate B7 were not reached.",
        "",
        "![Qualification and archived errors](qualification.png)",
        "",
        "## Recorded result",
        "",
        f"The frozen score-only selection chose iteration96 from all six saved prefits: objective "
        f"{selected['objective']:.12f}, independent stationarity {selected['stationarity']:.9g}. "
        "The two qualified zero-timing alternatives had worse same-model scores. No reference error entered selection.",
        "",
        f"After the unchanged receiver correction, the bounded postfit reported optimizer success, "
        f"but stationarity was **{postfit['stationarity']:.9g}**, versus the0.001 requirement. "
        f"It performed {postfit['evaluations']} evaluations in {postfit['elapsed_s']:.3f}s of its20s/600iteration budget. "
        "This was a convergence qualification failure, not a time limit.",
        "",
        f"Its objective was {postfit['objective']:.9f}, posterior RMS {postfit['posterior_rms_hz']:.3f}Hz, "
        f"and effective signal support {postfit['signal_windows']:.3f}. "
        "The correction changes the likelihood baseline: its raw objective must not be treated as an improvement "
        "over the uncorrected prefit objective. No candidate association or B7 pruning/support result exists.",
        "",
        "## Matched c coverage and baseline",
        "",
        "| Arm | Archived B7 error (km) | New final position | Fresh baseline parity |",
        "|---|---:|---|---|",
    ]
    lines.extend(
        f"| {row['arm']} | {row['error_km']:.6f} | Not reached | Not measured |" for row in baseline
    )
    lines += [
        "",
        "Published B7 remains the original ordinary region `point:-72.5:-137.5`. "
        "The candidate fixed position remained the ordinary score-selected `point:-47.5:-62.5`; "
        "it never became an operational winner. Reference errors above are evaluation-only archived results. "
        "There is no measured position improvement or matched-c frequency-fit comparison from this continuation.",
        "",
        "## Next causal test",
        "",
        "A separate frozen diagnostic can reconstruct this corrected objective and apply the already tested "
        "curvature polish to its saved terminal state, preserving the same full stationarity threshold, "
        "physical constraints and fixed initial-score roundoff allowance. The near-threshold prefit mechanism "
        "does not by itself prove the postfit failure has the same cause. Only a qualified downstream "
        "continuation and ordinary-only baseline replay can establish whether this region improves localization.",
        "",
        "No frozen source, deployment or original checkpoint was changed. This is a consumed single-scan "
        "diagnostic, not independent validation. The report reads persisted receipts only.",
        "",
        "Sources: [frozen protocol](protocol.json), [terminal receipt](result.json), "
        "[full numerical summary](summary.json), [iteration96](../2026_10_09_position_error_iter96/README.md).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
