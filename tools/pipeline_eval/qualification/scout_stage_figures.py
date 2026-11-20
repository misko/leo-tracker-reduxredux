"""Render acquisition-stage evidence from sealed stored-IQ measurements."""

import argparse
import gzip
import io
import json
import os
from dataclasses import dataclass
from hashlib import file_digest
from pathlib import Path
from statistics import median
from textwrap import fill

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from ..__main__ import ROOT, encoded, local_output, save_json, write  # noqa: E402

SCREENING = ROOT / "reports/2026_11_19_receiver_screening"
SUPPORT = SCREENING / "acquisition-support"
REPORT = SUPPORT / "stage-charts"
BOOK = "stage-evidence.pdf"
BASE, CANDIDATE, DIAGNOSTIC = "#5D6870", "#146C5F", "#A96124"
INK, SECONDARY = "#182832", "#495B64"


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    summary: str
    sources: tuple[Path, ...]
    figure: Figure


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verify(folder, receipt):
    lock = folder / receipt
    files = read(lock)["files"]
    for name, digest in files.items():
        if sha(folder / name) != digest:
            raise ValueError(f"sealed stage evidence changed: {folder.name}/{name}")
    return (lock, *(folder / name for name in files))


def canvas(title, scope, note):
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.2), facecolor="white")
    fig.subplots_adjust(left=0.184, right=0.943, bottom=0.244, top=0.715, wspace=0.41)
    fig.text(0.055, 0.917, title, fontsize=25, color=INK, weight="bold", va="top")
    fig.text(0.056, 0.832, scope, fontsize=12, color=SECONDARY, va="top")
    fig.text(0.056, 0.066, fill(note, 132), fontsize=10.4, color=SECONDARY, va="bottom")
    for ax in axes:
        ax.spines[["left", "right", "top"]].set_visible(False)
        ax.spines["bottom"].set_color("#ABB8BE")
        ax.tick_params(length=0, labelsize=9.5, colors=INK, pad=6)
        ax.grid(axis="x", color="#DCE4E7", linewidth=0.8)
        ax.set_axisbelow(True)
    return fig, axes


def header(ax, title, xlabel, labels, xmax):
    ax.set_title(title, fontsize=13.5, loc="left", pad=13, color=INK, weight="bold")
    ax.set_xlabel(xlabel, fontsize=10.5, labelpad=8, color=SECONDARY)
    ax.set_xlim(0, xmax)
    ax.set_yticks(list(range(len(labels))), labels)
    ax.set_ylim(len(labels) - 0.49, -0.52)


def paired(ax, labels, values, *, title, xlabel, fmt=".2f", denominator=None, xmax=None):
    maximum = max(v for pair in values for v in pair)
    limit = xmax or max(1, maximum * 1.30)
    header(ax, title, xlabel, labels, limit)
    for i, pair in enumerate(values):
        for offset, value, color in zip((-0.16, 0.16), pair, (BASE, CANDIDATE), strict=True):
            ax.barh(i + offset, value, height=0.23, color=color)
            denom = f" / {denominator}" if denominator is not None else ""
            ax.text(
                value + limit * 0.018,
                i + offset,
                format(value, fmt) + denom,
                ha="left",
                va="center",
                color=INK,
                fontsize=9,
            )


def key(fig, base, candidate):
    fig.legend(
        handles=[Patch(color=BASE, label=base), Patch(color=CANDIDATE, label=candidate)],
        loc="lower left",
        bbox_to_anchor=(0.052, 0.124),
        ncol=2,
        frameon=False,
        fontsize=10.5,
    )


