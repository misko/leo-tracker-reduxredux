"""Plot cutoff coverage and separate source staging costs from sealed parallel runs."""

import argparse

from .. import whole_iq
from ..__main__ import local_output, save_json
from .arrival_queue import NS, readgz
from .full_v5_check import _sha
from .parallel_acquisition_source import CPUS, REPORT
from .prefix_figures import csv_file

MANIFEST_SHA = "4ecd18e9a91b84ee40056141df5073ea10eb3e55934382f1db54156528b05417"
LABELS = {"wide": "Wide four-region", "original": "Prepared original"}
OUTCOMES = (
    ("processed_by_cutoff", "Completed by close", "#176c6a"),
    ("queue_drops", "Busy-queue drops", "#b77154"),
    ("late_drain", "Finished in drain", "#e2b84e"),
)
TIMELY = "positive_within_20ms_by_cutoff"
NAME = "parallel-recorded-acquisition"
SEAL = "stage-figure-lock.json"
DESCRIPTOR = "stage-figure.json"


def branch_counts(trace, cutoff):
    counts = dict(processed_by_cutoff=0, queue_drops=0, late_drain=0, **{TIMELY: 0})
    for visit in trace:
        packet, finish = visit["packet"], visit["finish_ns"]
        before_close = packet is not None and finish <= cutoff
        if before_close != visit["observed_by_cutoff"]:
            raise ValueError("cutoff marker disagrees with the packet finish time")
        admission = visit["admission"]
        if admission == "invalid_capture" and packet is None:
            continue
        if admission == "dropped_busy" and packet is None:
            counts["queue_drops"] += 1
            continue
        if admission != "queued" or packet is None:
            raise ValueError("arrival does not have one terminal acquisition outcome")
        if before_close:
            counts["processed_by_cutoff"] += 1
            if finish - visit["arrival_ns"] <= 20_000_000 and any(
                c["passed_fractional_margin_gate"]
                for probe in packet["probes"]
                for c in probe["candidates"]
            ):
                counts[TIMELY] += 1
        else:
            counts["late_drain"] += 1
    return counts


def measurements(report):
    lock = whole_iq.read(whole_iq.checked(report / "manifest.json", MANIFEST_SHA))

    def member(name):
        return whole_iq.checked(report / name, lock["files"][name])

    detector, source = [], []
    for ident in CPUS:
        case = lock["cases"][ident]
        valid, duration = case["valid_visits"], case["last_arrival_ns"] / NS
        for role in LABELS:
            branch = case["branches"][role]
            counts = branch_counts(readgz(member(branch["trace"])), case["last_arrival_ns"])
            summary = branch["summary"]
            if (
                counts["processed_by_cutoff"] != summary["observed_by_cutoff"]
                or counts["queue_drops"] != summary["counts"]["dropped_busy"]
                or counts["late_drain"] != summary["late_drain_packets"]
                or counts[TIMELY] != summary["positive_within_20ms"]
                or sum(counts[key] for key, _, _ in OUTCOMES) != valid
            ):
                raise ValueError("timing figure changed measured counts or the valid denominator")
            detector.append(
                dict(
                    recording=ident,
                    detector=role,
                    stage="detector",
                    recorded_span_s=duration,
                    valid_visits=valid,
                    **counts,
                )
            )
        stage = whole_iq.read(member(case["stage"]))
        source.append(
            dict(
                recording=ident,
                stage="source",
                recorded_span_s=duration,
                decode_readback_wall_s=stage["stage_start_to_ready_ns"] / NS,
                decode_readback_cpu_s=stage["stage_decode_and_readback_cpu_us"] / 1_000_000,
                compressed_capture_bytes=stage["stage"]["compressed_bytes"],
                staged_iq_bytes=stage["stage"]["bytes"],
                staged_memory_peak_bytes=stage["stage"]["end"]["memory.peak"],
                staging_swap_bytes=stage["stage"]["end"]["memory.swap.current"],
                staging_cpu_during_replay_us=stage["stage_cpu_during_replay_us"],
                publisher_replay_cpu_s=stage["publisher_replay_cpu_ns"] / NS,
            )
        )
    return detector, source


