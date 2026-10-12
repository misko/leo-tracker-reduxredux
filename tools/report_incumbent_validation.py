"""Report matched refinement and full-pipeline comparisons with pending cases."""

import json
import math
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import LOCAL, PREVIOUS, REPORT
from continuous_merge_consistency_study import verify as verify_full
from continuous_merge_study import sha, write
from incumbent_joined_study import DESTINATION, verify

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

OUT = REPORT / "refinement"


def comparison(member):
    case = PREVIOUS / "local" / member["dataset"] / member["session_id"]
    protocol_path = case / "positions/experiment.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify_full(protocol)
    files = [
        case / "positions" / name
        for name in (
            "evaluation-baseline-consistent.json",
            "evaluation-baseline-shape-consistent.json",
            "evaluation-offline-reference-baseline-consistent.json",
        )
    ]
    evaluation_path = next(p for p in files if p.exists())
    evaluation = json.loads(evaluation_path.read_bytes())
    seals = list((case / "positions").glob("evaluation-seal-*.json"))
    matching = [p for p in seals if sha(p) == evaluation["seal_sha256"]]
    if len(matching) != 1:
        raise ValueError("full comparison seal changed")
    seal = json.loads(matching[0].read_bytes())
    if seal["position_protocol_sha256"] != sha(protocol_path):
        raise ValueError("sealed full protocol changed")
    rows = []
    checks = []
    for variant in ("baseline", "consistent"):
        terminal_path = case / "positions" / variant / "terminal.json"
        if sha(terminal_path) != seal["terminals"][variant]:
            raise ValueError("sealed full numerical result changed")
        terminal = json.loads(terminal_path.read_bytes())
        if terminal["status"] != "complete":
            raise ValueError("development pair incomplete")
        finals = terminal["result"]["finals"]
        a, b = [next(f for f in finals if f["arm"] == arm) for arm in ("fitted-c", "zero-c")]
        checks.append(
            {
                "mode": variant,
                "common_bank": a["satellites"] == b["satellites"],
                "common_stage": a["accepted_stage"] == b["accepted_stage"],
                "all_stationary": a["fit"]["converged"] and b["fit"]["converged"],
            }
        )
        for arm in ("fitted-c", "zero-c"):
            if "results" in evaluation:
                e = evaluation["results"][variant][arm]
                selected = e["selected"]
                data = {
                    "reference_error_m": selected["horizontal_error_m"],
                    "objective": selected["objective"],
                    "posterior_rms_hz": selected["posterior_rms_hz"],
                    "likelihood_nll": e["likelihood_nll"],
                    "accepted_stage": e["accepted_stage"],
                }
            else:
                data = next(
                    e for e in evaluation["rows"] if e["variant"] == variant and e["arm"] == arm
                )
            rows.append(
                {"mode": variant, "arm": arm, **data, "terminal_sha256": sha(terminal_path)}
            )
    target = OUT / "full-development" / member["dataset"] / member["session_id"]
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(evaluation_path, target / "evaluation.json")
    return {
        "dataset": member["dataset"],
        "session_id": member["session_id"],
        "role": member["role"],
        "rows": rows,
        "c_arm_checks": checks,
        "protocol_sha256": sha(protocol_path),
        "evaluation_sha256": sha(evaluation_path),
    }


