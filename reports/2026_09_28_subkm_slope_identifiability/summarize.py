"""Verify exported curvature arithmetic and render the local diagnostic."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
rows = []
bindings = 0
for ordinal in range(1, 9):
    unit = f"single-{ordinal:03d}"
    receipt = HERE / "receipts" / unit
    assert (receipt / "exit-code.txt").read_text().strip() == "0"
    for path, expected in json.loads((receipt / "launch.json").read_text())["sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
        bindings += 1
    row = json.loads((HERE / "results" / f"{unit}.json").read_text())
    assert row["unit_id"] == unit
    for name, matrix in [
        ("observed_retention", np.asarray(row["observed_hessian_half_steps"])),
        ("optimistic_retention", np.asarray(row["optimistic_fisher"])),
    ]:
        matrix = (matrix + matrix.T) / 2
        result = row[name]
        if result["status"] != "positive":
            continue
        for key, indices in [("fixed_slope", [2]), ("free_slope", [2, 3])]:
            cross = matrix[np.ix_([0, 1], indices)]
            expected = matrix[:2, :2] - cross @ np.linalg.solve(
                matrix[np.ix_(indices, indices)], cross.T
            )
            assert np.allclose(result[key], expected, rtol=1e-10, atol=1e-10)
        # Generalized eigenvalues using a distinct Cholesky whitening.
        factor = np.linalg.cholesky(result["fixed_slope"])
        inverse = np.linalg.inv(factor)
        eigenvalues = np.linalg.eigvalsh(inverse @ result["free_slope"] @ inverse.T)
        assert np.allclose(eigenvalues, result["information_retention_eigenvalues"], atol=1e-10)
        assert np.isclose(
            1 / np.sqrt(eigenvalues.min()), result["worst_direction_standard_error_inflation"]
        )
    rows.append(row)
summary = {
    "records": 8,
    "binding_checks": bindings,
    "numerical_checks_pass": sum(row["numerical_checks_pass"] for row in rows),
    "positive_observed_blocks": sum(
        row["observed_retention"]["status"] == "positive" for row in rows
    ),
    "max_relative_step_sensitivity": max(row["relative_step_sensitivity"] for row in rows),
    "max_relative_asymmetry": max(row["relative_asymmetry"] for row in rows),
    "scope": (
        "Source verification and independent matrix arithmetic; "
        "not independent likelihood fits."
    ),
}
audit_path = HERE / "audit-summary.json"
if audit_path.exists():
    assert json.loads(audit_path.read_text()) == summary
else:
    with audit_path.open("x") as stream:
        json.dump(summary, stream, indent=2)
positions = np.arange(8)
fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
for offset, key, label, color in [
    (-0.18, "observed_retention", "Full-mixture observed curvature", "#347c91"),
    (0.18, "optimistic_retention", "Optimistic complete-label Fisher", "#c99742"),
]:
    values = [r[key].get("information_retention_eigenvalues", [float("nan")])[0] for r in rows]
    ax.bar(positions + offset, np.asarray(values) * 100, width=0.34, label=label, color=color)
ax.set(
    xticks=positions,
    xticklabels=[f"{i:03d}" for i in range(1, 9)],
    ylim=(0, 105),
    ylabel="Position information retained in worst direction (%)",
    xlabel="Chronological DS7 recording",
    title="Cost of freeing slope, with timing already free",
)
ax.axhline(100, color="black", linewidth=0.8, linestyle=":")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
fig.suptitle("Local expansion at fixed full88 position/timing; not a location uncertainty estimate")
fig.savefig(HERE / "identifiability.png", dpi=170)
fig.savefig(HERE / "identifiability.svg")
print(json.dumps(summary, indent=2))
