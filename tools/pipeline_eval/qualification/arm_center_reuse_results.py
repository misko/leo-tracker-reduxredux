"""Verify center/outer-start parity and publish saved-visit measurements."""

import argparse
import gzip
from hashlib import sha256
from pathlib import Path
from statistics import median, quantiles

from ..__main__ import ROOT, encoded, local_output, save_json, write
from . import arm_center_reuse_build as build
from . import arm_center_reuse_eval as eval_run
from . import arm_receiver_eval as receiver
from .arm_receiver_results import oracle_rows
from .full_v5_check import _sha
from .prefix_figures import csv_file

MODES = build.MODES
ARCHES = build.ARCH
DETECTORS = eval_run.DETECTORS
ARCH_TITLES = {"host": "Native x86", "arm64": "Cortex-A53 QEMU"}
MODE_TITLES = ("Original scalar", "Center reuse", "Center + outer pairs")


def conserved(original, center, pair):
    """Prove work issuance covers the same number of original lattice points."""
    s, sr, sp, sf = original
    c, cr, cp, cf = center
    p, pr, pp, pf = pair
    return (
        sr == sp == sf == cp == cf == 0
        and s == c + cr == p + pr + 2 * pp
        and (cr == pr and 0 <= pf <= 16 * pp)
    )


def packet(row):
    return encoded(receiver.scientific(row))


def audit(data, fixture, archive):
    outcomes, timing = [], []
    for edge in eval_run.EDGES:
        for detector in DETECTORS:
            timed = data["timed"][edge][detector]
            trace = data["trace"][edge][detector]
            real = timed["original"]["visits"]
            for idx, entry in enumerate(fixture["roster"][edge]):
                raw = [trace[m]["visits"][idx] for m in MODES]
                checksums = {
                    m: sha256(packet(r)).hexdigest() for m, r in zip(MODES, raw, strict=True)
                }
                original = packet(real[idx])
                source = archive[edge][detector][idx] if entry["kind"] == "recorded" else None
                outcomes.append(
                    dict(
                        arch=data["arch"],
                        edge=edge,
                        detector=detector,
                        file=entry["file"],
                        iq_sha256=entry["iq_sha256"],
                        kind=entry["kind"],
                        visit=entry.get("visit"),
                        delivery_clock=entry.get("delivery_clock"),
                        counter=entry.get("counter"),
                        matches_archived_factors=(
                            [receiver.projection(lane) for lane in real[idx]["rows"]]
                            == [p["candidates"] for p in source]
                            if source is not None
                            else None
                        ),
                        original_sha256=sha256(original).hexdigest(),
                        trace_sha256=checksums,
                        within_arch_parity={
                            m: receiver.parity(raw[0], r) for m, r in zip(MODES, raw, strict=True)
                        },
                        work={m: r["work"] for m, r in zip(MODES, raw, strict=True)},
                        work_conserved=conserved(*(r["work"] for r in raw)),
                        plants={m: oracle_rows(entry, r) for m, r in zip(MODES, raw, strict=True)},
                    )
                )
            for variant in MODES:
                for row, old in zip(timed[variant]["visits"], real, strict=True):
                    i, repeat = row["index"], row["repeat"]
                    if (i, repeat) != (old["index"], old["repeat"]):
                        raise ValueError("paired receipts changed fixture order")
                    entry = fixture["roster"][edge][i]
                    timing.append(
                        dict(
                            arch=data["arch"],
                            edge=edge,
                            detector=detector,
                            variant=variant,
                            file=entry["file"],
                            kind=entry["kind"],
                            repeat=repeat,
                            warm=i > 0 or repeat > 0,
                            candidate_exact=packet(row)
                            == packet(old)
                            == packet(trace[variant]["visits"][i]),
                            fractional_cpu_ms=sum(
                                lane["timings_ms"]["fractional_epoch"] for lane in row["rows"]
                            ),
                            detector_cpu_ms=row["detector"]["cpu_ns"] / 1e6,
                            detector_wall_ms=row["detector"]["wall_ns"] / 1e6,
                            complete_cpu_ms=(row["scout"]["cpu_ns"] + row["detector"]["cpu_ns"])
                            / 1e6,
                            complete_wall_ms=(row["scout"]["wall_ns"] + row["detector"]["wall_ns"])
                            / 1e6,
                        )
                    )
    return outcomes, timing