def folded(root):
    folder = root / "folded-bank"
    receipt, sealed, capsule = (
        folder / name
        for name in (
            "receipt.json",
            "source-lock.json",
            "armv7-benchmark.tar.gz",
        )
    )
    r = read(receipt)
    if sha(sealed) != r["source_lock_sha256"] or sha(capsule) != r["distribution_sha256"]:
        raise ValueError(
            "folded-bank source or benchmark archive differs from the published receipt"
        )
    cases = r["cases"]
    order = ("captured", "weak-pair", "noise")
    title = "FFT reuse accelerates the full folded acquisition grid"
    cells = cases["captured"]["parity"]["host-bank"]["values_compared"]
    delta = max(
        case["parity"][f"{port}-bank"]["max_absolute_score_delta"]
        for case in cases.values()
        for port in ("host", "arm")
    )
    rank = all(
        case["parity"][f"{port}-bank"]["retained_epoch_cfo_exact"]
        for case in cases.values()
        for port in ("host", "arm")
    )
    if not rank:
        raise ValueError("the folded-bank rank parity does not support the plotted claim")
    note = (
        f"Each pair evaluates all {cells:,} CFO–epoch cells. All retained basin ranks agree. "
        f"Largest absolute score difference across the three fixtures is {delta:.2e}. "
        "The stage includes filter transforms and planning. Cortex-A9 timing is emulated."
    )
    fig, axes = canvas(
        title, "One receiver's coarse folded acquisition on saved IQ and two controls", note
    )
    names = ("Saved IQ", "Weak pair", "Noise only")
    for ax, arch, arch_label in zip(
        axes, ("host", "arm"), ("Native x86", "Cortex-A9 QEMU"), strict=True
    ):
        rows, values = [], []
        for label, case in zip(names, order, strict=True):
            timing = cases[case]["median_stage_cpu_ns"][arch]
            count = len(cases[case]["timings"][arch]["direct"])
            if count != len(cases[case]["timings"][arch]["bank"]):
                raise ValueError("unpaired folded CPU observations")
            rows.append(f"{label}\n{count} pair{'s' if count != 1 else ''}")
            values.append(tuple(timing[m]["folded_grid_body"] / 1e9 for m in ("direct", "bank")))
        paired(ax, rows, values, title=arch_label, xlabel="Median folded-grid CPU (s)", fmt=".3f")
    key(fig, "Direct FP64", "Overlap-save FFT bank")
    return Stage(
        "folded-bank",
        title,
        "Full-grid CPU with score and basin parity",
        (receipt, sealed, capsule),
        fig,
    )


def capture_fft_data(folder):
    lock = read(folder / "source-lock.json")
    library = lock["source_files"][lock["library"]]
    measures = {}
    for ident, item in lock["cases"].items():
        raw = read(folder / f"{ident}.json.gz")
        if raw["id"] != ident or raw["candidate_source_sha256"] != library:
            raise ValueError("capture FFT response differs from the frozen native producer")
        bound = item["roster"]
        rows = {f"{r['segment']}-{r['sequence']}": r for r in raw["captures"]}
        if set(bound) != set(rows) or any(
            any(row[k] != value for k, value in bound[ident].items()) for ident, row in rows.items()
        ):
            raise ValueError("capture FFT changed the prespecified IQ roster")
        pairs = [p for visit in rows.values() for p in visit["rows"]]
        selected = [
            p for p in pairs if p["installed"]["status"] == p["fft"]["status"] == "processed"
        ]
        if not selected or any(set(pair) != {"installed", "fft"} for pair in pairs):
            raise ValueError("capture FFT needs paired processed measurements")
        repeat = [visit["rows"][-1] for visit in rows.values() if visit["rows"][-1] in selected]
        modes = ("installed", "fft")
        measures[ident] = dict(
            calls=len(selected),
            scheduled_calls=len(pairs),
            visits=len(rows),
            exact=sum(
                all(
                    encoded(p["installed"][k]) == encoded(p["fft"][k]) for k in ("public", "probes")
                )
                for p in selected
            ),
            total=tuple(median(p[m]["cpu_ns"] for p in selected) / 1e6 for m in modes),
            coarse=tuple(
                median(p[m]["stages_cpu_ns"]["coarse_inclusive"] for p in selected) / 1e6
                for m in modes
            ),
            warm_calls=len(repeat),
            warm_total=tuple(median(p[m]["cpu_ns"] for p in repeat) / 1e6 for m in modes),
            warm_coarse=tuple(
                median(p[m]["stages_cpu_ns"]["coarse_inclusive"] for p in repeat) / 1e6
                for m in modes
            ),
        )
    return measures


