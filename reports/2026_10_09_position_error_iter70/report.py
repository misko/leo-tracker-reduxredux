"""Full16-control execution comparison, no position-reference evaluation."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


plan = read(HERE / "protocol.json")
rows = []
for index in plan["endpoint_indices"]:
    for arm in ("fitted-c", "zero-c"):
        old = read(
            REPORTS / "2026_10_09_position_error_iter55/results" / f"{index:03d}-{arm}.json"
        )["fit"]
        crowded = read(
            REPORTS / "2026_10_09_position_error_iter69/results" / f"{index:03d}-00-{arm}.json"
        )["fit"]
        new = read(HERE / "results" / f"{index:03d}-{arm}.json")["fit"]
        rows.append(
            dict(
                index=index,
                arm=arm,
                old=old,
                crowded=crowded,
                new=new,
                objective_delta=new["objective"] - old["objective"],
                max_vector_delta=float(
                    np.max(abs(np.asarray(new["vector"]) - np.asarray(old["vector"])))
                ),
                max_clock_delta=float(
                    np.max(
                        abs(
                            np.asarray(new["clock_coefficients"])
                            - np.asarray(old["clock_coefficients"])
                        )
                    )
                ),
            )
        )
assert len(rows) == 16
summary = dict(
    rows=rows,
    counts={name: sum(r[name]["converged"] for r in rows) for name in ("old", "crowded", "new")},
    lost_convergence=sum(r["old"]["converged"] and not r["new"]["converged"] for r in rows),
    wall_cap_reached=sum(r["new"]["elapsed_s"] >= 90 for r in rows),
    max_abs_objective_delta=max(abs(r["objective_delta"]) for r in rows),
    max_vector_delta=max(r["max_vector_delta"] for r in rows),
    max_clock_delta=max(r["max_clock_delta"] for r in rows),
)
summary["qualified"] = summary["lost_convergence"] == 0 and summary["wall_cap_reached"] == 0
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
for name, color in (("old", "#227c9d"), ("crowded", "#cc6677"), ("new", "#228833")):
    for ax, key in zip(axes, ("evaluations", "elapsed_s"), strict=True):
        ax.plot(range(16), [r[name][key] for r in rows], "o-", label=name, color=color, alpha=0.7)
axes[0].set(ylabel="Recorded feasible evaluations", xlabel="Fixed control ordinal")
axes[1].set(ylabel="Fit wall seconds", xlabel="Fixed control ordinal")
axes[0].legend()
fig.suptitle("Same16 controls: original / eight-worker / two-worker qualification")
fig.savefig(HERE / "execution.png", dpi=160)
text = f"""# Iteration70: lower-concurrency execution qualification

**{"Qualified" if summary["qualified"] else "Not qualified"} on all16 fixed controls.**
Original/eight-worker/new convergence counts are
**{summary["counts"]["old"]} / {summary["counts"]["crowded"]} / {summary["counts"]["new"]}**.
There are{summary["lost_convergence"]} losses relative to original controls and
{summary["wall_cap_reached"]} new fits reaching the90-second wall allowance.

![Execution and evaluation counts](execution.png)

## Frozen test

Commit `69e5d4b99` froze the first eight iteration69 source indices, both c arms,
before execution. These are all16 controls from the first completed-source
comparison, not just its four regressions. There is no reference-position selection
or position-error computation. Two single-thread workers replace eight; the wall
allowance increases from20 to90seconds. The model,600-iteration limit, constraints,
starts, c locks and independent convergence gate remain unchanged. The original
direct sweep continued as a separate live job. This changes two execution settings,
so it does not isolate concurrency alone or claim equal computational budgets.

The observed max absolute objective difference from original is
**{summary["max_abs_objective_delta"]:.9g}**; max parameter-vector difference is
{summary["max_vector_delta"]:.9g} in mixed native units, and max smooth-clock
coefficient difference is{summary["max_clock_delta"]:.9g}Hz. These are descriptive
reproducibility checks, not a relaxed accuracy/convergence threshold.

| Source | Arm | Evaluations: old / crowded / new | Converged: old / crowded / new | New s |
|---:|---|---:|---|---:|
"""
for row in rows:
    text += (
        f"| {row['index']} | {row['arm']} | "
        + " / ".join(str(row[n]["evaluations"]) for n in ("old", "crowded", "new"))
        + " | "
        + " / ".join(str(row[n]["converged"]) for n in ("old", "crowded", "new"))
        + f" | {row['new']['elapsed_s']:.3f} |\n"
    )
text += """
The preserved iteration69 stopped receipts remain first-attempt evidence, not
overwritten controls. Its partial position results do not decide whether the
clock-proposal method works. If this execution qualification passes, use a new
frozen protocol for the full ordinary-region continuation experiment with this
lower-concurrency/larger-allowance policy; rerun controls and proposals together.
No timing or convergence limits in an already executed protocol are changed.

The overlapping tails of55/60 must retain their first results with the execution
overlap disclosed. No completed cohort errors are replaced. All148 DS16/DS17/DS18
members and exposure labels remain unchanged, and the fitted-c mean is1.360148km.
This is execution qualification on consumed controls, not localization validation.
The below1km goal remains active; production and RF collection are unchanged.

[Protocol](protocol.json), [raw receipts](results/), and [comparison data](summary.json)
retain all16 controls and their original/crowded counterparts. Source hashes are
checked by the evaluator. No independent convergence gate was relaxed.
"""
(HERE / "README.md").write_text(text)
print({k: v for k, v in summary.items() if k != "rows"})
