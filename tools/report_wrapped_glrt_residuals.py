"""Inspect conditional residual structure on development scans, without hard identities."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from leo.analysis.glrt_residual_diagnostics import signal_candidate_residuals, weighted_median
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, nuisance_design
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import load_bundle, load_phase_bank, phase_provider
from tools.report_wrapped_physical_diagnostics import paired_summary, replay_endpoint


def summarize(data, rf, residual, mass, norad):
    strong = data.signal_probability >= 0.95 - 1e-9
    bins = np.floor(data.time_s / 10).astype(int)
    rows = []
    for j, satellite in enumerate(norad):
        r, w = residual[:, :, j], mass[:, :, j]
        temporal = []
        for group in np.unique(data.group):
            for time_bin in np.unique(bins):
                mask = (data.group == group) & (bins == time_bin) & strong
                if w[mask].sum() >= 5:
                    temporal.append(
                        dict(
                            group=int(group),
                            center_s=float(10 * time_bin + 5),
                            mass=float(w[mask].sum()),
                            median_hz=weighted_median(r[mask], w[mask]),
                        )
                    )
        channel = []
        for frequency in np.unique(rf):
            mask = (rf == frequency) & strong
            if w[mask].sum() >= 5:
                channel.append(
                    dict(
                        rf_hz=float(frequency),
                        mass=float(w[mask].sum()),
                        median_hz=weighted_median(r[mask], w[mask]),
                    )
                )
        rows.append(
            dict(
                norad=int(satellite),
                signal_mass=float(w.sum()),
                strong_signal_mass=float(w[strong].sum()),
                median_hz=weighted_median(r, w),
                median_abs_hz=weighted_median(abs(r), w),
                strong_median_abs_hz=weighted_median(abs(r[strong]), w[strong]),
                temporal_bins=temporal,
                by_rf=channel,
            )
        )
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--surface-directory", default="fixed-frame-full-v2")
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    panel = json.loads((args.data_root / "panel.json").read_text())
    output = []
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for entry in panel["rows"]:
        if entry["split"] != "development":
            continue
        root = args.data_root / entry["session_id"]
        path = root / args.surface_directory / "result.json"
        result = json.loads(path.read_text())
        data, bank, meta, _ = load_bundle(root / "bundle")
        if (
            not result["completed"]
            or result["input_digest"] != meta["input_sha256"]
            or result["orbit_digest"] != meta["orbit_bank_sha256"]
        ):
            raise ValueError("completed development surface must match the source evidence")
        phases, receipt = load_phase_bank(root / "bundle", bank)
        if receipt != result["phase_receipt"]:
            raise ValueError("changed orbital phase bank")
        if result["phase_model"] != "fixed-reception-frame-orbital-phase":
            raise ValueError("declared fixed reception frame required")
        provider = phase_provider(phases, bank, data, meta["site"], (0, 0), inertial_phase=True)
        lookup = {int(n): i for i, n in enumerate(bank["norad"])}
        pool = np.asarray([lookup[n] for n in result["candidate_norad"]])
        cfg = WrappedConfig(**result["config"])
        for arm, fit in result["reference"]["arms"].items():
            active = np.asarray(fit["active"], dtype=int)
            pred, opp, _, _ = provider.predict(
                fit["phase_s"] + np.asarray(fit["satellite_phase_s"])[active],
                pool[active],
            )
            replay_endpoint(data, bank["rf_hz"], pred, opp, fit, cfg)
            if cfg.satellite_bias_sigma_hz is not None:
                pred = pred + np.asarray(fit["satellite_bias_hz"])[active][None, :]
            design, _, _ = nuisance_design(
                data,
                bank["rf_hz"],
                coefficient=fit["coefficient_enabled"],
                band_drift=cfg.band_drift_sigma_hz_s is not None,
            )
            residual, mass, clutter = signal_candidate_residuals(
                data,
                pred,
                opp,
                design,
                fit["beta"],
                cfg,
                fit["weights"],
            )
            if not np.isclose(clutter.mean(), fit["effective_background"], atol=1e-8, rtol=0):
                raise ValueError("candidate responsibilities do not reproduce the fitted mass")
            rows = summarize(data, bank["rf_hz"], residual, mass, fit["norad"])
            output.append(
                dict(
                    session=entry["session_id"],
                    split=entry["split"],
                    arm=arm,
                    input_digest=result["input_digest"],
                    orbit_digest=result["orbit_digest"],
                    surface_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    factors=len(data.ids),
                    rows=rows,
                )
            )
            count = len(rows)
            fig, axes = plt.subplots(
                int(np.ceil(count / 4)),
                4,
                figsize=(16, 3 * int(np.ceil(count / 4))),
                squeeze=False,
                constrained_layout=True,
            )
            strong = data.signal_probability >= 0.95 - 1e-9
            for j, ax in enumerate(axes.flat):
                if j >= count:
                    ax.set_visible(False)
                    continue
                for group in range(4):
                    select = ((data.group == group) & strong)[:, None] & (mass[:, :, j] >= 0.1)
                    t = np.broadcast_to(data.time_s[:, None], select.shape)
                    ax.scatter(
                        t[select], residual[:, :, j][select], s=4, alpha=0.25, color=f"C{group}"
                    )
                    medians = [b for b in rows[j]["temporal_bins"] if b["group"] == group]
                    ax.plot(
                        [b["center_s"] for b in medians],
                        [b["median_hz"] for b in medians],
                        ".",
                        linestyle="none",
                        markersize=6,
                        color=f"C{group}",
                        label=f"RX{group // 2} CH{'1–4' if group % 2 == 0 else '5–8'}",
                    )
                ax.axhline(0, color="black", lw=0.7)
                ax.set(
                    xlabel="Time (s)",
                    ylabel="Frequency residual (Hz)",
                    ylim=(-1250, 1250),
                    title=f"NORAD {rows[j]['norad']} / mass {rows[j]['strong_signal_mass']:.0f}",
                )
                if j == 0:
                    ax.legend(fontsize=6)
            fig.suptitle(
                f"{entry['session_id'][5:13]} / {arm}: conditional candidate residuals\n"
                "Strong GLRT factors; displayed candidate mass ≥0.1; "
                "10 s medians require mass ≥5. Identities remain unconfirmed."
            )
            fig.savefig(args.output / f"{entry['session_id'][5:13]}-{arm}.png", dpi=135)
            plt.close(fig)
    write_json(
        args.output / "conditional-residual-summary.json",
        dict(
            rows=output,
            bin_seconds=10,
            minimum_bin_signal_mass=5,
            scope="Development-only posterior diagnostics, conditional on fitted identities/marks; "
            "not independent frequency accuracy or a calibration prior",
            source_digests={
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (
                    Path(__file__),
                    Path("src/leo/analysis/glrt_residual_diagnostics.py"),
                    Path("src/leo/analysis/wrapped_glrt_likelihood.py"),
                )
            },
        ),
    )
    print(json.dumps(dict(development_scan_arms=len(output))))
    if args.surface_directory != "fixed-frame-full-v2":
        return
    audits, comparisons = [], []
    for entry in panel["rows"]:
        root = args.data_root / entry["session_id"]
        for source in sorted((root / "fixed-frame-full-catalogue-audit-v1").glob("*/result.json")):
            audit = json.loads(source.read_text())
            if not audit["completed"]:
                raise ValueError("incomplete catalogue audit cannot be summarized as completed")
            destination = args.output / entry["session_id"] / "full-catalogue" / source.parent.name
            shutil.copytree(source.parent, destination, dirs_exist_ok=True)
            audits.append(
                dict(
                    session=entry["session_id"],
                    point=source.parent.name,
                    position=audit["point"],
                    candidate_count=len(audit["candidate_norad"]),
                    arms={
                        a: dict(
                            score=f["score"],
                            gain=f["score"] - f["known_conditional_score"],
                            satellites=f["norad"],
                        )
                        for a, f in audit["arms"].items()
                    },
                )
            )
        if entry["split"] != "development":
            continue
        cases, evaluations = {}, {}
        for variant in ("restricted", "expanded"):
            folder = root / f"joint-satellite-bias-{variant}-v1"
            if not (folder / "result.json").exists():
                continue
            cases[variant] = json.loads((folder / "result.json").read_text())
            if not cases[variant]["completed"]:
                raise ValueError("incomplete joint-bias probe")
            evaluations[variant] = [
                json.loads(line) for line in (folder / "evaluations.jsonl").read_text().splitlines()
            ]
            shutil.copytree(
                folder, args.output / entry["session_id"] / folder.name, dirs_exist_ok=True
            )
        if len(cases) == 2:
            comparisons.extend(
                dict(row, session=entry["session_id"])
                for row in paired_summary(
                    cases["restricted"],
                    cases["expanded"],
                    evaluations["restricted"],
                    evaluations["expanded"],
                    changed_config_keys=("satellite_bias_sigma_hz",),
                )
            )
    write_json(args.output / "full-catalogue-audit-summary.json", dict(rows=audits))
    write_json(args.output / "joint-bias-paired-summary.json", dict(rows=comparisons))
    protocol = args.data_root / "joint-satellite-bias-development-protocol.json"
    if protocol.exists():
        shutil.copyfile(protocol, args.output / protocol.name)
    if comparisons:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
        for j, arm in enumerate(("zero-c", "fitted-c")):
            rows = [r for r in comparisons if r["arm"] == arm]
            x = np.arange(len(rows)) + (j - 0.5) * 0.35
            axes[0].bar(x, [r["reference_gain"] for r in rows], 0.35, label=arm)
            axes[1].bar(
                x,
                [r["alternative_reference_gap"] - r["base_reference_gap"] for r in rows],
                0.35,
                label=arm,
            )
        for ax in axes:
            ax.set_xticks(np.arange(len(rows)), [r["session"][5:13] for r in rows])
            ax.axhline(0, color="black", lw=0.7)
            ax.legend()
        axes[0].set(title="Reference frequency-score gain", ylabel="Expanded minus restricted")
        axes[1].set(
            title="Reference gap on identical probes",
            ylabel="Expanded gap minus restricted gap (lower better)",
        )
        fig.savefig(args.output / "joint-bias-frequency-and-position.png", dpi=160)
        plt.close(fig)
    for path in args.output.rglob("*.json"):
        path.write_text(
            json.dumps(json.loads(path.read_text()), separators=(",", ":"), allow_nan=False) + "\n"
        )


if __name__ == "__main__":
    main()