def capture_fft(root):
    folder = root / "capture-fft"
    if not (folder / "source-lock.json").is_file():
        return None
    cases = read(folder / "source-lock.json")["cases"]
    files = tuple(folder / f"{ident}.json.gz" for ident in cases)
    if not all(p.is_file() for p in files):
        return None
    detector_lock = folder / "detector-lock.json"
    source = folder / "source-lock.json"
    sources = (source, *files)
    if detector_lock.is_file():
        if read(detector_lock)["source_lock_sha256"] != sha(source):
            raise ValueError("capture FFT detector seal has a different source lock")
        sources = (source, *verify(folder, detector_lock.name))
    measured = capture_fft_data(folder)
    title = "Exhaustive FFT scores inside the installed capture detector"
    total = sum(m["calls"] for m in measured.values())
    scheduled = sum(m["scheduled_calls"] for m in measured.values())
    exact = sum(m["exact"] for m in measured.values())
    note = (
        f"Exact public and probe payloads on {exact}/{total} processed pairs. "
        f"The timing panel includes {total}/{scheduled} scheduled repeated pairs. "
        "The coarse clock includes each release's own selector. "
        "Timings cover the installed detector invocation."
    )
    fig, axes = canvas(
        title,
        "Two authenticated capture producers on x86, four saved dual-receiver visits each",
        note,
    )
    labels = [
        label
        for case, m in measured.items()
        for label in (
            f"{case}\n{m['calls']} matched calls",
            f"{case}\n{m['warm_calls']} warm repeats",
        )
    ]
    for ax, metric, heading in zip(
        axes,
        ("coarse", "total"),
        ("Inclusive coarse stage", "Full detector invocation"),
        strict=True,
    ):
        paired(
            ax,
            labels,
            [pair for m in measured.values() for pair in (m[metric], m[f"warm_{metric}"])],
            title=heading,
            xlabel="Median process CPU (ms)",
            fmt=".1f",
        )
    key(fig, "Installed producer", "Exhaustive FFT grid")
    return Stage(
        "capture-fft",
        title,
        "Paired saved-IQ CPU and exact detector output",
        sources,
        fig,
    )


def thinned(root):
    folder = root / "thinned-capture"
    sources = verify(folder, "evidence-lock.json")
    data = read(folder / "qualification.json")
    names = ("Original", "Thinned", "Wide")
    timing = [data["timing"][name] for name in ("capture", "thinned", "wide")]
    positives = data["held_positives"]
    count = positives["thinned"]["original"]
    if positives["wide"]["original"] != count or len({r["calls"] for r in timing}) != 1:
        raise ValueError("detector runs have different reference denominators")
    calls = timing[0]["calls"]
    basins = data["held_basin_keys"]
    title = "Thinning lowers detector CPU and misses original positives"
    note = (
        f"Each detector has {calls} measured calls over ten admitted dual-receiver visits. "
        f"The thinned proposal retained {basins['retained']}/{basins['original']} "
        "first-pass coarse basins. "
        f"Additional positives relative to the original were {positives['thinned']['surplus']} "
        f"for thinning and {positives['wide']['surplus']} for the wide detector."
    )
    fig, (ax, match_plot) = canvas(
        title,
        "Capture-era input and exact rescoring compared with the installed wide detector",
        note,
    )
    color = (BASE, CANDIDATE, DIAGNOSTIC)
    cpu = [t["median_cpu_ms"] for t in timing]
    ax.set_xscale("log")
    ax.set_xlim(10, 3600)
    ax.set_yticks(range(len(names)), names)
    ax.set_ylim(2.5, -0.5)
    ax.set_title("Saved-IQ detector cost", fontsize=13.5, loc="left", pad=13, weight="bold")
    ax.set_xlabel("Median detector CPU (ms, log scale)", fontsize=10.5, color=SECONDARY)
    ax.axvline(20, color="#819197", linestyle="--", linewidth=1)
    ax.text(20, 2.39, "20 ms", va="bottom", ha="center", color=SECONDARY, fontsize=8.5)
    for i, (value, shade) in enumerate(zip(cpu, color, strict=True)):
        ax.scatter(value, i, s=47, color=shade, zorder=3)
        ax.annotate(
            f"{value:,.2f}",
            (value, i),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
        )
    retained = [count, positives["thinned"]["matched"], positives["wide"]["matched"]]
    header(
        match_plot, "Final positive recovery", "One-to-one matches to original", names, count * 1.25
    )
    for i, (value, shade) in enumerate(zip(retained, color, strict=True)):
        match_plot.barh(i, value, height=0.36, color=shade)
        match_plot.text(value + 0.45, i, f"{value} / {count}", fontsize=9, va="center")
    return Stage(
        "thinned-capture",
        title,
        "Detector CPU, coarse basin loss and positive recall",
        sources,
        fig,
    )


