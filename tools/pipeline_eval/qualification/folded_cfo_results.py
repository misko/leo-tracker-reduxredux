"""Publish reproducible stage evidence from the frozen folded-CFO trial."""

import argparse
import json
from pathlib import Path

from ..__main__ import ROOT, encoded, save_json, write
from . import factor_cross, oracle_start
from . import folded_cfo_eval as study
from . import frame_coherence_results as common
from .full_v5_check import _from_native, _sha, compare_probes

ARMS = ("stock", "hinted", "phase", "sham")
MEASURES = ("grid_cells", "anchor_bins", "complex_taps")


def score_real(records):
    for row in records:
        rec = {
            k: row[k]
            for k in ("case", "visit", "receiver", "kind", "stratum", "status", "iq_sha256")
        }
        if row["status"] != "processed":
            yield dict(rec, reason=row["reason"])
            continue
        lane, result = row["receiver"], row["result"]
        rec.update(
            hint_epoch=result["hints"][lane], folded_phase_hz=result["phases"]["phase"][lane]
        )
        for arm, doc in row["outcomes"].items():
            rec.update({f"{arm}_{key}": value for key, value in doc.items()})
        for arm, counts in result["counts"].items():
            rec.update({f"{arm}_{metric}": sum(c[metric] for c in counts) for metric in MEASURES})
        for arm in ("phase", "sham"):
            left, right = (result["probes"][mode][lane] for mode in ("hinted", arm))
            comparison = compare_probes(left, right, study.dp.RATE)
            rec[f"{arm}_lost"] = comparison["production_only"]
            rec[f"{arm}_added"] = comparison["native_only"]
            rec[f"{arm}_payload_changed"] = encoded(result["payloads"]["hinted"]) != encoded(
                result["payloads"][arm]
            )
        yield rec


def score_controls(controls):
    for name, row in controls.items():
        plant, result = row["target"], row["result"]
        target = {
            "integer_epoch_sample": plant["epoch"],
            "fractional_epoch_offset_samples": 0,
            factor_cross.CFO: plant["cfo_hz"],
        }
        for rx in (0, 1):
            receipt = dict(
                control=name,
                receiver=rx,
                iq_sha256=row["iq_sha256"],
                target_epoch=plant["epoch"],
                cfo_hz=plant["cfo_hz"],
                phase=result["phases"]["phase"][rx],
                chosen=result["hints"][rx],
            )
            for mode in ARMS:
                candidates = result["payloads"][mode]["rows"][rx]["candidates"]
                factors = (_from_native(i, c) for i, c in enumerate(candidates))
                positive = [c for c in factors if c and c[factor_cross.GATE]]
                receipt[f"{mode}_gated"] = len(positive)
                receipt[f"{mode}_target"] = (
                    any(oracle_start.target_matches(c, target, exact_cfo=True) for c in positive)
                    if plant["plant"]
                    else None
                )
            yield receipt


def summarize(rows, records, controls):
    observed = [r for r in rows if r["status"] == "processed"]
    groups = {}
    for kind in ("miss", "matched"):
        group = [r for r in observed if r["kind"] == kind]
        groups[kind] = dict(
            n=len(group),
            **{
                f"{arm}_{key}": sum(r[f"{arm}_{key}"] for r in group)
                for arm in ARMS
                for key in ("passes", "physical_passes", "winner", "physical_winner")
            },
        )
    counts = {
        f"{m}_{k}": sum(r[f"{m}_{k}"] for r in observed)
        for m in ("off", "phase", "sham")
        for k in MEASURES
    }
    changes = {
        f"{m}_{k}": sum(r[f"{m}_{k}"] for r in observed)
        for m in ("phase", "sham")
        for k in ("payload_changed", "lost", "added")
    }
    measures = {arm: eval_times(records, arm) for arm in study.MODES}
    return dict(
        n=len(observed),
        scheduled=len(rows),
        position_attempted=False,
        groups=groups,
        coarse_work=counts,
        changed_candidate_outcomes=changes,
        timings_ms=measures,
        controls=controls,
    )


def eval_times(records, arm):
    keys = (
        "native_cpu",
        "native_wall",
        "coarse",
        "scout_plus_native_cpu",
        "scout_plus_native_wall",
    )
    tracks = {k: [] for k in keys}
    for row in records:
        if row["status"] != "processed":
            continue
        result = row["result"]
        for native, scout in zip(result["timings"][arm], result["phase_times"], strict=True):
            tracks["coarse"].append(sum(native["coarse_ms"]))
            for scope in ("cpu", "wall"):
                clock = f"{scope}_ns"
                tracks[f"native_{scope}"].append(native[clock] / 1e6)
                tracks[f"scout_plus_native_{scope}"].append((native[clock] + scout[clock]) / 1e6)
    return {name: common.describe(values) for name, values in tracks.items()}


