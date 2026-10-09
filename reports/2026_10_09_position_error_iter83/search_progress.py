"""Inference-only search progress; no position references or stopping rule."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


def trajectory(rows, arm):
    elapsed, best, points = 0.0, None, []
    for row in sorted(rows, key=lambda r: (r["index"], r["order"], ARMS.index(r["arm"]))):
        elapsed += row["fit"]["elapsed_s"]
        if row["arm"] != arm:
            continue
        if row["fit"]["converged"]:
            value = row["fit"]["objective"]
            best = value if best is None else min(best, value)
        points.append(dict(fit_seconds=elapsed, best_qualified_objective=best))
    return points


def main():
    snapshot = {}
    for directory in sorted((HERE / "attempts").glob("*")):
        rows, writing = [], []
        for path in sorted(directory.glob("*.json")):
            try:
                rows.append(json.loads(path.read_text()))
            except json.JSONDecodeError:
                writing.append(path.name)
        snapshot[directory.name] = dict(
            attempts=len(rows), incomplete_receipts=writing,
            qualified=sum(r["fit"]["converged"] for r in rows),
            solver_success_but_unqualified=sum(
                r["fit"]["solver_success"] and not r["fit"]["converged"] for r in rows),
            total_fit_seconds=sum(r["fit"]["elapsed_s"] for r in rows),
            arms={a: trajectory(rows, a) for a in ARMS},
        )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for label, result in snapshot.items():
            points = [p for p in result["arms"][arm] if p["best_qualified_objective"] is not None]
            if points:
                initial = points[0]["best_qualified_objective"]
                ax.step([p["fit_seconds"]/60 for p in points],
                        [p["best_qualified_objective"] - initial for p in points],
                        where="post", label=label)
        ax.set(title=arm, xlabel="Cumulative fit seconds /60 (both arms)",
               ylabel="Best qualified objective change (lower is better)")
        if ax.lines:
            ax.legend()
    fig.suptitle("Partial inference-only search progress; no early stopping or accuracy claim")
    fig.savefig(HERE / "search-progress.png", dpi=170)
    plt.close(fig)
    (HERE / "search-progress.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    lines = ["# Partial search progress", "",
             "This audit reads model scores, qualification and fit durations only. It does not "
             "read reference coordinates/errors or change any search decision. Curves are "
             "relative to each recording/arm's first qualified objective, not scores comparable "
             "across recordings. Time is summed reported fit time; loading and regional stages "
             "are excluded. These partial curves cannot establish localization accuracy or "
             "justify stopping the frozen search early.", "",
             "![Inference-only progress](search-progress.png)", "",
             "| Recording | Attempts | Qualified | Solver success but unqualified | Fit minutes |",
             "|---|---:|---:|---:|---:|"]
    for label, r in snapshot.items():
        lines.append(f"| {label} | {r['attempts']} | {r['qualified']} | "
                     f"{r['solver_success_but_unqualified']} | {r['total_fit_seconds']/60:.2f} |")
    lines += ["", "Receipts observed mid-write, if any, remain explicitly listed in JSON. "
              "No benchmark means are replaced. This is a regenerable progress view."]
    (HERE / "SEARCH_PROGRESS.md").write_text("\n".join(lines) + "\n")
    print({label: r["attempts"] for label, r in snapshot.items()})


if __name__ == "__main__":
    main()
