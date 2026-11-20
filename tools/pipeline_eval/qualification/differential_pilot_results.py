"""Package the frozen differential-pilot timing and native-gate measurements."""

import argparse
import json
from pathlib import Path

from ..__main__ import ROOT, save_json, write
from . import differential_pilot_eval as study
from . import frame_coherence_results as frame
from . import oracle_start
from .differential_pilot_confirm import held_plan
from .full_v5_check import _sha

COHORTS = ("primary", "confirmation")


def scored(case, cohort, locked, measured):
    if len(locked) != len(measured) or any(
        any(raw.get(k) != v for k, v in prior.items())
        for prior, raw in zip(locked, measured, strict=True)
    ):
        raise ValueError(f"{case} {cohort} results differ from their exact locked raw roster")
    for receipt in measured:
        row = dict(cohort=cohort, **frame.score_real(receipt))
        if row["status"] == "processed":
            ranks = receipt["measurement"]["centers"][row["receiver"]]
            distances = [oracle_start.distance(e, row["target_epoch"]) for e in ranks]
            row["raw_first_center"] = ranks[0] if ranks else None
            row["raw_first_distance"] = distances[0] if ranks else None
            row["raw_first_within_2"] = bool(distances and distances[0] <= 2)
            row["raw_nearest_rank"] = (
                min(range(len(ranks)), key=distances.__getitem__) + 1 if (ranks) else None
            )
        yield row


def rollup(subset):
    rows = [r for r in subset if r["status"] == "processed"]
    if not rows:
        raise ValueError("No admitted measurements in the locked cohort")
    flags = {k: sum(r[k] for r in rows) for k, val in rows[0].items() if isinstance(val, bool)}
    counts = {
        f"{mode}_other_{end}": sum(r[f"{mode}_other_{end}"] for r in rows)
        for mode in ("causal", "sham")
        for end in ("added", "lost")
    }
    return dict(scheduled=len(subset), n=len(rows), **flags, **counts)


