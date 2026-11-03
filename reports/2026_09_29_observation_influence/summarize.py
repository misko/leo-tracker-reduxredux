import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    receipts = json.loads((HERE / "receipts.json").read_text())
    assert len(receipts) == 9
    rows = []
    queue = []
    hashes = {}
    lines = [
        "| Panel | Training observations | Earlier budget proxy % | Ranked budget proxy % | "
        "Ratio | Top m/Hz | Refit relative error % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for receipt in receipts:
        key = receipt["panel"]
        p = HERE / f"{key}.json"
        if receipt["exit_code"] != 0 or not p.exists():
            rows.append(dict(panel=key, status="execution_failed"))
            continue
        d = json.loads(p.read_text())
        for path, digest in d["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        hashes[str(p.relative_to(ROOT))] = digest
        if not d["hessian_qualified"]:
            rows.append(dict(panel=key, status="hessian_unqualified"))
            continue
        archive = HERE / f"{key}.npz"
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == d["archive_sha256"]
        if not d["refit_qualified"]:
            rows.append(dict(panel=key, status="response_unqualified"))
            continue
        ratio = d["queue_energy_fraction"] / d["previous_energy_fraction"]
        row = dict(
            panel=key,
            status="ok",
            training_observations=d["training_observations"],
            eligible_observations=d["eligible_observations"],
            previous_fraction=d["previous_energy_fraction"],
            queue_fraction=d["queue_energy_fraction"],
            ratio=ratio,
            max_sensitivity_m_per_hz=d["top_eligible"][0]["sensitivity_m_per_hz"],
            response_relative_error=d["response_relative_error"],
            overlap=d["queue_previous_overlap"],
        )
        rows.append(row)
        lines.append(
            f"| {key} | {row['training_observations']} | {100 * row['previous_fraction']:.3f} | "
            f"{100 * row['queue_fraction']:.3f} | {ratio:.1f} | "
            f"{row['max_sensitivity_m_per_hz']:.3f} | {100 * row['response_relative_error']:.3f} |"
        )
        for rank, r in enumerate(d["top_eligible"], 1):
            queue.append(dict(panel=key, rank=rank, **r))
    valid = [r for r in rows if r["status"] == "ok"]
    output = dict(
        hashes=hashes,
        rows=rows,
        qualified_panels=len(valid),
        queued_observations=len(queue),
        median_budget_ratio=float(np.median([r["ratio"] for r in valid])) if valid else None,
    )
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    (HERE / "queue.json").write_text(
        json.dumps(
            dict(
                policy="top-eight-training-response-per-panel-at-least-5MSps",
                hashes=hashes,
                rows=queue,
            ),
            indent=2,
        )
        + "\n"
    )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(valid))
    for name, offset, label in (
        ("previous_fraction", -0.17, "Previously corrected eight"),
        ("queue_fraction", 0.17, "Ranked eight"),
    ):
        ax.barh(y + offset, [100 * r[name] for r in valid], height=0.32, label=label)
    ax.set_yticks(y, [r["panel"] for r in valid])
    ax.set_xlabel("Share of summed squared position response (%)")
    ax.set_title("Equal eight-observation budgets; local model sensitivity, not accuracy gain")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in output.items() if k not in ("hashes", "rows")}, indent=2))


if __name__ == "__main__":
    main()
