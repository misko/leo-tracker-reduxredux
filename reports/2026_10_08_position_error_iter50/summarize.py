"""Record assembly qualification before broader policy evaluation."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
rows = [
    json.loads((HERE / "results" / f"{label}.json").read_text())
    for label in ("DS18-009", "DS16-046", "S41", "DS17-008")
]
assert all(r["status"] == "complete" for r in rows)
fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
for arm, offset in (("fitted-c", -0.15), ("zero-c", 0.15)):
    ax.bar(
        [i + offset for i in range(len(rows))],
        [r["extension"]["operational"][arm]["error_km"] for r in rows],
        width=0.3,
        label=arm,
    )
ax.set_xticks(range(len(rows)), [r["label"] for r in rows])
ax.set(
    ylabel="Position error km",
    title="Assembly checks reproduce existing results; not new cohort validation",
)
ax.legend()
fig.savefig(HERE / "qualification.png", dpi=160)
text = """# Iteration 50: additive three-region-set assembly qualifies

**The new assembly preserves existing choices and reproduces all four numerical
controls.** It accepts baseline, sep25 and sep50 documents explicitly, chooses
each arm's eligible regional winner by score, then uses the winning fitted-region
calibration/bank/seed for the unchanged matched downstream c ablation.

![Qualification cases](qualification.png)

The stage-runner source after initial regional selection is byte-for-byte
identical to iteration20 (ignoring trailing whitespace). The iteration28
extension is unchanged. No synthetic public persisted document or production
contract is introduced; each regional source remains explicit.

Commits `17545441b` and `71873a56d` froze the two numerical qualifications before
execution. DS18-009 uses a duplicate sep25 document in the third slot to verify
unchanged behavior; DS16-046 uses the actual sep50 result from iteration48.
Both reproduce every stage's vectors, clocks, objectives and position errors
within 1e-5 absolute tolerance, with identical convergence flags. Historical S41
and DS17-008 reproduce the iteration27 final vectors, clocks, objective and error
within the same tolerance, including convergence/fallback behavior.

| Case | Fitted source | Zero-c source | Fitted km | Zero-c km | Converged fitted/zero |
|---|---|---|---:|---:|---|
"""
for row in rows:
    op = row["extension"]["operational"]
    raw = row["extension"]["stages"]["slope-0.25"]
    text += (
        f"| {row['label']} | {row['upstream']['regional_sources']['fitted-c']} | "
        f"{row['upstream']['regional_sources']['zero-c']} | {op['fitted-c']['error_km']:.6f} | "
        f"{op['zero-c']['error_km']:.6f} | "
        f"{raw['fitted-c']['converged']}/{raw['zero-c']['converged']} |\n"
    )
text += """
Two selection tests also pass. The real DS17-008 sep25 rescue survives a tied
new candidate, and independent per-arm selection rejects nonconverged low-score
candidates while ignoring reference error. Earlier candidates win score ties.
These are implementation checks on consumed examples, not fresh validation or
evidence of cohort-wide accuracy improvement.

## Next matched comparison

Evaluate baseline + sep25 + sep50 on all 148 frozen DS16/DS17/DS18 members. Some
older scans had no prior sep25 replay; compute it explicitly and report that the
policy adds both missing sep25 work and sep50 work where applicable. Preserve
the original region sets, exact 400-point grid, existing priors and per-fit
budgets. The total regional fit budget increases and must be reported.

Keep complete membership, old exposure labels, failed inputs, convergence
fallbacks, matched c=0/fitted-c and paired per-dataset regressions. Reusing an
archived region document requires exact input/configuration binding. Do not
replace benchmark entries selectively based on their position errors. Pending
DS16 baseline completion remains separate from scientific selection.

The four receipts in results/ preserve numerical checks and provenance. Ruff and
both selection tests pass; the plot was inspected. No production settings,
public contracts, golden fixtures, QNAP data or RF collection changed. The goal
of a full-corpus mean below 1 km remains unachieved.
"""
(HERE / "README.md").write_text(text)