def stats(inputs):
    warm = [x for x in inputs if x["warm"]]
    clocks = (
        "fractional_cpu_ms",
        "detector_cpu_ms",
        "detector_wall_ms",
        "complete_cpu_ms",
        "complete_wall_ms",
    )
    return dict(
        warm_count=len(warm),
        all_recorded=len(inputs),
        complete_wall_within_20ms=sum(r["complete_wall_ms"] <= 20 for r in inputs),
        p50={c: median(r[c] for r in warm) for c in clocks},
        p95={c: quantiles([r[c] for r in warm], n=100, method="inclusive")[94] for c in clocks},
    )


def cross_architecture(measures):
    rows = []
    for edge in eval_run.EDGES:
        for detector in DETECTORS:
            visits = [a["trace"][edge][detector]["original"]["visits"] for a in measures]
            for x, y in zip(*visits, strict=True):
                if (x["index"], x["repeat"]) != (y["index"], y["repeat"]):
                    raise ValueError("cross-architecture fixture order changed")
                rows.append(
                    dict(edge=edge, detector=detector, index=x["index"], **receiver.parity(x, y))
                )
    return rows


def summarize(measures, outcomes, timing):
    panel = {}
    for arch in ARCHES:
        panel[arch] = {}
        for detector in DETECTORS:
            group = [
                r
                for r in outcomes
                if (r["arch"], r["detector"], r["kind"]) == (arch, detector, "recorded")
            ]
            panel[arch][detector] = {
                m: dict(
                    **stats(
                        [
                            r
                            for r in timing
                            if (r["arch"], r["detector"], r["variant"], r["kind"])
                            == (arch, detector, m, "recorded")
                        ]
                    ),
                    work=[sum(r["work"][m][i] for r in group) for i in range(4)],
                )
                for m in MODES
            }
    process = {
        data["arch"]: dict(
            cpu_affinity=data["cpus"],
            cases={
                edge: {
                    detector: {
                        m: {k: p[k] for k in ("cpu_s", "wall_s", "max_process_rss_kib", "setup")}
                        for m, p in modes.items()
                    }
                    for detector, modes in streams.items()
                }
                for edge, streams in data["timed"].items()
            },
        )
        for data in measures
    }
    cross = cross_architecture(measures)
    lanes = [lane for r in cross for lane in r["lanes"]]
    return dict(
        panel=panel,
        process=process,
        timing_rows=len(timing),
        compared_unique_visits=len(outcomes),
        exact_timing_rows=sum(r["candidate_exact"] for r in timing),
        work_conserved_visits=sum(r["work_conserved"] for r in outcomes),
        exact_trace_comparisons=sum(
            p["scientific_bytes_agree"]
            for r in outcomes
            for m, p in r["within_arch_parity"].items()
            if m != "original"
        ),
        total_trace_comparisons=2 * len(outcomes),
        cross_architecture_original=dict(
            visits=len(cross),
            exact=sum(r["scientific_bytes_agree"] for r in cross),
            ranks_exact=sum(r["full_ranks_agree"] for r in cross),
            added_epochs_exact=sum(r["added_epochs_agree"] for r in cross),
            lanes=len(lanes),
            ordered_fractional_gates_exact=sum(lane["ordered_fractional_gates"] for lane in lanes),
            ordered_integer_keys_exact=sum(lane["ordered_integer_keys"] for lane in lanes),
            max_cfo_difference_hz=max(lane["max_cfo_difference_hz"] for lane in lanes),
            max_fractional_difference_samples=max(
                lane["max_fractional_difference_samples"] for lane in lanes
            ),
        ),
        archived_factors={
            a: [
                sum(r["matches_archived_factors"] is True for r in outcomes if r["arch"] == a),
                sum(r["matches_archived_factors"] is not None for r in outcomes if r["arch"] == a),
            ]
            for a in ARCHES
        },
    )


