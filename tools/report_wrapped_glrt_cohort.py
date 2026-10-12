"""Publish compact inventory and measured development diagnostics, retaining failures."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import (
    PILOT_ALIAS_HZ,
    WrappedConfig,
    circular,
    nuisance_design,
    wrapped_ratios,
)
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import (
    load_bundle,
    load_phase_bank,
    phase_provider,
    predictions,
)


def metrics(data, prediction, opportunity, rf, fit, config):
    design, _, _ = nuisance_design(data, rf, coefficient=fit["coefficient_enabled"])
    ratio = wrapped_ratios(
        data,
        prediction[:, fit["active"]],
        opportunity[:, fit["active"]],
        design,
        fit["beta"],
        config,
    )
    weights = np.asarray(fit["weights"])
    mixture = weights[0] + ratio @ weights[1:]
    q = data.signal_probability[:, None] * opportunity[:, fit["active"]]
    signal = weights[None, 1:] * (ratio - (1 - q)) / mixture[:, None]
    row_signal = signal.sum(axis=1)
    strong = data.signal_probability >= 0.95 - 1e-9
    if not np.isclose(np.mean(1 - row_signal), fit["effective_background"], atol=1e-8):
        raise ValueError("reported responsibility mass does not reproduce endpoint fit")
    by_group = {}
    for group in range(int(data.group.max()) + 1):
        mask = (data.group == group) & strong
        by_group[str(group)] = dict(
            strong_count=int(mask.sum()),
            conditional_strong_signal_fraction=float(np.mean(row_signal[mask]))
            if mask.any()
            else None,
        )
    return dict(
        factors=len(data.ids),
        strong_factors=int(strong.sum()),
        conditional_signal_mass=float(row_signal.sum()),
        strong_signal_fraction=float(np.mean(row_signal[strong])),
        by_receiver_band=by_group,
        posterior_background_fraction=float(np.mean(1 - row_signal)),
        score=fit["score"],
        satellites=len(fit["active"]),
        offsets_hz=fit["offsets_hz"],
        drift_hz_s=fit["drift_hz_s"],
        coefficient_hz_ghz=fit["coefficient_hz_ghz"],
        phase_s=fit.get("phase_s", 0),
        converged=fit["converged"],
        scope="conditional frequency fit; no position accuracy inference from this score",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    panel = json.loads((args.data_root / "panel.json").read_text())
    write_json(args.output / "panel.json", panel)
    session = "fast-bf660cb5200c4a27c3a2181a6dfc7132"
    root = args.data_root / session
    data, bank, meta, receipt = load_bundle(root / "bundle")
    cases = {
        "histogram": "reference-v1",
        "track-shape": "reference-shape-v1",
        "shared-orbit-phase": "reference-phase-v1",
    }
    summaries = []
    results = {}
    for name, directory in cases.items():
        result = json.loads((root / directory / "result.json").read_text())
        if (
            result["input_digest"] != meta["input_sha256"]
            or result["orbit_digest"] != meta["orbit_bank_sha256"]
        ):
            raise ValueError("endpoint receipts are not bound to the plotted scan")
        results[name] = result
        write_json(args.output / (name + "-result.json"), result)
        config = WrappedConfig(**result["config"])
        for arm, fit in result["reference"]["arms"].items():
            if name == "shared-orbit-phase":
                phase_bank, _ = load_phase_bank(root / "bundle", bank)
                provider = phase_provider(phase_bank, bank, data, meta["site"], (0, 0))
                pred, opp, _, _ = provider.predict(fit.get("phase_s", 0))
            else:
                pred, opp = predictions(bank, meta["site"], (0, 0))
            row = metrics(data, pred, opp, bank["rf_hz"], fit, config)
            row.update(case=name, arm=arm)
            summaries.append(row)
    write_json(
        args.output / "development-comparison.json",
        dict(
            session_id=session,
            evidence_receipt=receipt,
            rows=summaries,
            site=meta["site"],
            position_error_evaluated=False,
            validation_scans_evaluated=False,
            status="accuracy goal remains active; insufficient explained strong evidence",
        ),
    )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    ordered = panel["rows"][::-1]
    labels = []
    for row in ordered:
        parts = row["recording_name"].split("-")
        stamp = datetime.strptime(parts[2] + parts[3], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        labels.append(
            stamp.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%H:%M")
            + ("\nU" if parts[-1] == "upper" else "\nL")
        )
    x = np.arange(len(ordered))
    axes[0].bar(x, [r["counts"]["processed"] for r in ordered], label="GLRT completed")
    axes[0].bar(
        x,
        [r["counts"]["skipped_fast_score"] for r in ordered],
        bottom=[r["counts"]["processed"] for r in ordered],
        label="Fast gate skipped",
        color="silver",
    )
    axes[0].set(
        xticks=x,
        xticklabels=labels,
        ylabel="Capture windows",
        title="Frozen six-scan inventory (Oct 12, PDT capture labels)",
    )
    axes[0].legend(fontsize=8)
    for i, row in enumerate(ordered):
        axes[0].text(i, 100, row["split"][:3], ha="center", color="white", fontsize=8)
    names = list(cases)
    for arm, offset, color in (("zero-c", -0.17, "steelblue"), ("fitted-c", 0.17, "darkorange")):
        values = [
            next(r for r in summaries if r["case"] == name and r["arm"] == arm) for name in names
        ]
        axes[1].bar(
            np.arange(3) + offset,
            [100 * r["strong_signal_fraction"] for r in values],
            width=0.32,
            label=arm,
            color=color,
        )
    axes[1].set(
        xticks=np.arange(3),
        xticklabels=[
            "Histogram\nstarts",
            "Measured-track\nshape starts",
            "Shared orbit\nphase nuisance",
        ],
        ylabel="Conditional signal mass on strong GLRT (%)",
        ylim=(0, 100),
        title="Development scan: explanation of strong evidence",
    )
    axes[1].legend(fontsize=8)
    fig.savefig(args.output / "inventory-and-evidence.png", dpi=170)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    for arm, offset, color in (("zero-c", -0.17, "steelblue"), ("fitted-c", 0.17, "darkorange")):
        values = [
            next(r for r in summaries if r["case"] == name and r["arm"] == arm) for name in names
        ]
        ax.bar(
            np.arange(3) + offset, [r["score"] for r in values], width=0.32, label=arm, color=color
        )
    ax.set(
        xticks=np.arange(3),
        xticklabels=names,
        ylabel="Penalized composite log ratio",
        title="Same development evidence at configured Sausalito reference",
    )
    ax.legend()
    fig.savefig(args.output / "frequency-score-comparison.png", dpi=170)
    plt.close(fig)

    fit = results["shared-orbit-phase"]["reference"]["arms"]["fitted-c"]
    phase_bank, _ = load_phase_bank(root / "bundle", bank)
    provider = phase_provider(phase_bank, bank, data, meta["site"], (0, 0))
    pred, opp, _, _ = provider.predict(fit["phase_s"])
    design, _, _ = nuisance_design(data, bank["rf_hz"], coefficient=True)
    means = pred + (design @ np.array(fit["beta"]))[:, None]
    strongest = data.frequency_hz[np.arange(len(data.ids)), data.candidate_weight.argmax(axis=1)]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, constrained_layout=True)
    for group, ax in enumerate(axes.flat):
        rows = np.flatnonzero(data.group == group)
        rows = rows[np.argsort(data.time_s[rows])]
        strong = data.signal_probability[rows] >= 0.95 - 1e-9
        ax.scatter(data.time_s[rows], circular(strongest[rows]) / 1000, s=3, color="silver")
        ax.scatter(
            data.time_s[rows[strong]],
            circular(strongest[rows[strong]]) / 1000,
            s=5,
            color="black",
            alpha=0.6,
        )
        for sat, norad in zip(fit["active"], fit["norad"], strict=True):
            frequency = circular(means[rows, sat])
            valid = opp[rows, sat] > 0
            frequency = np.where(valid, frequency, np.nan)
            jumps = np.flatnonzero(np.abs(np.diff(frequency)) > PILOT_ALIAS_HZ / 2) + 1
            frequency[jumps] = np.nan
            ax.plot(data.time_s[rows], frequency / 1000, linewidth=1, label=str(norad))
        ax.set(
            title=f"RX{group // 2} / CH{('1–4' if group % 2 == 0 else '5–8')}",
            ylabel="Aliased CFO (kHz)",
            xlabel="Receive time from capture anchor (s)",
            ylim=(-115, 115),
        )
    axes[0, 0].legend(fontsize=7, ncol=2)
    fig.suptitle(
        "Development diagnostic: selected orbit curves leave substantial strong GLRT unexplained"
    )
    fig.savefig(args.output / "aliased-frequency-fit.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    main()