def main():
    protocol_path = DESTINATION / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    evaluation = json.loads((DESTINATION / "evaluation.json").read_bytes())
    seal_path = DESTINATION / "evaluation-seal.json"
    if evaluation["seal_sha256"] != sha(seal_path):
        raise ValueError("refinement seal changed")
    for path, digest in json.loads(seal_path.read_bytes()).items():
        if sha(Path(path)) != digest:
            raise ValueError("refinement result changed")
    (OUT / "incumbent").mkdir(parents=True, exist_ok=True)
    for name in ("protocol.json", "evaluation.json", "evaluation-seal.json"):
        shutil.copyfile(DESTINATION / name, OUT / "incumbent" / name)
    lookup = {
        (r["session_id"], r["calibration"], r["arm"], r["start"]): r for r in evaluation["rows"]
    }
    changed = []
    for row in evaluation["rows"]:
        if row["start"] == "incumbent" and row["source"] == "parents":
            control = lookup[row["session_id"], row["calibration"], row["arm"], "continue"]
            changed.append(
                {
                    "session_id": row["session_id"],
                    "calibration": row["calibration"],
                    "arm": row["arm"],
                    "objective_gain": control["objective"] - row["objective"],
                    "original_error_m": control["reference_error_m"],
                    "new_error_m": row["reference_error_m"],
                    "error_change_m": row["reference_error_m"] - control["reference_error_m"],
                }
            )
    write(
        OUT / "incumbent-changes.json",
        {
            "rows": changed,
            "fits": len(evaluation["rows"]),
            "all_attempts_stationary": all(r["attempt_stationary"] for r in evaluation["rows"]),
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    labels = [r["session_id"][5:9] + " " + r["calibration"] + " " + r["arm"] for r in changed]
    x = np.arange(len(changed))
    axes[0].bar(x, [r["objective_gain"] for r in changed], color="tab:blue")
    axes[0].set_ylabel("Joined objective improvement")
    axes[1].bar(
        x,
        [r["error_change_m"] for r in changed],
        color=["tab:orange" if r["error_change_m"] > 0 else "tab:green" for r in changed],
    )
    axes[1].set_ylabel("Reference error change (m) · lower is better")
    for ax in axes:
        ax.set_xticks(x, labels, rotation=20, fontsize=8)
        ax.axhline(0, color="black", lw=1)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Same joined model and original disk · feasible parent start versus joined continuation"
    )
    fig.savefig(OUT / "incumbent-score-and-position.png", dpi=160)
    plt.close(fig)

    selection_path = PREVIOUS / "cohort-selection.json"
    selection = json.loads(selection_path.read_bytes())
    full = [comparison(member) for member in selection["members"]]
    write(
        OUT / "full-development-results.json",
        {"cases": full, "selection_sha256": sha(selection_path)},
    )
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    for ax, ds in zip(axes, ("DS20", "DS16"), strict=True):
        cases = [c for c in full if c["dataset"] == ds]
        x = np.arange(len(cases))
        for arm, shift, color in [("fitted-c", -0.18, "tab:blue"), ("zero-c", 0.18, "tab:orange")]:
            changes = []
            for c in cases:
                rows = {(r["mode"], r["arm"]): r for r in c["rows"]}
                changes.append(
                    rows["consistent", arm]["reference_error_m"]
                    - rows["baseline", arm]["reference_error_m"]
                )
            ax.bar(x + shift, changes, width=0.36, color=color, label=arm)
        ax.set_xticks(x, [c["session_id"][:17] for c in cases], fontsize=8)
        ax.set_ylabel("Joined − original error (m)")
        ax.set_title(ds + " full B7 · raw observations")
        ax.axhline(0, color="black", lw=1)
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
    fig.savefig(OUT / "full-development-error-changes.png", dpi=160)
    plt.close(fig)

    validation = json.loads((REPORT / "validation-selection.json").read_bytes())
    statuses = []
    for member in validation["members"]:
        ds, sid = member["dataset"], member["session_id"]
        base = (
            LOCAL / ds / sid / "global-transfer"
            if ds == "DS20"
            else PREVIOUS / "local" / ds / sid / "positions"
        )
        states = {}
        for mode in member["planned_modes"]:
            p = base / mode / "terminal.json"
            states[mode] = json.loads(p.read_bytes())["status"] if p.exists() else "pending"
        ep = (
            base / "evaluation.json"
            if ds == "DS20"
            else base / "evaluation-baseline-consistent.json"
        )
        status = {
            "dataset": ds,
            "session_id": sid,
            "role": member["role"],
            "numerical_states": states,
            "evaluation_available": ep.exists(),
        }
        if ep.exists():
            target = OUT / "validation" / ds / sid
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ep, target / "evaluation.json")
            status["evaluation_sha256"] = sha(ep)
            status["evaluation"] = json.loads(ep.read_bytes())
            status["c_arm_checks"] = []
            for mode in member["planned_modes"]:
                terminal = json.loads((base / mode / "terminal.json").read_bytes())
                finals = terminal["result"]["finals"]
                a, b = [
                    next(f for f in finals if f["arm"] == arm) for arm in ("fitted-c", "zero-c")
                ]
                status["c_arm_checks"].append(
                    {
                        "mode": mode,
                        "common_stage": a["accepted_stage"] == b["accepted_stage"],
                        "common_bank": a["satellites"] == b["satellites"],
                        "all_stationary": a["fit"]["converged"] and b["fit"]["converged"],
                    }
                )
            seal = (
                base / "evaluation-seal.json"
                if ds == "DS20"
                else base / "evaluation-seal-baseline-consistent.json"
            )
            if sha(seal) != status["evaluation"]["seal_sha256"]:
                raise ValueError("validation evaluation seal changed")
            sealed = json.loads(seal.read_bytes())
            expected = (
                sealed
                if ds == "DS20"
                else {
                    str(base / mode / "terminal.json"): digest
                    for mode, digest in sealed["terminals"].items()
                }
            )
            for path, digest in expected.items():
                if sha(Path(path)) != digest:
                    raise ValueError("sealed validation numerical result changed")
            shutil.copyfile(seal, target / "evaluation-seal.json")
            for check in status["c_arm_checks"]:
                if check["common_stage"] and check["common_bank"]:
                    continue
                terminal_path = base / check["mode"] / "terminal.json"
                terminal = json.loads(terminal_path.read_bytes())
                attempts = terminal["result"]["b7"]["attempts"]
                stage = next(
                    s
                    for s in ("B7", "C6", "B5", "B4W", "B4", "B3")
                    if s in attempts
                    and all(
                        attempts[s].get(a) and attempts[s][a]["converged"]
                        for a in ("fitted-c", "zero-c")
                    )
                )
                reference = status["evaluation"]["reference"]
                rows = []
                for arm in ("fitted-c", "zero-c"):
                    fit = attempts[stage][arm]
                    lat, lon, rlat, rlon = map(
                        math.radians, (*coordinates(RegionalPrior(), fit["vector"][:2]), *reference)
                    )
                    h = (
                        math.sin((lat - rlat) / 2) ** 2
                        + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
                    )
                    rows.append(
                        {
                            "arm": arm,
                            "stage": stage,
                            "stationary": fit["converged"],
                            "reference_error_m": 2
                            * 6371008.8
                            * math.asin(math.sqrt(min(1, max(0, h)))),
                            "objective": fit["objective"],
                            "likelihood_nll": fit["joint_state"]["likelihood_nll"],
                            "posterior_rms_hz": fit["posterior_rms_hz"],
                        }
                    )
                write(
                    target / ("common-stage-" + check["mode"] + ".json"),
                    {
                        "rows": rows,
                        "mode": check["mode"],
                        "stage": stage,
                        "terminal_sha256": sha(terminal_path),
                        "scope": (
                            "Existing paired attempts use the same model, bank, priors, non-RF "
                            "seed and stage budgets; references only evaluate completed "
                            "sealed fits."
                        ),
                    },
                )
                check["controlled_stage"] = stage
                check["controlled_rows"] = rows
        statuses.append(status)
    write(
        OUT / "validation-status.json",
        {
            "members": statuses,
            "selection_sha256": sha(REPORT / "validation-selection.json"),
            "scope": (
                "Every selected member retained, including pending, failed and "
                "missing-reference states."
            ),
        },
    )
    if any(s["evaluation_available"] for s in statuses):
        fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
        for status in statuses:
            if status["dataset"] != "DS20" or not status["evaluation_available"]:
                continue
            rows = status["evaluation"]["rows"]
            modes = ["raw-original", "raw-joined", "cal-original", "cal-joined"]
            lookup = {(r["mode"], r["arm"]): r for r in rows}
            x = np.arange(4)
            for arm, shift, color in [
                ("fitted-c", -0.18, "tab:blue"),
                ("zero-c", 0.18, "tab:orange"),
            ]:
                ax.bar(
                    x + shift,
                    [lookup[m, arm]["reference_error_m"] / 1000 for m in modes],
                    width=0.36,
                    color=color,
                    label=arm,
                )
            ax.set_xticks(x, modes)
            ax.set_title(status["session_id"])
            ax.set_ylabel("Configured-reference error (km)")
            ax.grid(axis="y", alpha=0.2)
            ax.legend()
            break
        fig.savefig(OUT / "first-validation.png", dpi=160)
        plt.close(fig)
    print(
        json.dumps(
            {
                "refinement_fits": 64,
                "full_development_cases": len(full),
                "validation_evaluated": sum(s["evaluation_available"] for s in statuses),
            }
        )
    )


if __name__ == "__main__":
    main()
