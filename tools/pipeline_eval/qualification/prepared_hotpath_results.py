"""Publish complete detector parity, paired timings, and diagnostic stages."""

import argparse
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib

from ..__main__ import save_json, write
from ..variants import prepared_hotpath, prepared_hotpath_peaks
from . import prepared_hotpath_selector as selectors
from . import prepared_hotpath_trial as trial
from .capture_runtime import checked, decompress, read
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

LABELS = dict(
    prepared="Prepared",
    fine="Fine reuse",
    fine_selector="Fine + vector",
    vector="Vector selector",
    lane="Row-wise selector",
)
COLORS = dict(
    prepared="#65758a", fine="#9473a5", fine_selector="#547e7a", vector="#c3773d", lane="#087a70"
)


def spread(values):
    return dict(n=len(values), median=median(values), min=min(values), max=max(values))


def collect(work, folder, tag):
    lock = work / "input-lock.json"
    roster = read(lock)
    for path, digest in roster["sources"].items():
        checked(Path(path), digest)
    write(folder / f"{tag}-input-lock.json", lock.read_bytes())
    summary, timing, parity = {}, [], []
    for name, cfg in roster["cases"].items():
        raw = work / f"{name}.json.gz"
        source = decompress(raw)
        if source["input_lock_sha256"] != _sha(lock) or source["cpu"] != cfg["cpu"]:
            raise ValueError("detector worker did not match its authenticated setup")
        write(folder / f"{tag}-{raw.name}", raw.read_bytes())
        stacks = defaultdict(list)
        for fixture, row in zip(cfg["rows"], source["rows"], strict=True):
            if any(row[key] != fixture[key] for key in ("visit", "kind", "iq_sha256", "probes")):
                raise ValueError("completed output differs from planned archive")
            if set(row["clocks"]) != set(roster["modes"]):
                raise ValueError("receipt is missing a declared detector mode")
            clock = row["clocks"]["prepared"]
            per_visit = {}
            for mode, times in row["clocks"].items():
                if [r["repetition"] for r in times] != list(range(roster["repeats"])) or not all(
                    r["full_grid"]
                    and r["grid_calls"] >= 2
                    and r["inverse_ffts"] == reference["inverse_ffts"]
                    for r, reference in zip(times, clock, strict=True)
                ):
                    raise ValueError("repeat or full folded-kernel work differs by arm")
                if mode in ("fine", "fine_selector") and not all(
                    r["fine_calls"] > 0 and r["fine_fallbacks"] == 0 for r in times
                ):
                    raise ValueError("fine candidate did not execute the measured port")
                for data in times:
                    values = dict(
                        trial=tag,
                        case=name,
                        edge=cfg["edge"],
                        visit=row["visit"],
                        kind=row["kind"],
                        mode=mode,
                        cpu_ms=data["cpu_ns"] / 1e6,
                        wall_ms=data["wall_ns"] / 1e6,
                        **data,
                    )
                    timing.append(values)
                    stacks[mode].append(values)
                per_visit[mode] = len(times)
            public = [c for rx in row["public"]["receivers"] for c in rx["candidates"]]
            probes = [c for rx in row["probes"] for c in rx["candidates"]]
            parity.append(
                dict(
                    case=name,
                    visit=row["visit"],
                    kind=row["kind"],
                    comparisons=per_visit,
                    projected_probe_rows=len(row["probes"]),
                    public_candidates=len(public),
                    integer_pass=sum(c["passed_margin_gate"] for c in public),
                    projected_candidates=len(probes),
                    fractional_pass=sum(c["passed_fractional_margin_gate"] for c in probes),
                    closest_coarse_step_gap=min(g for g in row["rank_gaps"] if g is not None),
                    closest_fractional_gate_gap=min(
                        abs(c["fractional_margin"] - trial.GATE)
                        for c in probes
                        if c["fractional_margin"] is not None
                    ),
                    full_public_parity=True,
                    complete_projection_parity=True,
                )
            )
        runtime = {}
        for mode, rows in stacks.items():
            baseline = stacks["prepared"]
            runtime[mode] = dict(
                cpu_ms=spread([r["cpu_ms"] for r in rows]),
                wall_ms=spread([r["wall_ms"] for r in rows]),
                paired_cpu_savings_ms=spread(
                    [a["cpu_ms"] - b["cpu_ms"] for a, b in zip(baseline, rows, strict=True)]
                ),
                paired_cpu_savings_pct=100
                * median(
                    1 - b["cpu_ms"] / a["cpu_ms"] for a, b in zip(baseline, rows, strict=True)
                ),
                fine_calls=sum(r["fine_calls"] for r in rows),
                inverse_ffts=sum(r["inverse_ffts"] for r in rows),
            )
        summary[name] = dict(
            edge=cfg["edge"],
            producer=cfg["root"],
            cpu=cfg["cpu"],
            runtime=runtime,
            single_installed_call_per_visit_ms=spread(
                [r["installed"]["cpu_ns"] / 1e6 for r in source["rows"]]
            ),
            peak_rss_kib=source["peak_rss_kib"],
            fine_workspace_bytes=source["workspace_bytes"],
        )
        if tag == "selector":
            summary[name]["lane_over_vector_paired_cpu_savings_ms"] = spread(
                [
                    a["cpu_ms"] - b["cpu_ms"]
                    for a, b in zip(stacks["vector"], stacks["lane"], strict=True)
                ]
            )
    return summary, timing, parity


