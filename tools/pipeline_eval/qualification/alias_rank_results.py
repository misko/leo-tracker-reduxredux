"""Collect sealed alias-ranking, native retention and timing evidence for the stage gallery."""

import argparse
import json
from pathlib import Path

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from . import alias_rank_trial as study
from . import factor_cross, oracle_start
from . import frame_coherence_results as common
from .full_v5_check import _from_native, _sha, compare_probes

ARMS = ("stock", "hinted", "gated", "forced")
COUNTS = ("grid_cells", "anchor_bins", "complex_taps")


def estimate_rows(estimates, epoch, frequency):
    for a in estimates:
        row = dict(rank=a["rank"], proposed_epoch=a["epoch"], folded_hz=a["folded_hz"])
        if epoch is not None:
            row["epoch_error_samples"] = oracle_start.distance(a["epoch"], epoch)
            row["aligned"] = row["epoch_error_samples"] <= 2
        evidence = a["coherent"]
        prior = a["simple"]
        if evidence:
            opts = evidence["options"]
            row.update(
                alias_evidence_pass=evidence["confirmed"],
                exact_block_count=evidence["valid_blocks"],
                best_coherent_cfo=opts[0]["cfo_hz"],
                coherent_evidence=opts[0]["pooled"],
            )
            if frequency is not None:
                recalled = [abs(c["alias_hz"] - frequency) <= study.rank.PERIOD / 2 for c in opts]
                row.update(
                    coherent_top1=recalled[0],
                    coherent_top2=any(recalled[:2]),
                    coherent_absolute_error_hz=abs(opts[0]["cfo_hz"] - frequency),
                )
        if prior:
            row["best_short_lag_cfo"] = prior["absolute_hz"]
            if frequency is not None:
                phase = prior["folded_hz"] * 2 * np.pi / study.rank.PERIOD
                opts = study.pilot_carrier.frequency_options(phase, study.rank.dp.LAG)
                opts = sorted(opts, key=lambda hz: abs(hz - prior["short_hz"]))
                recalled = [abs(hz - frequency) <= study.rank.PERIOD / 2 for hz in opts]
                row.update(
                    short_lag_top1=recalled[0],
                    short_lag_top2=any(recalled[:2]),
                    short_lag_absolute_error_hz=abs(opts[0] - frequency),
                )
        for m in ("coherent", "short_lag"):
            key = f"{m}_absolute_error_hz"
            if key in row:
                row[f"{m}_within_40k"] = row[key] <= 40_000
                cfo = row["best_coherent_cfo" if m == "coherent" else "best_short_lag_cfo"]
                row[f"{m}_nearest_grid_bin"] = round(cfo / 80_000) == round(frequency / 80_000)
        yield row


def native_row(raw):
    row = {
        k: raw[k] for k in ("case", "visit", "receiver", "kind", "stratum", "status", "iq_sha256")
    }
    if raw["status"] != "processed":
        return dict(row, reason=raw["reason"])
    lane = raw["receiver"]
    result = raw["result"]
    row.update(
        {f"{mode}_{key}": value for mode, d in raw["outcomes"].items() for key, value in d.items()}
    )
    reference = result["probes"]["hinted"][lane]
    for mode in ("off", "gated", "forced"):
        cells = result["traces"][mode]
        row.update({f"{mode}_{k}": sum(r[k] for r in cells) for k in COUNTS})
        row[f"{mode}_mask_applied"] = cells != result["traces"]["off"]
        row[f"{mode}_payload_changed"] = encoded(result["payloads"][mode]) != encoded(
            result["payloads"]["hinted"]
        )
        change = compare_probes(reference, result["probes"][mode][lane], study.rank.dp.RATE)
        row.update(
            {f"{mode}_lost": change["production_only"], f"{mode}_added": change["native_only"]}
        )
    return row


