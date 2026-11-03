"""Render the complete saved-state identity audit without scientific model calls."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
METHODS = ("original", "fixed", "expanded", "b1000")


def main():
    summary = json.loads((HERE / "summary.json").read_text())
    rows = summary["rows"]
    windows = sorted({r["window"] for r in rows})
    lookup = {(r["arm"], r["method"], r["window"]): r for r in rows}
    for arm in ("fitted-c", "zero-c"):
        methods = METHODS if arm == "fitted-c" else METHODS[1:]
        fig, axes = plt.subplots(1, 2, figsize=(10, 10), sharey=True)
        for ax, field, title in zip(
            axes,
            ("assigned", "dominant_count"),
            ("All assigned model IDs / original N", "Dominant model ID / original N"),
            strict=True,
        ):
            matrix = np.array(
                [
                    [
                        lookup[arm, method, w][field] / lookup[arm, method, w]["observations"]
                        for method in methods
                    ]
                    for w in windows
                ]
            )
            image = ax.imshow(matrix, vmin=0, vmax=1, cmap="Blues", aspect="auto")
            for i, w in enumerate(windows):
                for j, method in enumerate(methods):
                    row = lookup[arm, method, w]
                    label = f"{row[field]}/{row['observations']}"
                    if field == "dominant_count" and row["dominant_model_id"] is not None:
                        label += f"\nID {row['dominant_model_id']}"
                    ax.text(
                        j,
                        i,
                        label,
                        ha="center",
                        va="center",
                        fontsize=8,
                        color="white" if matrix[i, j] > 0.65 else "black",
                    )
            ax.set(
                xticks=range(len(methods)),
                xticklabels=methods,
                yticks=range(len(windows)),
                yticklabels=[w.replace("DSX01-", "") for w in windows],
                title=title,
            )
            ax.set_xlabel("Complete saved protocol; no window-specific selection")
        axes[0].set_ylabel("Requested window")
        fig.colorbar(
            image,
            ax=axes.ravel().tolist(),
            label="Fraction of all original window points",
            fraction=0.025,
            pad=0.03,
        )
        fig.suptitle(f"DSX01 model-assigned identities, {arm}: dominance is not identity truth")
        fig.subplots_adjust(left=0.07, right=0.87, top=0.92, bottom=0.08, wspace=0.2)
        for suffix in ("png", "pdf"):
            fig.savefig(HERE / f"identity_{arm}.{suffix}", dpi=170)
        plt.close(fig)

    strong = [
        r
        for r in rows
        if r["method"] == "b1000" and r["arm"] == "fitted-c" and r["strong_restoration_descriptive"]
    ]
    lines = [
        "# Recovery identity audit",
        "",
        "The eight b1000 fitted-c windows called strongly restored by the existing net-coverage "
        "criterion are dominated by one **model-assigned** catalogue ID, but they are not all "
        "single-ID segments. Every one has a dominant ID covering at least70% of all original "
        "points; seven cover at least85% of assigned points. Window007 is materially mixed: "
        "ID66544 accounts for40/54 points and ID59841 for13/54. No independent emitter identity "
        "truth is available, and multiple real emitters may occur in a coherent window.",
        "",
        "This is a read-only audit of35 saved NPZs, seven complete protocols, all15 requested "
        "windows and693 fixed original points. Full source files contain20084 observations. "
        "It made zero model/objective calls, zero fits, zero CFO/held scores and no new position "
        "or reference reads. It took0.132 seconds under an external120s TERM/125s KILL cap. "
        "All saved endpoints are retained irrespective of KKT; these counts do not replace "
        "strict scientific selectors. Original c0 is unavailable rather than imputed.",
        "",
        "## The eight descriptive strong-restoration windows",
        "",
        "Strong restoration retains the prior report's criterion: net assigned gain divided by "
        "original missing points is at least80%. It is a coverage label, not a dominance or "
        "verified-identity threshold. The70%/85% dominance descriptions above are summaries "
        "of observed counts, not fitted or selection thresholds.",
        "",
        "| Window | Assigned/N | Dominant model ID | Dominant/N | Dominant/assigned | "
        "IDs with≥3 | Switches/eligible adjacent pairs |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in strong:
        lines.append(
            f"| {r['window']} | {r['assigned']}/{r['observations']} | "
            f"{r['dominant_model_id']} | {r['dominant_count']}/{r['observations']} | "
            f"{r['dominant_count']}/{r['assigned']} | {r['ids_with_at_least_3_assignments']} | "
            f"{r['adjacent_identity_switches']}/{r['adjacent_assigned_comparisons']} |"
        )
    lines += [
        "",
        "## All fifteen fitted-c windows",
        "",
        "Each cell is assigned/N followed by the dominant model-ID count. Complete protocols "
        "are compared without selecting a different method for individual windows.",
        "",
        "| Window | Original | Fixed profile | Expanded profile | b1000 profile |",
        "|---|---|---|---|---|",
    ]
    for w in windows:
        cells = []
        for method in METHODS:
            r = lookup["fitted-c", method, w]
            cells.append(
                f"{r['assigned']}/{r['observations']}; "
                f"{r['dominant_model_id']}:{r['dominant_count']}"
            )
        lines.append("| " + w + " | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Window003 remains0/27 in every fitted-c protocol. The b1000 partial "
        "windows004/006/011/012 have dominant counts only3/44,16/72,12/43,7/66, respectively, "
        "despite assigned counts13/44,34/72,23/43,25/66. Thus point coverage can conceal "
        "substantial fragmentation. Candidate expansion's window014 gain is comparatively "
        "concentrated:26/39 points on ID57864 among32 assigned, versus b1000's8/39 on ID60728 "
        "among12 assigned. This is a difference between complete algorithms, not permission "
        "to splice their per-window outcomes.",
        "",
        "The c0 matched protocols are retained separately in windows.csv, summary.json and "
        "identity_zero-c.png/.pdf. They are not pooled with fitted-c outcomes. For example, "
        "b1000 c0 window005 is33/33 on ID67849, while window002 splits25 assigned points "
        "between ID66154(11) and ID63307(10), plus four singletons. Better total counts alone "
        "therefore do not establish one recovered trajectory.",
        "",
        "## Adjacency, ordering and limits",
        "",
        "Switches compare consecutive chronological **observed** rows that are both assigned, "
        "in the same RX/channel/actual-RF lane, with gap≤1s. Unassigned rows and larger gaps "
        "break adjacency. All exclusions and pair denominators are saved. Zero switches with "
        "few eligible pairs are weak evidence; irregular sampling and multiple emitters "
        "prevent interpreting a switch as an error. The1s limit is a descriptive reporting "
        "convention, not an emitter-persistence prior.",
        "",
        "Original assignments and model IDs match the frozen source-context labels. Every "
        "NPZ has the exact full ordered source time vector and retained row count. b1000 "
        "additionally has exact observation IDs/channels and explicit model RX0/1 to metadata "
        "RX1/2 conversion. Older original/fixed/expanded NPZs lack persisted row IDs; their "
        "producer/common-observation ordering is source-bound, but equal-time row swaps cannot "
        "be independently ruled out from those NPZs alone. This limitation is explicit in "
        "summary.json.alignment. No labels from unassigned rows enter identity counts.",
        "",
        "Version1 stopped at the receiver-convention guard before any aggregate; its source "
        "and plan are preserved. Version2 adds the explicit conversion with two regression "
        "tests; it does not loosen any scientific threshold. Seven component tests pass, "
        "including denominator/loss retention, exact ordering, empty membership and switch "
        "semantics. Source hashes in plan_v2.json are verified before and after the audit.",
        "",
        "A next trajectory model should preserve multiple coherent candidate sequences and "
        "report per-ID support, residual/time consistency and gaps rather than equate assigned "
        "count with verified recovery. These descriptive counts alone do not justify a "
        "same-emitter transition prior, truth labels, dropped observations or a model promotion.",
        "",
        "Artifacts: summary.json contains all105 rows and complete ID histograms; windows.csv "
        "is the flat table; identity_fitted-c.png/.pdf and identity_zero-c.png/.pdf retain "
        "the same original denominators for assignment and dominant-ID coverage.",
    ]
    (HERE / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