def plot_timings(summary, folder):
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.7), layout="constrained")
    display = [("fine", tuple(summary["fine"])), ("selector", tuple(summary["selector"]))]
    for axis, (tag, names) in zip(axes, display, strict=True):
        modes = trial.MODES if tag == "fine" else selectors.MODES
        for group, mode in enumerate(modes):
            positions = [i + (group - 1) * 0.18 for i in range(len(names))]
            values = [summary[tag][c]["runtime"][mode]["cpu_ms"] for c in names]
            estimates = [v["median"] for v in values]
            bounds = [
                [v["median"] - v["min"] for v in values],
                [v["max"] - v["median"] for v in values],
            ]
            axis.errorbar(
                positions,
                estimates,
                yerr=bounds,
                fmt="o",
                capsize=2,
                color=COLORS[mode],
                label=LABELS[mode],
            )
        axis.set_xticks(range(len(names)), names, rotation=20, ha="right")
        axis.set(
            title="Fine FFT workspace" if tag == "fine" else "Peak selection alone",
            ylabel="Complete dual detector CPU (ms)",
        )
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=0.2)
        axis.legend(frameon=False, loc="lower left")
    fig.suptitle("Original capture detector on 16 held saved-IQ windows")
    save_figure(fig, folder, "stage")


def save_figure(figure, folder, name):
    figure.savefig(folder / f"{name}.png", dpi=170)
    figure.savefig(folder / f"{name}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(figure)


def plot_profiles(raw, folder):
    profile_stages = []
    for doc in raw:
        times = {k: v["cpu_ns"] / 1e6 for k, v in doc["scopes"].items()}
        stage = dict(
            coarse=sum((g["config_cpu_ns"] + g["native_cpu_ns"]) / 1e6 for g in doc["grid"]),
            selection=times["acquisition._retain_score_map_peaks"],
            fine=times["acquisition._normalized_frame_scores"],
            conditioned=times["acquisition._conditioned_frame_scores"],
            verify=times["acquisition.normalized_frame_score"],
            glrt=times["fast_scan_detector.conditioned_glrt64_scores"]
            + times["fast_scan_detector.refine_glrt64_epochs"],
            projection=times["capture_detector_replay._probe"],
        )
        stage["other"] = times["analyze_window"] + stage["projection"] - sum(stage.values())
        profile_stages.append(
            dict(
                case=doc["case"],
                visit=doc["visit"],
                mode=doc["mode"],
                coarse_prefix_ms=times["acquisition._power_prefix"],
                **stage,
            )
        )
    csv_file(folder / "profile-stages.csv", profile_stages)
    fig, axis = plt.subplots(figsize=(10.5, 5.2), layout="constrained")
    colors = (
        "#30596e",
        "#c3773d",
        "#9473a5",
        "#6c9d90",
        "#5e994a",
        "#8b5767",
        "#2b302e",
        "#c7d1d4",
    )
    lower = [0.0] * len(profile_stages)
    for name, color in zip(stage, colors, strict=True):
        values = [r[name] for r in profile_stages]
        axis.bar(range(len(values)), values, bottom=lower, label=name.capitalize(), color=color)
        lower = [a + b for a, b in zip(lower, values, strict=True)]
    axis.set_xticks(
        range(len(lower)), [f"{r['case']}\n{LABELS[r['mode']]}" for r in profile_stages], fontsize=8
    )
    axis.set(
        title="Separate instrumented stage profile on two producer types",
        ylabel="CPU per dual visit (ms)",
    )
    axis.legend(ncols=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15))
    save_figure(fig, folder, "profile-stages")


def publish(root, folder):
    summary, clocks, parity = {}, [], {}
    for tag, subdir in (("fine", "run"), ("selector", "select")):
        summary[tag], timing, parity[tag] = collect(root / subdir, folder, tag)
        clocks.extend(timing)
    for module in (prepared_hotpath, prepared_hotpath_peaks):
        path = Path(module.__file__)
        summary.setdefault("implementation", {})[path.name] = dict(
            lines=len(path.read_text().splitlines()),
            source_bytes=path.stat().st_size,
            added_native_exports=0,
        )
    save_json(folder / "summary.json", summary)
    save_json(folder / "parity.json", parity)
    csv_file(folder / "stage.csv", clocks)
    profiles = [read(p) for p in sorted((root / "profiles").glob("*.json"))]
    if len(profiles) != 6:
        raise ValueError(
            "expected independently instrumented samples for two cases and three modes"
        )
    save_json(folder / "profiles.json", profiles)
    plot_timings(summary, folder)
    plot_profiles(profiles, folder)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="prepared-hotpath",
            title="Original complete detector hot path",
            boundary="Resident authentic dual CI16 through complete detector and probe projection",
            sample="16 held windows across four cases, five rotated repeats per arm",
            note="CPU timing and the separately instrumented stage profiles are different runs.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
            profile_image="profile-stages.png",
            profile_pdf="profile-stages.pdf",
            profile_csv="profile-stages.csv",
        ),
    )
    save_json(
        folder / "qualification-lock.json",
        dict(
            files={
                p.name: _sha(p)
                for p in sorted(folder.iterdir())
                if p.is_file()
                and p.name
                not in (
                    "README.md",
                    "qualification-lock.json",
                )
            },
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("report", type=Path, default=trial.REPORT, nargs="?")
    args = parser.parse_args()
    publish(args.scratch, args.report)
