"""Publish compact sealed calibration/merge outcomes and scientific figures."""

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import LOCAL, REPORT, ROOT
from continuous_merge_study import sha, write

CASES = {
    "DS20": "fast-014c72ff95ab599c51ba3b3ec9b92cb8",
    "DS16": "scan-fw-0e40d0535caa0b16",
}
VARIANTS = [
    "zero-independent",
    "zero-parents",
    "zero-joined",
    "zero-shared",
    "cal-independent",
    "cal-parents",
    "cal-joined",
    "cal-shared",
    "cal-zero-seed",
]
LABELS = [
    "No band offset\nIndependent",
    "No band offset\nSoft parents",
    "No band offset\nSoft joined",
    "No band offset\nForced joined",
    "Profiled offset\nIndependent",
    "Profiled offset\nSoft parents",
    "Profiled offset\nSoft joined",
    "Profiled offset\nForced joined",
    "Offset from zero\nIndependent",
]


def main():
    cases = []
    for dataset, sid in CASES.items():
        case = LOCAL / dataset / sid
        protocol_path, evaluation_path = case / "protocol.json", case / "evaluation.json"
        protocol = json.loads(protocol_path.read_bytes())
        evaluation = json.loads(evaluation_path.read_bytes())
        for path, digest in protocol["bindings"].items():
            if sha(Path(path)) != digest:
                raise ValueError("executed scientific source changed: " + path)
        seal_path = case / "evaluation-seal.json"
        if sha(seal_path) != evaluation["seal_sha256"]:
            raise ValueError("evaluation seal changed")
        for path, digest in json.loads(seal_path.read_bytes()).items():
            if sha(Path(path)) != digest:
                raise ValueError("sealed numerical fit changed")
        if not all(r["stationary"] for r in evaluation["rows"]):
            raise ValueError("report requires the completed stationary local panel")
        target = REPORT / "receipts" / dataset
        target.mkdir(parents=True, exist_ok=True)
        for filename in ("protocol.json", "evaluation.json", "evaluation-seal.json"):
            shutil.copyfile(case / filename, target / filename)
        old = Path(protocol["parent_case"])
        old_protocol = json.loads((old / "positions/experiment.json").read_bytes())
        prepared = json.loads((Path(old_protocol["original_case"]) / "baseline.json").read_bytes())
        cases.append(
            {
                "dataset": dataset,
                "session_id": sid,
                "role": protocol["role"],
                "observations": len(prepared["observations"]["window_ids"]),
                "high_band_observations": sum(
                    ch >= 5 for ch in prepared["observations"]["channel"]
                ),
                "active_band_receivers": protocol["active_band_receivers"],
                "gamma_seed_hz": protocol["gamma_seed_hz"],
                "protocol_sha256": sha(protocol_path),
                "evaluation_sha256": sha(evaluation_path),
                "rows": evaluation["rows"],
            }
        )
    write(
        REPORT / "local-ablation-results.json",
        {
            "cases": cases,
            "fits": sum(len(c["rows"]) for c in cases),
            "executed_base_commit": "802fb26c43b40305d7974f1077a805f2c195266b",
            "report_tool_sha256": sha(Path(__file__)),
        },
    )
    fig, axes = plt.subplots(2, 1, figsize=(15, 8), constrained_layout=True)
    for ax, case in zip(axes, cases, strict=True):
        lookup = {(r["variant"], r["arm"]): r for r in case["rows"]}
        x = np.arange(len(VARIANTS))
        for arm, shift, color in [("fitted-c", -0.18, "tab:blue"), ("zero-c", 0.18, "tab:orange")]:
            ax.bar(
                x + shift,
                [lookup[v, arm]["reference_error_m"] / 1000 for v in VARIANTS],
                width=0.36,
                color=color,
                label=arm,
            )
        ax.set_xticks(x, LABELS, fontsize=8)
        ax.set_ylabel("Configured-reference error (km)")
        ax.set_title(
            f"{case['dataset']} · {case['session_id']} · "
            f"{case['observations']} retained observations, "
            f"{case['high_band_observations']} CH5–8"
        )
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
    fig.suptitle(
        "Matched local B7 refinements · shared seed, catalogue and budgets\n"
        "Exposed development recordings; conditional c ablations",
        fontsize=13,
    )
    fig.savefig(REPORT / "local-position-ablation.png", dpi=160)
    plt.close(fig)

    ds20 = next(c for c in cases if c["dataset"] == "DS20")
    rows = ds20["rows"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for ax, key, label in zip(
        axes[:2],
        ["singleton_nll", "singleton_rms_hz"],
        ["Original singleton negative log likelihood", "Posterior-weighted frequency RMS (Hz)"],
        strict=True,
    ):
        for arm, marker in [("fitted-c", "o"), ("zero-c", "^")]:
            for calibration, color in [("zero", "tab:blue"), ("cal", "tab:green")]:
                selected = [
                    r
                    for r in rows
                    if r["arm"] == arm
                    and r["variant"].startswith(calibration + "-")
                    and r["variant"] != "cal-zero-seed"
                ]
                ax.scatter(
                    [r[key] for r in selected],
                    [r["reference_error_m"] / 1000 for r in selected],
                    color=color,
                    marker=marker,
                    s=60,
                    label=f"{calibration}: {arm}",
                )
            failed = next(r for r in rows if r["arm"] == arm and r["variant"] == "cal-zero-seed")
            ax.scatter(
                failed[key],
                failed["reference_error_m"] / 1000,
                color="tab:red",
                marker=marker,
                s=65,
                label=f"Zero initialization: {arm}",
            )
        ax.set_xlabel(label)
        ax.set_ylabel("Configured-reference error (km)")
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    for arm, marker in [("fitted-c", "o"), ("zero-c", "^")]:
        for variant, color in [("cal-independent", "tab:green"), ("cal-zero-seed", "tab:red")]:
            row = next(r for r in rows if r["arm"] == arm and r["variant"] == variant)
            axes[2].scatter(
                row["band_offsets_hz"][0] / 1000,
                row["band_offsets_hz"][1] / 1000,
                color=color,
                marker=marker,
                s=65,
            )
    axes[2].scatter(
        ds20["gamma_seed_hz"][0] / 1000,
        ds20["gamma_seed_hz"][1] / 1000,
        marker="x",
        s=100,
        color="black",
        label="Data-only profile seed",
    )
    axes[2].set_xlabel("RX0 CH5–8 offset (kHz)")
    axes[2].set_ylabel("RX1 CH5–8 offset (kHz)")
    axes[2].grid(alpha=0.2)
    axes[2].legend(fontsize=8)
    fig.suptitle(
        "DS20: fit and position measured separately · "
        "initialization changes the stationary solution",
        fontsize=13,
    )
    fig.savefig(REPORT / "frequency-fit-and-initialization.png", dpi=160)
    plt.close(fig)

    audit = json.loads((REPORT / "edge-slope-sign-audit.json").read_bytes())
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    for edge, color in [("lower", "tab:blue"), ("upper", "tab:orange")]:
        slopes = [
            t["slope_hz_s"] / 1000
            for r in audit["rows"]
            for t in r["tracks"]
            if t["lane"][1] == edge
        ]
        ax.hist(
            slopes,
            bins=np.linspace(-7, 1, 50),
            color=color,
            alpha=0.6,
            label=f"{edge}: {len(slopes)} segments",
        )
    ax.axvline(0, color="black", lw=1)
    ax.set_xlabel("Orbit-blind segment slope (kHz/s), normalized to 11.2 GHz")
    ax.set_ylabel("Qualified segments")
    ax.set_title("All 18 DS20 members · ≥15 observations over ≥15 s")
    ax.legend()
    fig.savefig(REPORT / "edge-slope-signs.png", dpi=160)
    plt.close(fig)

    recovery = Path(
        "/srv/bulk/leo-dev/leo-track-merge-consistency/reports/2026_10_12_consistent_track_merge/local/DS20/fast-1836ee948f30c7b7a28a28c5b596dac2/positions/evaluation-offline-reference-baseline-consistent.json"
    )
    shutil.copyfile(recovery, REPORT / "recovered-reference-evaluation.json")
    pairs = Path("/srv/bulk/leo-dev/leo-track-merge-study/pair-plot-review")
    for source, destination in [
        ("glrt-cfo-joined-curves-verified.png", "verified-anchor-curves.png"),
        ("verified-fit-summary.json", "verified-anchor-summary.json"),
    ]:
        shutil.copyfile(pairs / source, REPORT / destination)
    paths = [
        ROOT / p
        for p in (
            "src/leo/analysis/lnb_band_objective.py",
            "src/leo/analysis/lnb_band_calibration.py",
            "tools/band_calibrated_merge_study.py",
            "tools/global_band_merge_study.py",
        )
    ]
    write(
        REPORT / "source-provenance.json",
        {
            "files": {str(p.relative_to(ROOT)): sha(p) for p in paths},
            "numerical_protocols": {c["dataset"]: c["protocol_sha256"] for c in cases},
            "reference_evaluation": sha(recovery),
        },
    )
    print(json.dumps({"fits": 36, "all_stationary": True, "report": str(REPORT)}))


if __name__ == "__main__":
    main()
