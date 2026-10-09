import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "protocol.json").read_text())
tolerances = plan["qualification_tolerances"]
rows = []
for index in plan["endpoint_indices"]:
    for arm in ("fitted-c", "zero-c"):
        name = f"{index:03d}-{arm}.json"
        path = HERE / "results" / name
        if not path.exists():
            continue
        a = json.loads(
            (HERE.parent / "2026_10_09_position_error_iter60/results" / name).read_text()
        )["fit"]
        b = json.loads(path.read_text())["fit"]
        delta = abs(np.array(a["vector"]) - np.array(b["vector"]))
        differences = dict(
            position_km_absolute=float(max(delta[:2])),
            other_vector_absolute=float(max(delta[2:])),
            clock_hz_absolute=float(
                max(abs(np.array(a["clock_coefficients"]) - np.array(b["clock_coefficients"])))
            ),
            objective_absolute=abs(a["objective"] - b["objective"]),
            rms_hz_absolute=abs(a["posterior_rms_hz"] - b["posterior_rms_hz"]),
        )
        checks = {key: value <= tolerances[key] for key, value in differences.items()}
        checks["same_convergence"] = a["converged"] == b["converged"]
        checks["zero_c_lock"] = arm != "zero-c" or (a["vector"][6] == b["vector"][6] == 0)
        rows.append(
            dict(
                index=index,
                arm=arm,
                differences=differences,
                checks=checks,
                qualified=all(checks.values()),
                numpy_seconds=a["elapsed_s"],
                native_seconds=b["elapsed_s"],
                numpy_evaluations=a["evaluations"],
                native_evaluations=b["evaluations"],
            )
        )
summary = dict(
    completed=len(rows), expected=6, qualified=sum(r["qualified"] for r in rows), rows=rows
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
x = np.arange(len(rows))
for label, key, offset in [("NumPy", "numpy_seconds", -0.18), ("Native", "native_seconds", 0.18)]:
    ax.bar(x + offset, [r[key] for r in rows], width=0.36, label=label)
ax.set_xticks(x, [f"{r['index']} {r['arm']}" for r in rows], rotation=20)
ax.set(
    ylabel="Fit elapsed seconds", title=f"Native trajectory qualification: {len(rows)}/6 complete"
)
ax.legend()
fig.savefig(HERE / "qualification.png", dpi=160)
text = f"""# Iteration62: native smooth-fit trajectory qualification

**{len(rows)}/6 complete; {summary["qualified"]} satisfy every frozen tolerance.**
This compares implementations, not localization policies. No receiver reference
coordinate or position error is used in this audit. The first three ordinary
regions are selected by inventory order, not their outcomes. Both c arms use
identical starts,90second allowances,600iteration caps, priors and convergence gates.

![Elapsed fitting time](qualification.png)

| Endpoint | Arm | Qualified | Max coordinate delta km | Objective delta | NumPy/native evals |
|---:|---|---|---:|---:|---:|
"""
for r in rows:
    text += (
        f"| {r['index']} | {r['arm']} | {r['qualified']} | "
        f"{r['differences']['position_km_absolute']:.8g} | "
        f"{r['differences']['objective_absolute']:.8g} | "
        f"{r['numpy_evaluations']}/{r['native_evaluations']} |\n"
    )
text += """
Frozen absolute tolerances: position coordinates1e-5km; other vector parameters
1e-3 in their native units; clock coefficients1e-3Hz; objective1e-5; RMS1e-5Hz.
Convergence state must match and c0 must remain locked. summary.json reports every
difference and check, including failures; no tolerance is relaxed after execution.
Floating-point evaluation equivalence alone does not guarantee identical optimizer
trajectories. This audit tests that distinction on six controls, not all recordings.

The native helper is private research code. The ongoing iteration60 pilot still
uses its original NumPy implementation and immutable receipts. No result is
replaced, and no production, contract, fixture or RF changes are made. Future use
still needs frozen budgets and policy, uniform cohort evaluation and independent
validation. This audit is consumed-data numerical qualification only.
"""
if len(rows) == 6 and summary["qualified"] != 6:
    text += (
        "\n## Qualification failed\n\n"
        "Three controls fail the frozen trajectory tolerances despite pointwise "
        "objective/gradient equivalence. Maximum position-coordinate discrepancies "
        "are approximately10m,70m and84m. These are implementation-to-implementation "
        "differences, not errors against receiver truth. The native helper is not "
        "qualified as a drop-in numerical replacement. Keep the NumPy pilot unchanged. "
        "Any native use requires its own frozen outcomes and further investigation "
        "of optimizer sensitivity; do not relax tolerances retroactively.\n"
    )
(HERE / "README.md").write_text(text)
print(summary["completed"], summary["qualified"])
