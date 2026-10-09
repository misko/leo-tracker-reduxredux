"""Replay historical proposal receipts; no optimizer or position scoring."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from clock_starts import clock_starts, wrap  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def main():
    plan = read(HERE / "protocol.json")
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first qualification")
    results = []
    for label in plan["labels"]:
        audit = read(REPORTS / "2026_10_08_position_error_iter34/results" / f"{label}.json")
        for sigma in plan["sigmas"]:
            for initialization in plan["initializations"]:
                row = next(
                    r
                    for r in audit["candidates"]
                    if r["arm"] == "fitted-c"
                    and r["relative_sigma_s"] == sigma
                    and r["initialization"] == initialization
                )
                if sigma == 2 and initialization == "original-start":
                    source = REPORTS / "2026_10_08_position_error_iter36/results" / f"{label}.json"
                else:
                    source = (
                        REPORTS
                        / "2026_10_08_position_error_iter37/results"
                        / f"{label}-{sigma:g}-{initialization}.json"
                    )
                saved = read(source)
                residual = np.asarray(row["residual_hz"])
                rebuilt = wrap(
                    np.array([p["measured_difference_hz"] for p in audit["pairs"]])
                    - np.asarray(row["predicted_receiver_difference_hz"])
                )
                np.testing.assert_allclose(rebuilt, residual, atol=1e-7, rtol=0)
                # Historical pair times were centered at the observation time center.
                # Recover that fixed center from the bound preparation receipt.
                center = plan["time_center_s"][label]
                times = np.array([p["time_s"] for p in audit["pairs"]]) - center
                proposals, starts, rejected = clock_starts(saved["shared_seed"], times, residual)
                assert proposals == saved["proposals"]
                assert rejected == saved["rejected"]
                assert {name for name, _ in starts} == {
                    r["initialization"] for r in saved["candidates"]
                }
                results.append(
                    dict(
                        label=label,
                        sigma=sigma,
                        initialization=initialization,
                        proposals=proposals,
                        accepted_starts=len(starts),
                        rejected=rejected,
                        source=str(source.relative_to(ROOT)),
                        max_residual_reconstruction_hz=float(np.max(abs(rebuilt - residual))),
                    )
                )
    (HERE / "results.json").write_text(
        json.dumps(dict(rows=results, status="passed"), indent=2) + "\n"
    )
    fig, ax = plt.subplots(figsize=(10, 4), layout="constrained")
    for i, row in enumerate(results):
        ax.scatter(
            [i] * len(row["proposals"]),
            [p["slope_hz_s"] for p in row["proposals"]],
            s=[p["support"] for p in row["proposals"]],
            alpha=0.65,
        )
    ax.set_xticks(
        range(len(results)),
        [
            f"{r['label'][-3:]} / {r['sigma']} / "
            + ("original" if r["initialization"] == "original-start" else "zero timing")
            for r in results
        ],
        rotation=30,
        ha="right",
    )
    ax.set(
        ylabel="Proposed relative slope correction (Hz/s)",
        title="Historical clock proposals reproduced; marker area = support count",
    )
    fig.savefig(HERE / "proposals.png", dpi=160)
    print("Qualified", len(results), "historical proposal inventories")


if __name__ == "__main__":
    main()