def plot(folder, summary):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, layout="constrained", figsize=(9, 6.4), sharex=True)
    for arch, row in zip(ARCHES, axes, strict=True):
        for detector, ax in zip(DETECTORS, row, strict=True):
            p50 = [summary["panel"][arch][detector][m]["p50"] for m in MODES]
            outer = [r["complete_cpu_ms"] for r in p50]
            actual = [r["fractional_cpu_ms"] for r in p50]
            walls = [r["complete_wall_ms"] for r in p50]
            ax.bar(range(3), outer, width=0.62, color="#6689a0", label="Total CPU")
            ax.bar(range(3), actual, width=0.62, color="#087e78", label="Fractional CPU")
            ax.scatter(range(3), walls, color="#17252e", s=185, marker="_", label="Total wall")
            ax.axhline(20, linestyle="--", color="#b14a57", linewidth=1.0, label="20 ms visit")
            ax.set(title=f"{ARCH_TITLES[arch]} · {detector}", ylabel="Warm dual-RX median (ms)")
            ax.set_ylim(0, max(20, *outer, *walls) * 1.23)
            ax.set_xticks(range(3), MODE_TITLES)
            ax.set_axisbelow(True)
            ax.grid(axis="y", alpha=0.22)
    fig.suptitle("Exact fractional grid reuse on two recorded streams")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, ncols=4, loc="outside upper center")
    fig.savefig(folder / "stage.png", dpi=180)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="arm-center-reuse",
            title="Portable fractional center and outer starts",
            boundary="Packed saved dual CI16 to native candidate rows with fractional grid",
            sample="Fixed visits 12–17 from two recordings, two passes per detector and variant",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
            note="Cortex-A53 times are host process clocks during QEMU emulation.",
        ),
    )


def publish(work):
    folder = build.REPORT
    measures = [build.read(work / f"measured-{a}.json") for a in ARCHES]
    fixture = build.read(work / "input-lock.json")
    inputs = work / "archived-probes.json"
    build.parent.check(inputs, fixture["archived_probes_sha256"])
    build.parent.check(Path(eval_run.__file__), fixture["source_sha256"])
    archive = build.read(inputs)
    outcomes, timing = [], []
    for a, data in zip(ARCHES, measures, strict=True):
        build.parent.check(work / "input-lock.json", data["input_lock_sha256"])
        release = build.parent.check(work / f"build-{a}.json", data["build_sha256"])
        for name, digest in build.read(release)["sources"].items():
            build.parent.check(ROOT / name, digest)
        for item in build.read(release)["artifacts"].values():
            build.parent.check(Path(item["path"]), item["sha256"])
        found, seen = audit(data, fixture, archive)
        outcomes.extend(found)
        timing.extend(seen)
        write(folder / release.name, release.read_bytes())
    write(folder / "input-lock.json", (work / "input-lock.json").read_bytes())
    write(folder / "archived-probes.json.gz", gzip.compress(inputs.read_bytes(), mtime=0))
    write(folder / "measurements.json.gz", gzip.compress(encoded(measures), mtime=0))
    write(folder / "parity.json.gz", gzip.compress(encoded(outcomes), mtime=0))
    save_json(folder / "cross-architecture.json", cross_architecture(measures))
    summary = summarize(measures, outcomes, timing)
    save_json(folder / "summary.json", summary)
    csv_file(folder / "stage.csv", timing)
    plot(folder, summary)
    files = (
        "README.md",
        "PROTOCOL.md",
        "input-lock.json",
        "archived-probes.json.gz",
        "measurements.json.gz",
        "parity.json.gz",
        "cross-architecture.json",
        "build-host.json",
        "build-arm64.json",
        "summary.json",
        "stage.csv",
        "stage.pdf",
        "stage.png",
        "stage-figure.json",
    )
    save_json(
        folder / "qualification-lock.json",
        dict(
            cases=["DS26-0197", "DS29-0316"],
            scope="saved IQ detector, native x86 and emulated AArch64 Cortex-A53",
            files={n: _sha(folder / n) for n in files},
            sources={
                str(p.relative_to(ROOT)): _sha(p)
                for p in (
                    Path(__file__),
                    ROOT / "tests/pipeline_eval/test_arm_center_reuse.py",
                )
            },
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", default=build.WORK, type=local_output)
    publish(p.parse_args().work)