def draw(report, detector, source):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ((coverage, timely), (prep, size)) = plt.subplots(
        2, 2, figsize=(11.2, 7), gridspec_kw={"height_ratios": [1.55, 1]}
    )
    fig.subplots_adjust(left=0.23, right=0.96, top=0.87, bottom=0.145, wspace=0.33, hspace=0.73)
    fig.suptitle(
        "Two concurrent detectors on the recorded arrival clock",
        y=0.975,
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.924,
        "One 300-second replay per recording • one waiting visit per detector",
        ha="center",
        color="#475569",
        fontsize=10,
    )
    y = (0, 1, 2.35, 3.35)
    for pos, row in zip(y, detector, strict=True):
        left = 0
        for key, _, color in OUTCOMES:
            count = row[key]
            pct = 100 * count / row["valid_visits"]
            coverage.barh(pos, pct, left=left, color=color, height=0.58)
            if pct >= 8:
                coverage.text(
                    left + pct / 2,
                    pos,
                    f"{pct:.1f}%",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=8.5,
                    fontweight="bold",
                )
            left += pct
        count = row[TIMELY]
        pct = 100 * count / row["valid_visits"]
        timely.barh(pos, pct, color="#176c6a", height=0.51)
        timely.text(pct + 0.36, pos, f"{count:,}  ({pct:.1f}%)", va="center", fontsize=9)
    coverage.set(
        yticks=y,
        yticklabels=[f"{r['recording']}  {LABELS[r['detector']]}" for r in detector],
        xlim=(0, 100),
        title="What happened to each valid visit",
    )
    coverage.invert_yaxis()
    timely.set(
        yticks=y,
        yticklabels=[],
        ylim=coverage.get_ylim(),
        xlim=(0, 21),
        title="Positive within 20 ms and by close",
    )
    for ax in (coverage, timely):
        ax.xaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax.grid(axis="x", color="#e2e8f0")
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.set_xlabel("Share of all valid visits", labelpad=4)
    coverage.legend(
        handles=[Patch(color=color, label=label) for _, label, color in OUTCOMES],
        loc="upper left",
        bbox_to_anchor=(-0.01, -0.24),
        ncol=3,
        fontsize=8,
        frameon=False,
        columnspacing=0.85,
        handlelength=1,
    )
    for i, row in enumerate(source):
        t = row["decode_readback_wall_s"]
        prep.barh(i, t, height=0.45, color="#697e9a")
        prep.text(t + 0.55, i, f"{t:.1f} s", va="center", fontsize=9)
        for key, offset, color in (
            ("compressed_capture_bytes", -0.17, "#b2bdcb"),
            ("staged_iq_bytes", 0.17, "#697e9a"),
        ):
            gb = row[key] / NS
            size.barh(i + offset, gb, height=0.27, color=color)
            size.text(gb + 0.16, i + offset, f"{gb:.2f}", va="center", fontsize=9)
    cases = [row["recording"] for row in source]
    prep.set(
        yticks=range(len(cases)),
        yticklabels=cases,
        xlim=(0, 41),
        title="Source decode and verified readback",
        xlabel="Wall time (s)",
    )
    size.set(
        yticks=range(len(cases)),
        yticklabels=cases,
        xlim=(0, 12.9),
        title="Source input and resident IQ",
        xlabel="Bytes (GB)",
    )
    for ax in (prep, size):
        ax.tick_params(axis="y", length=0)
        ax.invert_yaxis()
    size.legend(
        handles=[
            Patch(color="#b2bdcb", label="Compressed read"),
            Patch(color="#697e9a", label="Staged CI16"),
        ],
        loc="upper left",
        bbox_to_anchor=(0, -0.23),
        ncol=2,
        fontsize=8,
        frameon=False,
    )
    fig.text(
        0.06,
        0.022,
        "Valid visits per branch  DS29-0082  4,868  |  DS26-0237  6,766. "
        "The last physical arrival sets the cutoff. Each branch drained 1 or 2 visits.",
        fontsize=8.5,
        color="#475569",
    )
    fig.savefig(report / f"{NAME}.png", dpi=175)
    fig.savefig(report / f"{NAME}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def generate(report):
    detector, source = measurements(report)
    draw(report, detector, source)
    rows = detector + source
    fields = dict.fromkeys(key for row in rows for key in row)
    csv_file(report / "stage-timing.csv", [fields | row for row in rows])
    save_json(
        report / DESCRIPTOR,
        dict(
            version=1,
            id=NAME,
            title="Two concurrent detectors at recorded pace",
            sample="DS29-0082 and DS26-0237, one full 300-second paired host replay each",
            boundary="Two distinct pinned detector cores with one waiting visit per branch",
            note="Shares use all valid visits. Positive packets meet 20 ms and finish by the last "
            "recorded arrival. Source staging costs precede the receiver clock.",
            image=f"{NAME}.png",
            pdf=f"{NAME}.pdf",
            csv="stage-timing.csv",
            seal=SEAL,
        ),
    )
    names = (DESCRIPTOR, f"{NAME}.png", f"{NAME}.pdf", "stage-timing.csv", "manifest.json")
    save_json(report / SEAL, dict(files={name: _sha(report / name) for name in names}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    generate(parser.parse_args().report)
