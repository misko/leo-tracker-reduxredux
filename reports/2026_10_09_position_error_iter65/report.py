"""Publish final uniform-policy assessment only when all148 members complete."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
source = HERE.parent / "2026_10_09_position_error_iter51/summary.json"
raw = source.read_bytes()
data = json.loads(raw)
assert len(data["cases"]) == 148
assert all(r["status"] == "complete" for r in data["cases"]), "Wait for full cohort"
assert {k: v["complete"] for k, v in data["metrics"].items()} == dict(DS16=63, DS17=51, DS18=34)
if (HERE / "snapshot.json").exists():
    raise FileExistsError("Preserve final full-cohort snapshot")
(HERE / "snapshot.json").write_bytes(raw)
models = ("baseline", "previous", "candidate")
arms = ("fitted-c", "zero-c")
pooled = {
    a: {m: float(np.mean([r["arms"][a][m]["error_km"] for r in data["cases"]])) for m in models}
    for a in arms
}
changes = {
    a: {
        k: sum(v["arms"][a][k] for v in data["metrics"].values())
        for k in ("improved", "regressed", "tied")
    }
    for a in arms
}
summary = dict(
    source_sha256=hashlib.sha256(raw).hexdigest(),
    pooled_mean_km=pooled,
    paired_changes=changes,
    datasets=data["metrics"],
    groups=data["groups"],
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
names = ["DS16", "DS17", "DS18", "All148"]
for ax, arm in zip(axes, arms, strict=True):
    for j, model in enumerate(models):
        values = [data["metrics"][n]["arms"][arm]["position"][model]["mean"] for n in names[:3]]
        values.append(pooled[arm][model])
        ax.bar(np.arange(4) + (j - 1) * 0.25, values, width=0.25, label=model)
    ax.axhline(1, color="black", linestyle="--", label="1km target")
    ax.set_xticks(np.arange(4), names)
    ax.set(title=arm, ylabel="Full-membership mean position error (km)")
    ax.legend(fontsize=8)
fig.savefig(HERE / "means.png", dpi=160)
text = f"""# Iteration65: complete148-recording uniform region-policy assessment

All **63 DS16,51 DS17 and34 DS18** members have matched completed results.
The uniform expanded-region candidate has pooled fitted-c mean error
**{pooled["fitted-c"]["candidate"]:.6f}km**, versus
{pooled["fitted-c"]["previous"]:.6f}km for the preceding research pipeline and
{pooled["fitted-c"]["baseline"]:.6f}km for bounded-recovery hard60 baseline.
The below1km goal remains unachieved. No single-scan diagnostic replacement or
independent-validation claim enters these means.

![Full-membership mean position errors](means.png)

| Dataset | Arm | Baseline mean km | Previous research mean km | Expanded-region mean km |
|---|---|---:|---:|---:|
"""
for name, metric in data["metrics"].items():
    for arm in arms:
        text += (
            "| "
            + name
            + " | "
            + arm
            + " | "
            + " | ".join(f"{metric['arms'][arm]['position'][m]['mean']:.6f}" for m in models)
            + " |\n"
        )
text += """
## What changed

The policy retains baseline,25km-separated and50km-separated regional finalists,
then selects each c arm using converged regional score. Downstream joint clocks,
timing pruning, RF-time and satellite-slope fitting remain the frozen research
sequence. It adds regional computation; this is not an equal-total-compute claim.
Matched c arms preserve observations, candidate inputs, other priors and stage
budgets, with c0/RF-time locks. Frequency RMS is reported separately from position.

| Arm | Improved / regressed / tied versus previous research |
|---|---:|
"""
for arm, c in changes.items():
    text += f"| {arm} | {c['improved']} / {c['regressed']} / {c['tied']} |\n"
text += """
DS16-046 is the known consumed rescue:265.789km to0.798370km fitted-c and
261.743km to2.128007km c0. Its sep50 regional receipt was explicitly reused from
iteration48; this is reproduction in the uniform policy, not new validation.
The large DS18 failure remains in all means. The separate common-bank and smooth
horizon pilots do not replace any cohort result and are still development work.

## Coverage, failures and provenance

The [full cohort report](../2026_10_09_position_error_iter51/README.md) contains
every session, per-dataset mean/median/p95/worst, convergence/fallbacks, paired
regressions, separate RMS and original48/added15 DS16 subgroup metrics.
The two historical metadata serialization failures remain immutable; separately
frozen iteration64 retries completed with unchanged numerical policy. Their
original attempts and completion sources are retained in snapshot.json.

DS18 uses the frozen34-member authority and includes the sealed archive member.
Its24 previously consumed recordings remain flagged. No earlier registry match
for the other10 does not establish unseen validation; all evaluated data here are
now consumed research. No readiness/quality gate or exclusion changes membership.
The configured Sacramento250km spatial prior remains explicit. Known/reference
coordinates and errors are evaluation-only, never operational region/seed/bank
or per-scan hyperparameter selection inputs.

## Decision

Keep the expanded-region candidate as a demonstrated consumed-data tail rescue,
not a claim of broad average improvement or a promoted production default.
Complete the ordinary-start/common-bank and smooth-horizon pilots, evaluate any
resulting policy uniformly across all three datasets, and obtain independent
validation under a frozen rule. Mean error below1km is not yet proven. Existing
production deployment, fitted-c default and longest16-track PNG rendering remain
unchanged; no new RF collection is authorized or performed.
"""
(HERE / "README.md").write_text(text)
print(pooled, changes)