PHASE_ORDER = ("recorded", "planted", "weak", "null")


def phase_groups(folder):
    sources = (*verify(folder, "prediction-lock.json"), folder / "scores.json")
    groups = read(folder / "scores.json")["groups"]
    if (
        sum(r["windows"] for r in groups.values())
        != read(folder / "prediction-lock.json")["attempts"]
    ):
        raise ValueError("phase-scout summary roster does not match the prediction receipt")
    return sources, groups


def share(ax, labels, counts, *, title, xlabel, color, xmax=None):
    values = [100 * numerator / denominator for numerator, denominator in counts]
    limit = xmax or max(2, max(values) * 1.48)
    header(ax, title, xlabel, labels, limit)
    for i, (value, (numerator, denominator)) in enumerate(zip(values, counts, strict=True)):
        ax.barh(i, value, height=0.35, color=color)
        ax.text(
            value + limit * 0.018, i, f"{numerator:,}/{denominator:,}", fontsize=8.6, va="center"
        )


def phase(root):
    sources, groups = phase_groups(root / "phase-scout")
    recorded = groups["recorded"]
    primary = recorded["primary"]
    exact = recorded["exact_payloads"]
    note = (
        f"Recorded outputs matched exactly on {exact}/{recorded['windows']} windows. "
        f"Signed phase saved {primary['compared_cells'] - primary['evaluated_cells']:,} of "
        f"{primary['compared_cells']:,} real epoch/bin cells."
    )
    title = "Signed phase rarely narrows the grid on saved IQ"
    fig, (allocation, timing) = canvas(
        title,
        "Signed phase detector on 28 complete dual-receiver windows",
        note,
    )
    labels = [f"{name.capitalize()}\n{groups[name]['windows']} windows" for name in PHASE_ORDER]
    share(
        allocation,
        labels,
        [
            (groups[name]["primary"]["restricted"], groups[name]["primary"]["centers"])
            for name in PHASE_ORDER
        ],
        title="Neighborhoods assigned fewer bins",
        xlabel="Share of scout neighborhoods (%)",
        color=CANDIDATE,
    )
    timing_rows = [
        tuple(recorded["timings"][m][k] for m in ("stock", "candidate"))
        for k in ("detector_ms", "coarse_ms")
    ]
    paired(
        timing,
        ["Full detector", "Coarse stage"],
        timing_rows,
        title="Recorded detector CPU",
        xlabel="Median CPU per window (ms)",
        fmt=".3f",
    )
    key(fig, "All 21 bins", "Signed phase")
    return Stage(
        "phase-scout",
        title,
        "Real and synthetic allocation rates with paired recorded detector CPU",
        sources,
        fig,
    )