def plot(document, dest):
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np
    from matplotlib import pyplot as plt

    series = (
        ("primary_miss", "Primary misses"),
        ("confirmation", "Confirmation misses"),
        ("primary_matched", "Primary retained"),
    )
    x = np.arange(len(series))
    fig, axs = plt.subplots(1, 3, figsize=(12.9, 3.85), layout="constrained")
    labels = [f"{label}\n(n={document['groups'][key]['n']})" for key, label in series]
    for ax, options, title in (
        (axs[0], ("ordinary_4_2", "raw_4_2", "sham_4_2"), "Top four within ±2 samples"),
        (axs[1], ("stock_passes", "causal_passes", "sham_passes"), "Native target passes"),
    ):
        for i, (field, label, color) in enumerate(
            zip(
                options,
                ("Wide stock", "Differential pilot", "Shifted sham"),
                ("#607283", "#007C75", "#B07728"),
                strict=True,
            )
        ):
            values = [document["groups"][key][field] for key, _ in series]
            bars = ax.bar(x + (i - 1) * 0.23, values, 0.21, label=label, color=color)
            ax.bar_label(bars, fontsize=8, padding=2)
        ax.set(title=title, xticks=x, xticklabels=labels, ylim=(0, 12), yticks=range(0, 13, 2))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_ylabel("Saved-IQ visits")
        ax.spines[["top", "right"]].set_visible(False)
    axs[0].legend(frameon=False, loc="upper left", fontsize=8, ncols=2)

    ax = axs[2]
    costs = document["whole_dual_rx_timing"]
    keys = ("stock_cpu_ms", "scout_cpu_ms", "raw_plus_native_cpu_ms")
    names = ("Wide native", "Differential scout", "Scout + hinted native")
    y = np.arange(len(keys))
    colors = ("#607283", "#007C75", "#007C75")
    bar = ax.barh(y, [costs[k]["median"] for k in keys], color=colors, height=0.40)
    ax.scatter([costs[k]["p90"] for k in keys], y, marker="|", s=100, color="#16202B")
    for patch in bar:
        value = patch.get_width()
        ax.text(
            value - 0.65,
            patch.get_y() + patch.get_height() / 2,
            f"{value:.1f}",
            color="white",
            ha="right",
            va="center",
        )
    ax.axvline(20, linestyle="--", color="#963A38", linewidth=1)
    ax.set(
        title="Primary CPU P50 and P90",
        xlabel="Host CPU time per dual-RX visit (ms)",
        xlim=(0, 42),
        yticks=y,
        yticklabels=names,
    )
    ax.tick_params(axis="y", labelsize=8)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    primary = document["groups"]["primary_miss"]["causal_passes"]
    confirmed = document["groups"]["confirmation"]["causal_passes"]
    fig.suptitle(
        f"Adjacent-symbol timing recovered {primary} primary and {confirmed} confirmation misses"
    )
    fig.savefig(dest / "stage.png", dpi=155)
    fig.savefig(dest / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    dest = study.REPORT
    primary, _ = study.bind(work)
    held_file, held = held_plan(work, primary)
    continuation_file = work / "confirmation-execution.json"
    proof = json.loads(continuation_file.read_bytes())
    if proof["plan_sha256"] != _sha(held_file) or proof["source_sha256"] != _sha(
        ROOT / proof["source"]
    ):
        raise ValueError("Confirmation execution differs from frozen code or input")
    files = [held_file.name, continuation_file.name, "controls.json.gz"]
    stages, real = [], []
    for cohort, plan in zip(COHORTS, (primary, held), strict=True):
        suffix = "" if cohort == "primary" else "-confirmation"
        for case, roster in plan["cases"].items():
            if not roster:
                continue
            name = f"{case}{suffix}.json.gz"
            raw = frame.capture(work, name)
            stages.extend(scored(case, cohort, roster, raw))
            files.append(name)
            if cohort == "primary":
                real.extend(raw)
    controls = frame.capture(work, "controls.json.gz")
    synth = [
        r for name, assembly in controls.items() for r in frame.score_synthetic(name, assembly)
    ]
    first = [r for r in stages if r["cohort"] == "primary"]
    info = frame.summary(real, first, synth, controls)
    groups = {
        f"primary_{s}": rollup([r for r in first if r["kind"] == s]) for s in ("miss", "matched")
    }
    groups["confirmation"] = rollup([r for r in stages if r["cohort"] == "confirmation"])
    info["groups"] = groups
    info["confirmation_trigger"] = dict(gated_misses=2, matched_targets_retained=7)
    info["timing_note"] = (
        "Warm host calls on CPU4, nice10, concurrent host load; excludes IQ reads."
    )
    info["confirmation_targets"] = [
        {key: r[key] for key in ("case", "visit", "receiver", "causal_cfo_delta_hz")}
        for r in stages
        if (r["cohort"] == "confirmation" and r.get("causal_physical_passes"))
    ]

    for name in files:
        write(dest / name, (work / name).read_bytes())
    save_json(dest / "qualification.json", info)
    frame.write_csv(dest / "stage.csv", stages)
    frame.write_csv(dest / "controls.csv", synth)
    plot(info, dest)
    save_json(
        dest / "stage-figure.json",
        dict(
            version=1,
            id="differential-pilot",
            title="Adjacent-symbol differential pilot timing",
            sample="24 primary plus 8 disjoint dual-RX visits from four recordings",
            boundary="Saved CI16 → 44-sample differential code → native wide fractional gate",
            note="Recovered 5/16 primary and 2/8 confirmation misses. Position unmeasured.",
            seal="prediction-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    files.extend(
        (
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
    evidence = (Path(__file__), ROOT / "tests/pipeline_eval/test_differential_pilot.py")
    save_json(
        dest / "prediction-lock.json",
        dict(
            cases=study.CASES,
            files={name: _sha(dest / name) for name in sorted(files)},
            sources={str(p.relative_to(ROOT)): _sha(p) for p in evidence},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=study.WORK)
    publish(parser.parse_args().work)