def control_rows(controls):
    for name, raw in controls.items():
        plant, result = raw["target"], raw["result"]
        target = {
            "integer_epoch_sample": plant["epoch"],
            "fractional_epoch_offset_samples": 0,
            factor_cross.CFO: plant["cfo_hz"],
        }
        for lane, a in enumerate(result["estimates"]):
            row = dict(control=name, receiver=lane, iq_sha256=raw["iq_sha256"])
            row.update(
                next(
                    estimate_rows(
                        a[:1], plant["epoch"], plant["cfo_hz"] if (plant["plant"]) else None
                    ),
                    {},
                )
            )
            for mode in ARMS:
                candidates = result["payloads"][mode]["rows"][lane]["candidates"]
                factors = (_from_native(i, c) for i, c in enumerate(candidates))
                positives = [c for c in factors if c and c[factor_cross.GATE]]
                row[f"{mode}_gated"] = len(positives)
                row[f"{mode}_target_gate"] = (
                    any(oracle_start.target_matches(c, target, exact_cfo=True) for c in positives)
                    if plant["plant"]
                    else None
                )
            yield row


def rollup(raw, native, aliases, synth):
    ranks = {}
    for n in range(1, 5):
        group = [r for r in aliases if r["rank"] == n and r.get("aligned")]
        ranks[n] = dict(
            aligned=len(group),
            **{
                f"{m}_{k}": sum(r.get(f"{m}_{k}", False) for r in group)
                for m in ("coherent", "short_lag")
                for k in ("top1", "top2", "within_40k", "nearest_grid_bin")
            },
        )
    outcomes = {}
    for k in ("miss", "matched"):
        group = [r for r in native if r["kind"] == k and r["status"] == "processed"]
        outcomes[k] = dict(
            n=len(group),
            **{
                f"{a}_{x}": sum(r[f"{a}_{x}"] for r in group)
                for a in ARMS
                for x in ("passes", "physical_passes", "winner", "physical_winner")
            },
        )
    measured = [r for r in native if r["status"] == "processed"]
    work = {
        f"{mode}_{k}": sum(r[f"{mode}_{k}"] for r in measured)
        for mode in ("off", "gated", "forced")
        for k in (*COUNTS, "mask_applied", "payload_changed", "lost", "added")
    }
    return dict(
        visited=len(measured),
        scheduled=len(native),
        position_attempted=False,
        rank=ranks,
        native=outcomes,
        work=work,
        controls=synth,
        timings=times(raw),
    )


def times(raw):
    valid = [r for r in raw if r["status"] == "processed"]
    out = {}
    for scope in ("cpu", "wall"):
        ns = f"{scope}_ns"
        series = [r["result"]["estimates"][r["receiver"]][0]["clocks"] for r in valid]
        out[f"scorer_{scope}"] = common.describe([c[ns] / 1e6 for runs in series for c in runs])
        for mode in study.MODES:
            op, whole = [], []
            for r, clocks in zip(valid, series, strict=True):
                result = r["result"]
                for i, (n, p) in enumerate(
                    zip(result["timing"][mode], result["phase_times"], strict=True)
                ):
                    op.append(n[ns] / 1e6)
                    delta = clocks[i][ns] if mode in ("gated", "forced") else 0
                    whole.append((n[ns] + p[ns] + delta) / 1e6)
            out[f"{mode}_native_{scope}"] = common.describe(op)
            out[f"{mode}_whole_{scope}"] = common.describe(whole)
    return out