def coherent_phase(root):
    folder = root / "phase-scout"
    sources, groups = phase_groups(folder)
    sources = (*sources, *verify(folder, "coherent-lock.json"))
    cpu = groups["recorded"]["median_prototype_cpu_ms"]
    title = "Coherent phase narrows planted cases on a replayed grid"
    note = (
        f"The Python allocation diagnostic used median {cpu:.2f} ms "
        "CPU per recorded window. Counts come from the stock score grid and the prototype's "
        "eligibility masks. Detector execution and positioning sit outside this diagnostic."
    )
    fig, (allocation, work) = canvas(
        title,
        "Measured prototype allocation using sealed complete-grid output",
        note,
    )
    labels = [f"{name.capitalize()}\n{groups[name]['windows']} windows" for name in PHASE_ORDER]
    modes = [groups[name]["coherent"] for name in PHASE_ORDER]
    share(
        allocation,
        labels,
        [(r["restricted"], r["centers"]) for r in modes],
        title="Neighborhoods assigned fewer bins",
        xlabel="Share of scout neighborhoods (%)",
        color=DIAGNOSTIC,
    )
    share(
        work,
        labels,
        [
            (r["compared_symbol_bins"] - r["evaluated_symbol_bins"], r["compared_symbol_bins"])
            for r in modes
        ],
        title="Supported work the masks would avoid",
        xlabel="Share of symbol × bin evaluations (%)",
        color=DIAGNOSTIC,
        xmax=53,
    )
    return Stage(
        "phase-scout-coherent",
        title,
        "Recorded and planted eligibility plus supported work avoided",
        sources,
        fig,
    )


def scout(root, name):
    folder = root / name
    sources = verify(folder, "prediction-lock.json")
    held = read(folder / "qualification.json")["held"]
    budget = name == "scout-budget"
    alternate = "scout16" if budget else "radius2"
    modes = [held["modes"][m] for m in ("control", alternate)]
    eligible = "archive_positive_epochs_in_scout" if budget else "archive_eligible"
    final = "matched_final" if budget else "archive_final_matched"
    pooled = "total_cpu_ms" if budget else "pooled_cpu_ms"
    cpu_stage = "stages_cpu_ms" if budget else "stage_cpu_ms"
    calls_key = "late_calls" if budget else "calls"
    calls = modes[0][calls_key]
    if modes[1][calls_key] != calls:
        raise ValueError("scout timing counts differ")
    count = modes[0]["archive_positives"] if budget else held["archive_records"]
    head = (
        "Sixteen scout centers increase detector CPU"
        if budget
        else "Wider scout radius covers three more archived positives"
    )
    delta = 100 * (modes[1][pooled] / modes[0][pooled] - 1)
    wall_key = "wall_within_20_ms" if budget else "wall_within_20ms"
    achieved = tuple(m[wall_key] for m in modes)
    note = (
        f"{held['processed']}/{held['scheduled']} saved visits were admitted. "
        f"Pooled detector CPU changed {delta:+.2f}%. "
        f"Wall time met 20 ms on {achieved[0]}/{calls} control and "
        f"{achieved[1]}/{calls} candidate calls. "
        "Final matches use the original capture-era epoch and CFO tolerances."
    )
    fig, (evidence, timing) = canvas(
        head, f"Matched detector runs over {calls} warm calls on x86", note
    )
    paired(
        evidence,
        ["Epoch in scout support", "Final positive match"],
        [tuple(m[k] for m in modes) for k in (eligible, final)],
        title="Archived positive records",
        xlabel="Original positive records represented",
        fmt=".0f",
        denominator=count,
    )
    paired(
        timing,
        ["Full detector", "Regional coarse"],
        [
            tuple(m[pooled] / calls for m in modes),
            tuple(m[cpu_stage]["coarse"] / calls for m in modes),
        ],
        title="Pooled CPU divided by call count",
        xlabel="Mean CPU per warm call (ms)",
    )
    key(
        fig,
        "Four centers" if budget else "Radius one",
        "Sixteen centers" if budget else "Radius two",
    )
    return Stage(
        name, head, "Coarse geometric coverage, final matches and detector CPU", sources, fig
    )


