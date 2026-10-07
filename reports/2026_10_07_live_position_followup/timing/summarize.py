"""Validate matched experiment receipts, plot fit/accuracy separately, summarize."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "results.json").read_text())
    rows = data["results"]
    snapshot = json.loads(
        (HERE.parent.parent / "2026_10_07_live_position_review" / "snapshot.json").read_text()
    )
    provenance = dict(
        protocol=(
            "All archived basins; two archived V16 fitted-c final vectors per "
            "basin, associated and zero-timing, identical across .15/1 "
            "relative sigma and zero/fitted c; shared fitted-c frozen "
            "calibration and association"
        ),
        fit_seconds=5,
        fit_iterations=300,
        common_sigma_s=3,
        source_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob("*.py")
        },
        cases=[],
    )
    for r in snapshot["regional"]:
        if r["session"] in {x["session"] for x in rows}:
            from leo.storage.regional_position import RegionalPositionStore

            doc = (
                RegionalPositionStore(Path("/srv/bulk/leo"))
                .status(r["session"])
                .manifest.document.model_dump(mode="json")
            )
            provenance["cases"].append(
                dict(
                    session=r["session"],
                    input_manifest_sha256=doc["input_manifest_sha256"],
                    analysis_manifest_sha256=doc["analysis_manifest_sha256"],
                    configuration_sha256=doc["configuration_sha256"],
                    snapshot_sha256=doc["diagnostics"]["snapshot_sha256"],
                    checkpoint_binding=doc["diagnostics"]["checkpoint_binding"],
                )
            )
            expected = {
                (f["basin"], "fitted-c:" + f["start"])
                for f in doc["diagnostics"]["final_starts"]
                if f["method"] == "V16" and f["arm"] == "fitted-c" and f["fit"]
            }
            for sigma in (0.15, 1.0):
                for arm in ("zero-c", "fitted-c"):
                    actual = {
                        (x["basin"], x["start"])
                        for x in rows
                        if x["session"] == r["session"]
                        and x["relative_sigma_s"] == sigma
                        and x["arm"] == arm
                    }
                    assert actual == expected, (r["session"], sigma, arm, "incomplete archive pool")
    provenance["executed_source_note"] = (
        "Primary run.py matches final source; inputs.py was imported "
        "before extra explicit receipt/evidence assertions were added. "
        "source_snapshots/inputs_executed.py.txt reconstructs executed helper "
        "and matches independently captured "
        "ca88998f45e802def08c2ce0f0640029a4720c2956da49e37b3167f98e9a727a. "
        "Added provenance assertions execute during separate repricing, "
        "never change numerical fits."
    )
    provenance["executed_inputs_sha256"] = hashlib.sha256(
        (HERE / "source_snapshots" / "inputs_executed.py.txt").read_bytes()
    ).hexdigest()
    if (HERE / "provenance.json").exists():
        historical = json.loads((HERE / "provenance.json").read_text())
        historical["current_publication_sha256"] = provenance["source_sha256"]
        provenance = historical
    provenance["executed_source_note"] = provenance["executed_source_note"].replace(
        "source_snapshots/inputs_executed.py reconstructs",
        "source_snapshots/inputs_executed.py.txt reconstructs",
    )
    provenance["publication_source_note"] = (
        "Current Python files received publication-only lint/format edits. "
        "Historical source_sha256 values remain unchanged; exact preformat sources are "
        "archived in ../source_snapshots/timing/*.py.txt. Numerical receipts remain unchanged."
    )
    (HERE / "provenance.json").write_text(json.dumps(provenance, indent=2))
    groups = {}
    for r in rows:
        groups.setdefault((r["session"], r["relative_sigma_s"], r["arm"]), []).append(r)
    assert len(groups) == 8
    for session in sorted({r["session"] for r in rows}):
        pools = []
        for sigma in (0.15, 1.0):
            for arm in ("zero-c", "fitted-c"):
                group = groups[session, sigma, arm]
                pools.append({(r["basin"], r["start"], tuple(r["bank"])) for r in group})
                assert all(r["common_sigma_s"] == 3 for r in group)
                if arm == "zero-c":
                    assert all(r["c_hz"] == 0 for r in group)
                for r in group:
                    v = np.array(r["fit"]["vector"])
                    np.testing.assert_allclose(
                        r["timing_penalty"],
                        0.5 * (v[7] / 3) ** 2 + 0.5 * np.sum(v[8:] ** 2) / sigma**2,
                    )
                    np.testing.assert_allclose(
                        r["score"], r["data_nll"] + r["timing_penalty"] + r["calibration_penalty"]
                    )
        assert all(p == pools[0] for p in pools)
    winners = [min(g, key=lambda r: r["score"]) for _, g in sorted(groups.items())]
    (HERE / "winners.json").write_text(json.dumps(winners, indent=2))
    fig, axes = plt.subplots(1, 3, figsize=(15, 6), layout="constrained")
    labels = []
    capture_times = {r["session"]: r["start_utc"][11:19] + " UTC" for r in snapshot["regional"]}
    for i, w in enumerate(winners):
        labels.append(
            w["session"][-4:]
            + " / "
            + capture_times[w["session"]]
            + "\n"
            + str(w["relative_sigma_s"])
            + " s / "
            + w["arm"]
        )
        for ax, key, scale in zip(
            axes, ("error_m", "data_nll", "timing_penalty"), (1000, 1, 1), strict=True
        ):
            ax.bar(
                i,
                w[key] / scale,
                color="#3465a4" if w["arm"] == "fitted-c" else "#b97736",
                edgecolor="#222222",
                linewidth=0.7,
                hatch="///" if not w["fit"]["converged"] else None,
            )
    axes[0].set_yscale("log")
    axes[0].set_ylim(1, 500)
    for ax, title in zip(
        axes, ("Position error (km)", "Frequency data NLL", "Timing penalty"), strict=True
    ):
        ax.set_title(title)
        ax.set_xticks(range(len(labels)), labels, rotation=65, ha="right", fontsize=8)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Archived V16 timing sensitivity — score-selected warm-start "
        "fits\nRelative timing sigma varies; common timing sigma remains 3 "
        "s",
        fontsize=13,
    )
    fig.legend(
        handles=[
            Patch(facecolor="#3465a4", label="Fitted c"),
            Patch(facecolor="#b97736", label="c = 0"),
            Patch(
                facecolor="white",
                edgecolor="#222222",
                hatch="///",
                label="Nonconverged (KKT > 0.001)",
            ),
        ],
        loc="outside lower center",
        ncol=3,
        frameon=False,
    )
    fig.savefig(HERE / "timing_ablation.png", dpi=170)
    fig.savefig(HERE / "timing_ablation.pdf")
    plt.close(fig)
    lines = [
        "# Controlled timing-prior refits",
        "",
        "Read-only archived-snapshot experiment, two catastrophic scans. "
        "All archived basins are retained. The two published V16 fitted-c "
        "final vectors (associated and zero-timing) form the identical "
        "fixed, score-independent seed pool for every timing variant and "
        "RF arm. Seeds depend on the original full-data fitted-c fit; this "
        "is a bounded warm-start sensitivity experiment, not an "
        "independent localization validation.",
        "",
        "Only relative timing sigma changes (.15 to 1 s); common sigma "
        "stays 3 s, sigma_hz=125, detection budget=1.6, clutter=.5. "
        "Original observations, satellite bank, receiver correction, "
        "prior, calibration penalties and local basin disks stay fixed. "
        "Each fit has 5 s and 300 iteration caps; score winners include "
        "unconverged fits, matching the published selection rule.",
        "",
        "| Scan | Relative sigma | c arm | Winner basin | Error km | Total "
        "score | Data NLL | Timing penalty | RMS Hz | KKT | Converged |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for w in winners:
        f = w["fit"]
        lines.append(
            f"| {w['session'][-16:]} | {w['relative_sigma_s']} | {w['arm']} | "
            f"{w['basin']} | {w['error_m'] / 1000:.3f} | {w['score']:.3f} | "
            f"{w['data_nll']:.3f} | {w['timing_penalty']:.3f} | "
            f"{f['posterior_rms_hz']:.2f} | {f['stationarity']:.3g} | "
            f"{f['converged']} |"
        )
    lines += [
        "",
        f"Validation: {len(data['parity'])} archived objective values "
        f"reproduced to 1e-6; analytic timing-only objective/gradient "
        f"differences checked on every fitting seed before optimization. "
        f"Receipt checks verify identical basin/start/bank pools across all "
        f"arms, exact c=0, fixed common timing sigma, and additive score "
        f"decomposition. {len(rows)} fits; elapsed {data['elapsed_s']:.1f} "
        f"s including source reconstruction.",
        "",
        "Accuracy is evaluated only after fitting, separately from "
        "frequency NLL and posterior RMS. A lower penalized score or "
        "in-sample RMS does not establish improved localization. "
        "Time-limited, nonstationary winners are provisional. No services, "
        "deployments, RF collection, QNAP data, or golden scientific "
        "fixtures changed.",
    ]
    lines += [
        "",
        "The first scan published zero-c result was near (~5.20 km), "
        "whereas the primary zero-c control selects the far basin (~296.81 "
        "km). This discrepancy exposes dependence on the fitted-c-only "
        "warm-start pool; the primary zero-c result does not reproduce the "
        "published zero-c optimization. All-arm archived fixed-state "
        "repricing below isolates the omitted seed-state sensitivity "
        "without additional optimization.",
    ]
    if (HERE / "repricing.json").exists():
        repricing = json.loads((HERE / "repricing.json").read_text())
        lines += [
            "",
            "Fixed-state repricing uses all archived V16 final vectors from "
            "both RF arms, projecting c exactly to zero for the zero-c arm. "
            "Same full pool across all four variants; no optimizer, so these "
            "are alternative-state score comparisons, not refits.",
            "",
            "| Scan | Relative sigma | c arm | Winning source arm | Basin | Error km | Score |",
            "|---|---:|---|---|---|---:|---:|",
        ]
        for w in repricing["winners"]:
            lines.append(
                f"| {w['session'][-16:]} | {w['relative_sigma_s']} | {w['arm']} | "
                f"{w['source_arm']} | {w['basin']} | {w['error_m'] / 1000:.3f} | "
                f"{w['score']:.3f} |"
            )
        lines += [
            "",
            "For the first scan, the archived zero-c near state is feasible "
            "for fitted-c as well and scores 44111.833 under the original .15 "
            "s V16 objective, beating the published far fitted-c state "
            "(44170.238). This directly identifies a start/optimization "
            "selection limitation even without loosening timing. For the "
            "second scan, original fitted-c fixed-state repricing still favors "
            "the far basin; relaxing timing shifts both RF arms to the near "
            "basin. The timing sensitivity and first-case seed sensitivity are "
            "distinct observations.",
        ]
        lines += [
            "",
            "Repricing also executes the strengthened input/analysis manifest "
            "and composite window/snapshot/candidate evidence assertions added "
            "after primary imports. Exact executed helper snapshot and current "
            "verification source hashes are distinguished in provenance.json.",
        ]
    lines += [
        "",
        "Exact executed helper bytes: source_snapshots/inputs_executed.py.txt. "
        "Publication formatting hashes are separate from historical hashes in provenance.json.",
    ]
    (HERE / "findings.md").write_text("\n".join(lines) + "\n")
    print("matched receipt tests passed", len(rows))


if __name__ == "__main__":
    main()
