"""Render the complete fixed eight-recording local panel without exclusions."""

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import LOCAL, PREVIOUS, REPORT
from continuous_merge_study import sha, write

OUT = REPORT / "cohort"
VARIANTS = ["zero-independent", "cal-independent", "cal-parents", "cal-joined", "cal-shared"]
LABELS = ["Original", "Band offset", "Soft parents", "Soft joined", "Forced joined"]


def main():
    selection_path = PREVIOUS / "cohort-selection.json"
    selection = json.loads(selection_path.read_bytes())
    cases = []
    for member in selection["members"]:
        case = LOCAL / member["dataset"] / member["session_id"]
        protocol_path = case / "protocol.json"
        protocol = json.loads(protocol_path.read_bytes())
        for path, digest in protocol["bindings"].items():
            if sha(Path(path)) != digest:
                raise ValueError("cohort authority changed: " + path)
        evaluation_path = case / "evaluation-cohort-reference.json"
        if not evaluation_path.exists():
            evaluation_path = case / "evaluation.json"
        evaluation = json.loads(evaluation_path.read_bytes())
        seal_path = case / "evaluation-seal.json"
        if sha(seal_path) != evaluation["seal_sha256"]:
            raise ValueError("cohort seal changed")
        for path, digest in json.loads(seal_path.read_bytes()).items():
            if sha(Path(path)) != digest:
                raise ValueError("cohort numerical result changed")
        if len(evaluation["rows"]) != 18:
            raise ValueError("missing local condition in cohort")
        old = json.loads((Path(protocol["parent_case"]) / "positions/experiment.json").read_bytes())
        prepared = json.loads((Path(old["original_case"]) / "baseline.json").read_bytes())
        row = {
            "dataset": member["dataset"],
            "session_id": member["session_id"],
            "role": member["role"],
            "observations": len(prepared["observations"]["window_ids"]),
            "high_band_observations": sum(ch >= 5 for ch in prepared["observations"]["channel"]),
            "gamma_seed_hz": protocol["gamma_seed_hz"],
            "protocol_sha256": sha(protocol_path),
            "evaluation_sha256": sha(evaluation_path),
            "rows": evaluation["rows"],
        }
        cases.append(row)
        target = OUT / "receipts" / member["dataset"] / member["session_id"]
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(protocol_path, target / "protocol.json")
        shutil.copyfile(evaluation_path, target / "evaluation.json")
        shutil.copyfile(seal_path, target / "evaluation-seal.json")
        grouping = Path(protocol["parent_case"]) / "shared-refinement/protocol.json"
        group_protocol = json.loads(grouping.read_bytes())
        if "group_authority_audit" in group_protocol:
            shutil.copyfile(grouping, target / "group-authority.json")
    write(
        OUT / "results.json",
        {
            "cases": cases,
            "fits": sum(len(c["rows"]) for c in cases),
            "all_stationary": all(r["stationary"] for c in cases for r in c["rows"]),
            "selection_path": str(selection_path),
            "selection_sha256": sha(selection_path),
            "script_sha256": sha(Path(__file__)),
        },
    )
    fig, axes = plt.subplots(4, 2, figsize=(14, 12), constrained_layout=True)
    for col, dataset in enumerate(("DS20", "DS16")):
        selected = [c for c in cases if c["dataset"] == dataset]
        for ax, case in zip(axes[:, col], selected, strict=True):
            lookup = {(r["variant"], r["arm"]): r for r in case["rows"]}
            x = np.arange(len(VARIANTS))
            for arm, shift, color in [
                ("fitted-c", -0.18, "tab:blue"),
                ("zero-c", 0.18, "tab:orange"),
            ]:
                ax.bar(
                    x + shift,
                    [lookup[v, arm]["reference_error_m"] / 1000 for v in VARIANTS],
                    width=0.36,
                    color=color,
                    label=arm,
                )
            prefix = case["session_id"][5:13] if dataset == "DS20" else case["session_id"][8:16]
            ax.set_title(f"{dataset} {prefix} · {case['high_band_observations']} CH5–8 rows")
            ax.set_xticks(x, LABELS, fontsize=8)
            ax.set_ylabel("Reference error (km)")
            ax.grid(axis="y", alpha=0.2)
    axes[0, 0].legend(fontsize=9)
    fig.suptitle(
        "Fixed development cohort · all 144 local fits stationary\n"
        "Per-panel scales differ; 156 km failure retained",
        fontsize=14,
    )
    fig.savefig(OUT / "position-panel.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for c in [c for c in cases if c["dataset"] == "DS20"]:
        lookup = {(r["variant"], r["arm"]): r for r in c["rows"]}
        for arm, marker in [("fitted-c", "o"), ("zero-c", "^")]:
            baseline, calibrated = lookup["zero-independent", arm], lookup["cal-independent", arm]
            x = calibrated["singleton_nll"] - baseline["singleton_nll"]
            y = (calibrated["reference_error_m"] - baseline["reference_error_m"]) / 1000
            axes[0].scatter(
                x,
                y,
                marker=marker,
                color="tab:blue" if arm == "fitted-c" else "tab:orange",
                s=50,
                label=arm if c["session_id"].startswith("fast-014") else None,
            )
            axes[0].annotate(
                c["session_id"][5:9],
                (x, y),
                xytext=(-28, 4) if c["session_id"].startswith("fast-3b67") else (4, 4),
                textcoords="offset points",
                fontsize=8,
            )
        row = lookup["cal-independent", "fitted-c"]
        axes[1].scatter(
            row["band_offsets_hz"][0] / 1000,
            row["band_offsets_hz"][1] / 1000,
            s=60,
            label=c["session_id"][5:13],
        )
    axes[0].axhline(0, color="black", lw=1)
    axes[0].axvline(0, color="black", lw=1)
    axes[0].set_xlabel("Calibrated − original singleton NLL")
    axes[0].set_ylabel("Calibrated − original reference error (km)")
    axes[0].legend()
    axes[1].set_xlabel("Fitted RX0 high-band offset (kHz)")
    axes[1].set_ylabel("Fitted RX1 high-band offset (kHz)")
    axes[1].legend(loc="center right")
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle("Better frequency fit does not guarantee better position · DS20 local panel")
    fig.savefig(OUT / "fit-versus-position-and-offsets.png", dpi=160)
    plt.close(fig)
    shutil.copyfile(
        REPORT / "joined-parent-start-audit.json", OUT / "joined-parent-start-audit.json"
    )
    recovery_path = OUT / "global-recovery/evaluation.json"
    if recovery_path.exists():
        recovery = json.loads(recovery_path.read_bytes())
        modes = ["raw-original", "raw-joined", "cal-original", "cal-joined"]
        lookup = {(r["mode"], r["arm"]): r for r in recovery["rows"]}
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
        for ax, selected in zip(axes, [modes, modes[2:]], strict=True):
            x = np.arange(len(selected))
            for arm, shift, color in [
                ("fitted-c", -0.18, "tab:blue"),
                ("zero-c", 0.18, "tab:orange"),
            ]:
                values = [lookup[m, arm]["reference_error_m"] / 1000 for m in selected]
                bars = ax.bar(x + shift, values, width=0.36, color=color, label=arm)
                ax.bar_label(
                    bars,
                    labels=[f"{v:.2f}" for v in values],
                    padding=3,
                    fontsize=9,
                    rotation=45 if len(selected) == 4 else 0,
                )
            ax.set_xticks(x, selected, fontsize=9)
            ax.set_ylabel("Configured-reference error (km)")
            ax.grid(axis="y", alpha=0.2)
        axes[0].set_yscale("log")
        axes[0].set_ylim(0.5, 350)
        axes[0].set_title("Full 400-point discovery · logarithmic scale")
        axes[0].legend()
        axes[1].set_ylim(0, 4.4)
        axes[1].set_title("Calibrated conditions · linear scale")
        fig.suptitle("Recovery 1836: development-only fixed calibration applied before discovery")
        fig.savefig(OUT / "global-recovery.png", dpi=160)
        plt.close(fig)
    print(
        json.dumps(
            {
                "cases": len(cases),
                "fits": sum(len(c["rows"]) for c in cases),
                "all_stationary": all(r["stationary"] for c in cases for r in c["rows"]),
            }
        )
    )


if __name__ == "__main__":
    main()