def fractional(folder):
    authority = folder / "qualification.json"
    if not authority.is_file():
        return None
    sources = verify(folder, "prediction-lock.json")
    data = read(authority)
    title = "Ordered fractional interpolation reduces host work"
    host = data["architectures"]["host"]["totals"]
    before, after = (host[m]["within_20_ms"] for m in ("control", "fractional_runtime"))
    note = (
        f"Host prepared-IQ wall met 20 ms on {before}/{host['control']['calls']} control and "
        f"{after}/{host['fractional_runtime']['calls']} candidate calls. "
        "The medians remained above the deadline. "
        "This page accompanies the separately measured position comparison."
    )
    fig, axes = canvas(
        title,
        "Prepared saved-IQ detector outputs are identical within each measured architecture",
        note,
    )
    for ax, arch, label in zip(
        axes, ("host", "arm"), ("Native x86", "Cortex-A9 QEMU"), strict=True
    ):
        totals = data["architectures"][arch]["totals"]
        modes = [totals[m] for m in ("control", "fractional_runtime")]
        calls = modes[0]["calls"]
        if modes[1]["calls"] != calls:
            raise ValueError("fractional runtime needs paired call counts")
        stage_times = (
            tuple(m["search_cpu_total_ms"]["fractional_epoch"] / calls for m in modes)
            if arch == "host"
            else tuple(m["fractional_epoch_cpu_total_ms"] / calls for m in modes)
        )
        paired(
            ax,
            ["Full detector", "Fractional epoch"],
            [tuple(m["detector_cpu_total_ms"] / calls for m in modes), stage_times],
            title=f"{label} · {calls} calls per mode",
            xlabel="Mean process CPU per call (ms)",
        )
    key(fig, "Prepared parent", "Ordered interpolation")
    return Stage(
        "fractional-runtime",
        title,
        "Paired native and emulated CPU for the fractional-stage companion",
        sources,
        fig,
    )


def render(output, screening=SCREENING):
    output = local_output(output)
    support = screening / "acquisition-support"
    primary = [
        folded(support),
        capture_fft(support),
        thinned(support),
        phase(support),
        coherent_phase(support),
        scout(support, "scout-budget"),
        scout(support, "scout-radius"),
        fractional(screening / "streamlined/fractional-runtime"),
    ]
    pages = []
    document = io.BytesIO()
    with PdfPages(
        document, metadata=dict(Title="Saved-IQ acquisition stage evidence", CreationDate=None)
    ) as pdf:
        for index, item in enumerate((p for p in primary if p is not None), 1):
            image = f"{item.id}.png"
            data = io.BytesIO()
            item.figure.savefig(data, format="png", dpi=165, facecolor="white")
            write(output / image, data.getvalue())
            pdf.savefig(item.figure, facecolor="white")
            plt.close(item.figure)
            pages.append(
                dict(
                    id=item.id,
                    title=item.title,
                    summary=item.summary,
                    image=image,
                    pdf_page=index,
                    sources={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(item.sources))},
                )
            )
    write(output / BOOK, document.getvalue())
    pending = [
        name
        for name, item in (("capture-fft", primary[1]), ("fractional-runtime", primary[-1]))
        if item is None
    ]
    manifest = dict(
        version=1, book=BOOK, book_sha256=sha(output / BOOK), pages=pages, pending=pending
    )
    save_json(output / "manifest.json", manifest)
    index = [
        "# Saved-IQ acquisition stage evidence",
        "",
        f"[Read the combined PDF]({BOOK}) · [Evidence and source hashes](manifest.json)",
        "",
        "These charts compare physical acquisition and detector stages on sealed measurements. "
        "Each page identifies the timed boundary, matched exposures and relevant detector outcome. "
        "Cortex-A9 figures use emulation. A companion page covers fractional interpolation.",
        "",
    ]
    for page in pages:
        source = next(
            (
                p
                for p in page["sources"]
                if p.endswith(("qualification.json", "scores.json", "receipt.json", "summary.json"))
            ),
            next(iter(page["sources"])),
        )
        relative = os.path.relpath(ROOT / source, output)
        index.append(
            f"- [{page['title']}]({page['image']}) · PDF page {page['pdf_page']}. "
            f"{page['summary']}. [Source evidence]({relative})"
        )
    if pending:
        index.extend(
            ("", "Stages awaiting a complete measured receipt include " + ", ".join(pending) + ".")
        )
    index.extend(
        (
            "",
            "## Reproduce",
            "",
            "```sh",
            ".venv/bin/python -m tools.pipeline_eval.qualification.scout_stage_figures",
            "```",
            "",
        )
    )
    write(output / "README.md", "\n".join(index).encode())
    return manifest


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--output", type=Path, default=REPORT)
    render(args.parse_args().output)


if __name__ == "__main__":
    main()
