"""Verify and publish serial incumbent runtime and conditional coarse outcomes."""

import inspect
import json
import statistics
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import REPORT
from clock_conditioned_merge_study import verify
from continuous_merge_study import sha, write
from incumbent_clock_merge_study import OUTPUT

from leo.analysis.hard60_score import Hard60Objective, likelihood

PUBLIC = REPORT / "incumbent-clock"


def main():
    protocol_path = OUTPUT / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    parent = json.loads(Path(protocol["parent_protocol"]).read_bytes())
    verify(parent["bindings"])
    rows, seal = [], {}
    for budget in protocol["budgets"]:
        for case in protocol["cases"]:
            for cal in case["calibrations"]:
                for mode in protocol["modes"]:
                    path = (
                        OUTPUT
                        / budget
                        / case["dataset"]
                        / case["session_id"]
                        / (cal + "-" + mode + ".json")
                    )
                    if not path.exists():
                        raise ValueError("complete fixed panel required: " + str(path))
                    data = json.loads(path.read_bytes())
                    assert data["protocol_sha256"] == sha(protocol_path)
                    seal[str(path)] = sha(path)
                    record = {
                        k: data[k]
                        for k in ("case", "budget", "calibration", "mode", "status", "reason")
                    }
                    record["numerical_result_sha256"] = sha(path)
                    if data["status"] == "complete":
                        audit = data["audit"]
                        packets = audit["candidate_packets"]
                        selected = data["selected"]
                        original = next(
                            i
                            for i, c in enumerate(audit["candidates"])
                            if c["source"]["kind"] == "original"
                        )
                        cost = audit["candidates"][selected["incumbent"]]["score"]
                        assert cost <= audit["candidates"][original]["score"] + 1e-9
                        for name, fits in data["fits"].items():
                            np.testing.assert_array_equal(
                                fits["zero-c"]["vector"][:2], case["point"]
                            )
                            np.testing.assert_array_equal(
                                fits["fitted-c"]["vector"][:2], case["point"]
                            )
                            assert abs(fits["zero-c"]["vector"][6]) <= 1e-10
                            assert len(fits["zero-c"]["vector"]) == len(
                                packets[selected[name]]["vector"]
                            )
                        for reused, source in data["exact_fit_reuse"].items():
                            assert (
                                packets[selected[reused]]["satellite_indices"]
                                == packets[selected[source]]["satellite_indices"]
                            )
                            assert (
                                packets[selected[reused]]["vector"]
                                == packets[selected[source]]["vector"]
                            )
                            assert data["fits"][reused] == data["fits"][source]
                        record.update(
                            seconds=audit["seconds"],
                            complete_path=audit["complete_path"],
                            timed_out=audit["timed_out"],
                            profiles=audit["profiles"],
                            events=audit["events"],
                            candidates=audit["candidates"],
                            selected=selected,
                            fits=data["fits"],
                            exact_fit_reuse=data["exact_fit_reuse"],
                            oracle=data["oracle"],
                            original_score=audit["candidates"][original]["score"],
                            selected_score=cost,
                            catalogue_numbers=data["catalogue_numbers"],
                        )
                    rows.append(record)
    summary = []
    for budget in protocol["budgets"]:
        complete = [r for r in rows if r["budget"] == budget and r["status"] == "complete"]
        conditioned = [r for r in complete if r["mode"].endswith("conditioned")]
        controls = [r for r in complete if r["mode"].endswith("control")]
        sources = Counter()
        comparisons = []
        unique_stationary = 0
        for row in complete:
            source = row["candidates"][row["selected"]["incumbent"]]["source"]
            sources[
                "original"
                if source["kind"] == "original"
                else "final-pass"
                if source["pass"] == 2
                else "intermediate-pass"
            ] += 1
            for selection, fits in row["fits"].items():
                if selection not in row["exact_fit_reuse"]:
                    unique_stationary += sum(f["converged"] for f in fits.values())
            for arm in ("fitted-c", "zero-c"):
                final, incumbent = (row["fits"][s][arm] for s in ("final", "incumbent"))
                if final["converged"] and incumbent["converged"]:
                    comparisons.append(
                        {
                            "delta": incumbent["objective"] - final["objective"],
                            "same_bank": row["catalogue_numbers"]["incumbent"]
                            == row["catalogue_numbers"]["final"],
                            "changed": not row["exact_fit_reuse"],
                        }
                    )
        changed = [c for c in comparisons if c["changed"]]
        same_bank_changed = [c for c in changed if c["same_bank"]]
        summary.append(
            {
                "budget": budget,
                "conditions": len(complete),
                "failed": sum(r["budget"] == budget and r["status"] != "complete" for r in rows),
                "complete_paths": sum(r["complete_path"] for r in complete),
                "timed_out_paths": sum(r["timed_out"] for r in complete),
                "conditioned_complete_paths": sum(r["complete_path"] for r in conditioned),
                "controls_seconds": [
                    min(r["seconds"] for r in controls),
                    max(r["seconds"] for r in controls),
                ],
                "conditioned_seconds": [
                    min(r["seconds"] for r in conditioned),
                    max(r["seconds"] for r in conditioned),
                ],
                "oracle_controls": sum(r["oracle"] is not None for r in complete),
                "max_oracle_vector_difference": max(
                    r["oracle"]["max_vector_difference"] for r in controls
                ),
                "selected_sources": dict(sources),
                "coherence_worse_than_original": sum(
                    r["selected_score"] > r["original_score"] + 1e-9 for r in complete
                ),
                "logical_coarse_attempts": len(complete) * 4,
                "unique_coarse_attempts": sum(
                    2 * (2 - len(r["exact_fit_reuse"])) for r in complete
                ),
                "stationary_unique_coarse_attempts": unique_stationary,
                "stationary_logical_coarse_attempts": sum(
                    f["converged"]
                    for r in complete
                    for fits in r["fits"].values()
                    for f in fits.values()
                ),
                "qualified_coarse_comparisons": len(comparisons),
                "lower_coarse_objective": sum(c["delta"] < -1e-6 for c in comparisons),
                "higher_coarse_objective": sum(c["delta"] > 1e-6 for c in comparisons),
                "changed_qualified_comparisons": len(changed),
                "same_bank_changed_comparisons": len(same_bank_changed),
                "same_bank_changed_lower": sum(c["delta"] < -1e-6 for c in same_bank_changed),
            }
        )
    write(PUBLIC / "protocol.json", protocol)
    write(PUBLIC / "numerical-seal.json", seal)
    sparse_path = Path(
        "/srv/bulk/leo-dev/leo-track-merge-study/reports/2026_10_12_continuous_track_merge"
        "/local/DS20/fast-43ce59233fe914e1d273ee584efcd405/baseline.json"
    )
    sparse = json.loads(sparse_path.read_bytes())["observations"]
    margin_rows = []
    for high in (False, True):
        margins = [
            m
            for m, ch in zip(sparse["margin"], sparse["channel"], strict=True)
            if (ch >= 5) == high
        ]
        margin_rows.append(
            {
                "band": "CH5-8" if high else "CH1-4",
                "rows": len(margins),
                "median": statistics.median(margins),
                "minimum": min(margins),
                "maximum": max(margins),
                "below_0_033": sum(m < 0.033 for m in margins),
            }
        )
    write(
        PUBLIC / "sparse-margin-audit.json",
        {
            "source": str(sparse_path),
            "source_sha256": sha(sparse_path),
            "rows": margin_rows,
            "likelihood_inputs": list(inspect.signature(likelihood).parameters),
            "objective_uses_margin_directly": ".margin"
            in inspect.getsource(Hard60Objective.evaluate),
            "likelihood_source_sha256": sha(Path(inspect.getfile(likelihood))),
            "reference_usage": "none",
            "scope": (
                "Posthoc known sparse regression, outside this development experiment. Fractional "
                "GLRT margins are not calibrated probabilities. They affect upstream selection "
                "and curve weights; the frozen Hard60 frequency likelihood does not consume them "
                "directly. Responsibilities still depend on residual and visibility. No weighting "
                "change, new fit or independent physical identity/RF-state inference."
            ),
        },
    )
    (PUBLIC / "results.json").write_text(
        json.dumps(
            {
                "rows": rows,
                "summary": summary,
                "script_sha256": sha(Path(__file__)),
                "reference_usage": "none",
                "scope": protocol["scope"],
            },
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for mode, color in (("original-conditioned", "#1679ac"), ("joined-conditioned", "#d87814")):
        values = [r["seconds"] for r in rows if r["budget"] == "generous" and r["mode"] == mode]
        axes[0].plot(range(len(values)), values, "o-", color=color, label=mode)
    axes[0].axhline(5, color="black", ls="--", label="Five-second allowance")
    axes[0].set(
        xlabel="Fixed recording/calibration condition",
        ylabel="Initializer time (seconds)",
        title="Serial complete nine-pass paths",
    )
    axes[0].legend(fontsize=8)
    bottom = np.zeros(2)
    for source, color in (
        ("original", "#999999"),
        ("intermediate-pass", "#1679ac"),
        ("final-pass", "#d87814"),
    ):
        values = [s["selected_sources"].get(source, 0) for s in summary]
        axes[1].bar(range(2), values, bottom=bottom, label=source, color=color)
        bottom += values
    axes[1].set_xticks(range(2), [s["budget"] for s in summary])
    axes[1].set(
        ylabel="Selected seeds (48 conditions)", title="Original and intermediate states survive"
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Profile reuse and clock incumbents · fixed development points\n"
        "Field budget interrupts 22 paths; valid saved seeds remain available"
    )
    fig.savefig(PUBLIC / "runtime-and-incumbents.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