def plot(data):
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), layout="constrained")
    groups = data["groups"]
    labels = ("Stock wide", "Unpruned timing", "Measured phase", "Phase sham")
    colors = ("#8A9299", "#52677D", "#007B6E", "#BA752A")
    positions = np.arange(len(ARMS))
    for ax, kind, heading in zip(
        axes[:2],
        ("miss", "matched"),
        ("Missed archive positives", "Retained archive controls"),
        strict=True,
    ):
        count = groups[kind]["n"]
        y = [groups[kind][f"{a}_passes"] for a in ARMS]
        bars = ax.bar(positions, y, color=colors, width=0.65)
        ax.bar_label(bars, fontsize=9, padding=2)
        ax.set(
            title=f"{heading} (n={count})",
            ylabel="Native target passes",
            xticks=positions,
            xticklabels=[label.replace(" ", "\n", 1) for label in labels],
            ylim=(0, max(y) + 1.2),
        )
        ax.tick_params(axis="x", labelsize=8)
    cost = data["timings_ms"]
    ax = axes[-1]
    keys = ("hinted", "phase", "sham")
    total = [cost[m]["scout_plus_native_cpu"]["median"] for m in keys]
    bars = ax.barh(np.arange(3), total, color=colors[1:], height=0.52)
    ax.bar_label(bars, fmt="%.2f", fontsize=9, padding=3)
    ax.axvline(20, color="#8A4B3F", linewidth=1, linestyle="--")
    ax.set(
        title="Dual-RX P50 CPU",
        xlabel="Scout plus detector (ms)",
        xlim=(0, 34),
        yticks=np.arange(3),
        yticklabels=labels[1:],
    )
    ax.invert_yaxis()
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    before, after = (data["coarse_work"][f"{m}_complex_taps"] for m in ("off", "phase"))
    fig.suptitle(
        f"Folded phase saved {100 * (1 - after / before):.1f}% of coarse tap work on 16 visits"
    )
    fig.savefig(study.REPORT / "stage.png", dpi=155)
    fig.savefig(study.REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    plan, paths = study.bind(work)
    records = []
    names = ["build-lock.json", "controls.json.gz"]
    for ident, locked in plan["cases"].items():
        name = f"{ident}.json.gz"
        observed = common.capture(work, name)
        if len(observed) != len(locked) or any(
            any(r.get(k) != v for k, v in p.items()) for r, p in zip(observed, locked, strict=True)
        ):
            raise ValueError("Result roster differs from its raw input seal")
        records.extend(observed)
        names.append(name)
    rows = list(score_real(records))
    synth = list(score_controls(common.capture(work, "controls.json.gz")))
    data = summarize(rows, records, synth)
    dest = study.REPORT
    for name in names:
        write(dest / name, (work / name).read_bytes())
    receipt = Path(paths["band"]).parent / "build-receipt.json"
    if _sha(receipt) != json.loads((work / "build-lock.json").read_bytes())["recipe_sha256"]:
        raise ValueError("Compiler receipt changed")
    write(dest / "build-receipt.json", receipt.read_bytes())
    save_json(dest / "qualification.json", data)
    common.write_csv(dest / "stage.csv", rows)
    common.write_csv(dest / "controls.csv", synth)
    plot(data)
    save_json(
        dest / "stage-figure.json",
        dict(
            version=1,
            id="folded-cfo",
            title="Modulo CFO screening on a new differential hint",
            sample="16 independent saved dual-RX visits and 14 signed, weak and null controls",
            boundary="Exact raw timing → folded phase candidate mask → native wide fractional GLRT",
            note="Phase skipped 2.6% of the coarse tap work. No end-to-end CPU or recall gain.",
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
            "input-lock.json.gz",
            "qualification.json",
            "stage.csv",
            "controls.csv",
            "stage.png",
            "stage.pdf",
            "stage-figure.json",
        )
    )
    src = (Path(__file__), *(ROOT / "tests/pipeline_eval").glob("test_folded_cfo*"))
    save_json(
        dest / "prediction-lock.json",
        dict(
            cases=study.timing.CASES,
            sources={str(p.relative_to(ROOT)): _sha(p) for p in src},
            files={name: _sha(dest / name) for name in sorted(names)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=study.WORK)
    publish(parser.parse_args().work)