def plot(summary):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, axs = plt.subplots(1, 3, figsize=(12.6, 3.75), layout="constrained")
    x = np.arange(4)
    palettes = ("#54697B", "#00796C", "#B37237")
    for ax, rank_depth in zip(axs[:2], (1, 2), strict=True):
        for i, (k, label) in enumerate(
            (("short_lag", "4-sample lag"), ("coherent", "Coherent blocks"))
        ):
            y = [summary["rank"][r][f"{k}_top{rank_depth}"] for r in range(1, 5)]
            bars = ax.bar(x + (i - 0.5) * 0.33, y, 0.30, label=label, color=palettes[i])
            ax.bar_label(bars, padding=2, fontsize=9)
        labels = [f"Rank {r}\n(n={summary['rank'][r]['aligned']})" for r in range(1, 5)]
        ax.set(
            title=f"Correct absolute alias in top {rank_depth}",
            ylabel="Timing-aligned nominations",
            xticks=x,
            xticklabels=labels,
            ylim=(0, 5.2),
        )
    axs[0].legend(frameon=False, fontsize=8)
    work = summary["work"]
    totals = [summary["timings"][f"{m}_whole_cpu"]["median"] for m in ("hinted", "gated", "forced")]
    ax = axs[2]
    bars = ax.barh(range(3), totals, color=palettes, height=0.52)
    ax.bar_label(bars, fmt="%.2f", padding=2, fontsize=9)
    ax.set(
        title="P50 total CPU per dual-RX visit",
        xlabel="Timing + alias + native (ms)",
        yticks=range(3),
        yticklabels=["Unpruned", "Evidence-gated", "Forced"],
        xlim=(0, 60),
    )
    ax.axvline(20, linestyle="--", color="#914B43", linewidth=1)
    ax.invert_yaxis()
    for ax in axs:
        ax.spines[["top", "right"]].set_visible(False)
    save = 100 * (1 - work["gated_complex_taps"] / work["off_complex_taps"])
    fig.suptitle(
        f"Coherent alias ranking on held IQ · evidence gate saved {save:.2f}% of coarse taps"
    )
    fig.savefig(study.REPORT / "stage.png", dpi=155)
    fig.savefig(study.REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    plan, paths = study.bind(work)
    raw = []
    names = ["build-lock.json", "controls.json.gz"]
    for case, old in plan["cases"].items():
        name = f"{case}.json.gz"
        records = common.capture(work, name)
        if len(records) != len(old["selected"]) or any(
            any(r.get(k) != v for k, v in p.items())
            for r, p in zip(records, old["selected"], strict=True)
        ):
            raise ValueError("Measured receiver visits differ from the preregistered roster")
        names.append(name)
        raw.extend(records)
    aliases = [
        dict(case=r["case"], visit=r["visit"], receiver=r["receiver"], kind=r["kind"], **a)
        for r in raw
        if r["status"] == "processed"
        for a in estimate_rows(
            r["result"]["estimates"][r["receiver"]],
            oracle_start.exact_epoch(r["target"]),
            r["target"][factor_cross.CFO],
        )
    ]
    native = [native_row(r) for r in raw]
    synth = list(control_rows(common.capture(work, "controls.json.gz")))
    out = study.REPORT
    for name in names:
        write(out / name, (work / name).read_bytes())
    receipt = Path(paths["candidate"]).parent / "build-receipt.json"
    if _sha(receipt) != json.loads((work / "build-lock.json").read_bytes())["recipe_sha256"]:
        raise ValueError("Native build provenance did not match")
    write(out / "build-receipt.json", receipt.read_bytes())
    data = rollup(raw, native, aliases, synth)
    save_json(out / "qualification.json", data)
    common.write_csv(out / "stage.csv", native)
    common.write_csv(out / "ranks.csv", aliases)
    common.write_csv(out / "controls.csv", synth)
    plot(data)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="alias-rank",
            title="Coherent ranking of folded CFO aliases",
            sample="16 later dual-RX held visits and 14 synthetic IQ controls",
            boundary="Blind timing and folded phase → coherent alias rank → native GLRT",
            note="Better first-rank alias recall. Forced pruning lost a gated factor.",
            seal="prediction-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    names.extend(
        (
            "build-receipt.json",
            "PROTOCOL.md",
            "README.md",
            "qualification.json",
            "input-lock.json.gz",
            "stage.csv",
            "ranks.csv",
            "controls.csv",
            "stage.png",
            "stage.pdf",
            "stage-figure.json",
        )
    )
    src = (Path(__file__), ROOT / "tests/pipeline_eval/test_alias_rank.py")
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=study.CASES,
            files={f: _sha(out / f) for f in sorted(names)},
            sources={str(p.relative_to(ROOT)): _sha(p) for p in src},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=study.WORK)
    publish(parser.parse_args().work)
