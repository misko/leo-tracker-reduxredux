"""Render and package the receiver-core position gallery and sealed stage measurements."""

import argparse
import csv
import io
import json
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from statistics import median
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from matplotlib.backends.backend_pdf import PdfPages

from .. import atlas
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import POSITION_FAILURES, arm_outcome, terminal_position_decision
from . import acquisition_index as index
from . import acquisition_pack as export
from . import scout_stage_figures as stage
from . import screening_figures as position

ROOT = stage.SCREENING / "receiver-core"
ZIP = "modification-charts.zip"
TITLE = "Receiver-core measurements"
ARMS = index.ARMS
STAGE_SPEC = "stage-figure.json"


@dataclass(frozen=True)
class AuthoredStage:
    id: str
    title: str
    sample: str
    boundary: str
    note: str
    seal: str = "result-lock.json"
    source_csv: str | None = None
    source_png: str | None = None
    source_pdf: str | None = None


AUTHORED_STAGES = (
    AuthoredStage(
        "track-timing",
        "Predict the next pilot epoch on a Doppler track",
        "4 recordings · two detector sources · matched timing permutations",
        "Graph track history → forecast the next fractional pilot epoch",
        "The two-peak forecast and shuffled next-epoch control use the same histories.",
    ),
    AuthoredStage(
        "causal-track-scout",
        "Causal scout starts from earlier tracklets",
        "6 wide recordings + 2 separate stride controls · 104,162 receiver probes",
        "Chronological saved detector factors → up to four future scout starts",
        "Prior same-lane pilot measurements supply each proposal. Coverage uses capture-era "
        "targets missed by the ordinary wide detector, with a matched timing-null subset.",
        seal="stage-figure-lock.json",
        source_csv="scores.csv",
    ),
    AuthoredStage(
        "hinted-glrt",
        "Use a causal hint in the four-start GLRT",
        "16 real dual-receiver IQ windows · hints in 24/32 lanes · separate controls",
        "Saved raw IQ and sealed hints → complete four-start detector",
        "The stock, causal and sham arms all kept four centers. Real-window margins remained "
        "below the 0.025 gate. Those windows contained zero capture-era positives.",
    ),
    AuthoredStage(
        "range-epoch",
        "Held pilot epochs and predicted orbital range",
        "4 recordings at one surveyed roof · 2 development and 2 held",
        "Known original v5 orbit identities and surveyed hypotheses → held epoch residuals",
        "This diagnostic uses privileged orbital identities and tests fixed nearby hypotheses. "
        "Clock-only, physical-range and reflected-sign measurements share the same held epochs.",
        seal="chart-lock.json",
    ),
)


@dataclass
class Page:
    id: str
    title: str
    study: str
    sample: str
    boundary: str
    note: str
    sources: dict
    series: tuple
    rows: list = field(default_factory=list)
    plots: list = field(default_factory=list)

    def add(self, recording, sample, condition, series, metric, value, unit, source, total=None):
        self.rows.append(
            dict(
                modification=self.id,
                recording=recording,
                sample=sample,
                condition=condition,
                series=series,
                metric=metric,
                value=value,
                unit=unit,
                denominator=total,
                source=f"{self.study}/{source}",
            )
        )

    def plot(self, title, unit, labels, values, *, fmt=".2f"):
        if len(labels) != len(values) or not labels:
            raise ValueError(f"empty or unpaired stage chart for {self.id}")
        self.plots.append((title, unit, labels, values, fmt))
        for label, pair in zip(labels, values, strict=True):
            for name, value in zip(self.series, pair, strict=True):
                self.rows.append(
                    dict(
                        modification=self.id,
                        recording=label,
                        sample="",
                        condition="plotted summary",
                        series=name,
                        metric=title,
                        value=value,
                        unit=unit,
                        denominator=None,
                        source="Verified measurements in this table",
                    )
                )


def sealed(folder, receipt, names):
    lock = folder / receipt
    if lock.suffix == ".json":
        hashes = stage.read(lock)["files"]
    else:
        hashes = dict(
            reversed(line.split(maxsplit=1))
            for line in lock.read_text().splitlines()
            if line.strip()
        )
    return authenticated(folder, lock, names, hashes)


def authenticated(folder, lock, names, hashes):
    sources = {lock.name: stage.sha(lock)}
    data = {}
    for name in names:
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or hashes.get(name) != stage.sha(
            path
        ):
            raise ValueError(f"unsealed stage source {folder.name}/{name}")
        sources[name] = hashes[name]
        data[name] = stage.read(path)
    return data, sources


def screened(root, vnni):
    study = "screened-detector"
    inputs = {"DS29-0174": "grid-run.json.gz" if vnni else "DS29-0174.json.gz"}
    if not vnni:
        inputs["DS26-0036"] = "DS26-0036.json.gz"
    data, hashes = sealed(root / study, "SHA256SUMS", ("summary.json", *inputs.values()))
    key, candidate = ("vnni_pair", "vnni_pair") if vnni else ("lanczos_reuse", "reuse")
    title = "Paired integer-VNNI epochs" if vnni else "Reuse exact Lanczos coefficients"
    boundary = "Saved dual-RX IQ → complete detector and probe projection"
    receipt = data["summary.json"][key]
    sample = (
        f"{sum(v['windows'] for v in (r['authentic'] for r in receipt.values()))} windows · "
        f"{len(inputs)} recording{'s' if len(inputs) != 1 else ''} · 3 warm pairs per window"
    )
    leaf = "screen_integer_grid" if vnni else "lanczos"
    note = "The coefficient cache preserved public rows and capture-era probes on both producers."
    if vnni:
        archived = receipt["DS29-0174"]
        cells = sum(archived[k]["audited_screen_cells"] for k in ("authentic", "controls"))
        diffs = sum(archived[k]["differing_screen_cells"] for k in ("authentic", "controls"))
        improvement = archived["authentic"]["paired_median_cpu_improvement_percent"]
        note = (
            f"The grid audit compared {cells:,} integer screen cells with {diffs} differences. "
            f"Matched whole-detector median CPU improvement was {improvement:.2f}%."
        )
    page = Page(
        "screened-vnni" if vnni else "screened-lanczos",
        title,
        study,
        sample,
        boundary,
        note,
        hashes,
        ("Installed detector", "Paired VNNI" if vnni else "Lanczos cache"),
    )
    for case, name in inputs.items():
        raw = data[name]
        for condition, windows in (
            ("recorded", raw["captures"]),
            ("control", raw["controls"].values()),
        ):
            for i, window in enumerate(windows, 1):
                for pair, observation in enumerate(window["pairs"], 1):
                    for mode in ("installed", candidate):
                        m = observation[mode]
                        metrics = dict(
                            detector_cpu=m["cpu_ns"],
                            detector_wall=m["wall_ns"],
                            **m["refinement_cpu_ns"],
                            **m["stages_cpu_ns"],
                        )
                        for metric, ns in metrics.items():
                            page.add(
                                case,
                                f"{window.get('visit', i)}/{pair}",
                                condition,
                                mode,
                                metric,
                                ns / 1e6,
                                "ms",
                                name,
                            )
        for metric, value in receipt[case]["authentic"].items():
            if isinstance(value, (int, float)):
                page.add(
                    case,
                    "",
                    "warm summary",
                    candidate,
                    metric,
                    value,
                    "%" if "percent" in metric else "count",
                    "summary.json",
                )
        first = receipt[case]["cold_first_visit"]
        for mode in ("installed", candidate):
            for metric, ms in first[f"{mode}_ms"].items():
                page.add(case, first["visit"], "first use", mode, metric, ms, "ms", "summary.json")
    for title, metric in (
        ("Complete detector", "cpu"),
        ("VNNI screen grid" if vnni else "Lanczos interpolation", leaf),
    ):
        page.plot(
            title,
            "Median CPU (ms)",
            list(inputs),
            [
                tuple(
                    receipt[case]["authentic"]["median_ms"][m][metric]
                    for m in ("installed", candidate)
                )
                for case in inputs
            ],
        )
    return page


def stride_host(root):
    study, qualification = "cfo-stride", "qualification.json"
    files = ("DS26-0036-held.json.gz", "DS29-0082-held.json.gz")
    data, hashes = sealed(root / study, "prediction-lock.json", (qualification, *files))
    q = data[qualification]
    page = Page(
        "cfo-stride-host",
        "CFO stride on the x86 host",
        study,
        "22/24 held visits · 108 timed calls per method · 2 recordings",
        "Saved IQ → four-region wide detector",
        "Both banks matched the same 23 archived positive records. The eight separately "
        "traced receiver rows used 39.0% fewer coarse cells after local repair.",
        hashes,
        ("Full 21-bin bank", "Stride and repair"),
    )
    for name in files:
        receipt = data[name]
        for row in receipt["rows"]:
            page.add(
                receipt["id"], row["visit"], "held", "both", "status", row["status"], "status", name
            )
            for mode, calls in row.get("timings", {}).items():
                for i, call in enumerate(calls, 1):
                    for metric, value in (
                        ("detector_cpu", call["detector_cpu_ms"]),
                        ("detector_wall", 1000 * call["wall_s"]),
                        ("coarse_cpu", sum(rx["coarse"] for rx in call["rows"])),
                    ):
                        page.add(
                            receipt["id"],
                            f"{row['visit']}/{i}",
                            "held",
                            mode,
                            metric,
                            value,
                            "ms",
                            name,
                        )
    for row in q["actual_coarse_cells"]:
        for rx in row["receivers"]:
            for mode, key in (("control", "full_cells"), ("stride", "stride_cells")):
                page.add(
                    row["id"],
                    f"{row['visit']}/RX{rx['receiver']}",
                    "engineering",
                    mode,
                    "coarse_cells",
                    rx[key],
                    "cells",
                    qualification,
                )
    modes = q["held"]["modes"]
    page.plot(
        "Held calls",
        "Median elapsed (ms)",
        ["Detector CPU", "Wall"],
        [tuple(modes[m][f"median_{k}_ms"] for m in ("control", "stride")) for k in ("cpu", "wall")],
    )
    page.plot(
        "Coarse CPU pooled by capture",
        "CPU (ms)",
        list(q["independent_cases"]),
        [
            tuple(r["modes"][m]["stages_cpu_ms"]["coarse"] for m in ("control", "stride"))
            for r in q["independent_cases"].values()
        ],
    )
    return page


def carry(root):
    study, initial, cycle = "epoch-carry", "scores.json", "cycle/scores.json"
    data, hashes = sealed(root / study, "audit-lock.json", (initial, cycle))
    q = data[cycle]
    cases = q["cases"]
    counts = q["aggregate"]["coverage"]
    page = Page(
        "epoch-carry",
        "Pilot epoch carry across retunes",
        study,
        f"{len(cases)} full-waveform recordings · {counts['processed_probe']:,} receiver probes",
        "Saved wide IQ factors → causal timing forecasts",
        f"The 120 ms rule yielded no forecasts. The 400 ms rule made {counts['forecast_probe']:,}. "
        f"All {counts['missed_wide_with_forecast']} forecasted missed targets had same-lane "
        "timing error above 1,000 samples.",
        hashes,
        ("Same-lane forecast", "Wrong-time control"),
    )
    for source in (initial, cycle):
        for group, quantities in data[source]["groups"].items():
            case, kind = group.split("/", 1)
            for metric, n in quantities.items():
                page.add(
                    case,
                    "",
                    "120 ms" if source == initial else "400 ms",
                    kind,
                    metric,
                    n,
                    "count",
                    source,
                )
    comparison = [
        q["aggregate"][f"missed_wide/{mode}/epoch/common_null"] for mode in ("own", "wrong_time")
    ]
    page.plot(
        "Forecasts at matched missed targets",
        f"Receiver probes ({sum(comparison[0].values())} common per method)",
        ["≤20 samples", "21–100", "101–1,000", ">1,000"],
        [tuple(c.get(k, 0) for c in comparison) for k in ("20", "100", "1000", "above_1000")],
        fmt="d",
    )
    paired = {
        case: [
            q["groups"].get(f"{case}/missed_wide/{mode}/epoch/common_null", {})
            for mode in ("own", "wrong_time")
        ]
        for case in cases
    }
    page.plot(
        "Large errors in the common subset",
        "Receiver probes above 1,000 samples",
        [f"{case} ({sum(pair[0].values())})" for case, pair in paired.items()],
        [tuple(c.get("above_1000", 0) for c in pair) for pair in paired.values()],
        fmt="d",
    )
    counts_to_export = [
        ("Forecasters", counts["forecast_probe"], "400 ms"),
        ("Matched capture-era missed targets", counts["missed_wide_with_forecast"], "400 ms"),
        ("Same-lane recovered within ±1 sample", 0, "400 ms"),
    ]
    for label, n, condition in counts_to_export:
        page.add(
            "All eight recordings",
            "",
            condition,
            "same-lane",
            label,
            n,
            "receiver probes",
            cycle,
            counts["processed_probe"],
        )
    return page


def stride_arm(root):
    study, qual, controls = "stride-arm", "qualification.json", "controls.json.gz"
    manifest = stage.read(root / study / "prediction-lock.json")
    files = tuple(f"{case}.json.gz" for case in manifest["cases"])
    data, hashes = sealed(root / study, "prediction-lock.json", (qual, controls, *files))
    q = data[qual]
    page = Page(
        "cfo-stride-cortex-a9",
        "CFO stride under Cortex-A9 emulation",
        study,
        f"{q['admitted']}/{q['scheduled']} held visits · {len(files)} recordings",
        "Saved IQ → wide detector under QEMU on a pinned x86 host CPU",
        "Both builds matched all eight archived positives. These costs describe QEMU "
        "execution on the x86 host, with no physical ARM throughput measurement.",
        hashes,
        ("Full 21-bin bank", "Stride and repair"),
    )
    modes = ("control", "stride")
    for f in files:
        receipt = data[f]
        for r in receipt["rows"]:
            page.add(receipt["id"], r["visit"], "held", "both", "status", r["status"], "status", f)
            for mode, calls in r.get("timings", {}).items():
                for i, c in enumerate(calls, 1):
                    for key, value in (
                        ("detector_cpu", c["detector_cpu_ms"]),
                        ("external_wall", c["external_wall_s"] * 1000),
                        ("coarse_cpu", sum(rx["coarse"] for rx in c["rows"])),
                    ):
                        page.add(
                            receipt["id"], f"{r['visit']}/{i}", "held", mode, key, value, "ms", f
                        )
        for mode, profile in receipt["warm_profile"].items():
            for i, sample in enumerate(profile["calls"], 1):
                for key, value in sample.items():
                    page.add(
                        receipt["id"],
                        f"{receipt['warm_visit']}/{i}",
                        "reused context",
                        mode,
                        key,
                        value,
                        "ms",
                        f,
                    )
    for control, row in q["control_positive_counts"].items():
        for mode in modes:
            for rx, value in enumerate(row[mode]):
                page.add(
                    control, f"RX{rx}", "control", mode, "positive_candidates", value, "count", qual
                )
    page.plot(
        "Cold emulated detector",
        "Pooled CPU (ms)",
        ["Complete detector", "Regional coarse"],
        [tuple(q["modes"][mode][k] for mode in modes) for k in ("cpu_ms", "coarse_ms")],
    )
    cases = [data[f]["id"] for f in files]
    page.plot(
        "Reused emulated contexts",
        "Median steady CPU (ms)",
        cases,
        [
            tuple(q["modes"][mode]["warm"][case]["steady_cpu_ms"] for mode in modes)
            for case in cases
        ],
    )
    return page


def scope_title(root):
    return (
        TITLE
        if root.name == ROOT.name
        else f"{root.name.replace('-', ' ').capitalize()} measurements"
    )


def stage_specs(root, *, descriptors=None):
    panels = []
    if descriptors is None:
        panels = [(p, None) for p in AUTHORED_STAGES if (root / p.id / p.seal).is_file()]
        descriptors = sorted(root.rglob(STAGE_SPEC))
    for path in descriptors:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"{path} resolves outside the evidence directory")
        spec = stage.read(path)
        required = ("version", "id", "title", "sample", "boundary", "note", "seal", "image", "csv")
        profile = {"profile_image", "profile_csv", "profile_pdf"}
        position._require_keys(spec, required, ("pdf", *profile))
        profile_fields = spec.keys() & profile
        if (
            spec["version"] != 1
            or any(
                not isinstance(spec[k], str) or not spec[k].strip()
                for k in (*required, *profile_fields)
                if k != "version"
            )
            or (profile_fields and profile_fields != profile)
            or position.NAME.fullmatch(spec["id"]) is None
        ):
            raise ValueError(f"invalid stage figure descriptor {path}")
        panel = AuthoredStage(
            spec["id"],
            spec["title"],
            spec["sample"],
            spec["boundary"],
            spec["note"],
            seal=spec["seal"],
            source_png=spec["image"],
            source_csv=spec["csv"],
            source_pdf=spec.get("pdf"),
        )
        if not position._local(path.parent, panel.seal).is_file():
            continue
        current = [panel]
        if profile_fields:
            current.append(
                replace(
                    panel,
                    id=f"{panel.id}-profile",
                    title=f"{panel.title} · Stage profile",
                    sample="Separate instrumented detector runs",
                    source_png=spec["profile_image"],
                    source_csv=spec["profile_csv"],
                    source_pdf=spec["profile_pdf"],
                )
            )
        for entry in current:
            if entry.id in {p.id for p, _ in panels}:
                raise ValueError(f"duplicate stage figure {entry.id}")
            panels.append((entry, path))
    return panels


def add_authored_stage(root, out, book, panel, descriptor=None):
    label = panel.id
    folder = root / label if descriptor is None else descriptor.parent
    lock = position._local(folder, panel.seal).read_bytes()
    png, pdf, table = (f"{label}.{ext}" for ext in ("png", "pdf", "csv"))
    sources = {png: panel.source_png or png, table: panel.source_csv or table}
    original_pdf = pdf if descriptor is None else panel.source_pdf
    if original_pdf is not None:
        sources[pdf] = original_pdf
    receipt = json.loads(lock)["files"]
    data = {name: position._local(folder, source).read_bytes() for name, source in sources.items()}
    hashes = {name: sha256(payload).hexdigest() for name, payload in data.items()}
    if any(receipt.get(source) != hashes[name] for name, source in sources.items()):
        raise ValueError(f"{label} assets differ from the sealed stage results")
    source_paths = {str((folder / panel.seal).relative_to(root)): sha256(lock).hexdigest()}
    source_paths.update(
        {str((folder / name).relative_to(root)): hashes[key] for key, name in sources.items()}
    )
    if descriptor is not None:
        digest = stage.sha(descriptor)
        if receipt.get(descriptor.name, digest) != digest:
            raise ValueError(f"{label} descriptor differs from the sealed stage results")
        source_paths[str(descriptor.relative_to(root))] = digest
    rows = csv.DictReader(io.StringIO(data[table].decode("utf-8")))
    if not any(any(row.values()) for row in rows):
        raise ValueError(f"{label} stage CSV has no measured rows")
    for name, payload in data.items():
        write(out / name, payload)
    raster = stage.plt.imread(out / png)
    figure = stage.plt.figure(figsize=(13.5, 13.5 * raster.shape[0] / raster.shape[1]), dpi=160)
    ax = figure.add_axes([0, 0, 1, 1])
    ax.imshow(raster, interpolation="none")
    ax.set_axis_off()
    book.savefig(figure, facecolor="white")
    stage.plt.close(figure)
    manifest = dict(
        id=label,
        title=panel.title,
        image=png,
        csv=table,
        sample=panel.sample,
        boundary=panel.boundary,
        sources=source_paths,
        artifact_sha256=hashes,
    )
    if original_pdf is not None:
        manifest["stage_pdf"] = pdf
    row = index.Row(
        label,
        label,
        panel.title,
        "Measured stage evidence",
        panel.boundary,
        "Stage",
        "stage",
        "Chart ready",
        panel.sample,
        chart=f"stage-charts/{png}",
        evidence=f"stage-charts/{table}",
        report=index.report_link(folder, root),
        notes=panel.note,
    )
    return row, manifest


def stage_book(root, destination=None, *, panels=None):
    destination = root if destination is None else destination
    out = destination / "stage-charts"
    studies = (
        ("screened-detector/SHA256SUMS", screened, (False,)),
        ("screened-detector/SHA256SUMS", screened, (True,)),
        ("cfo-stride/prediction-lock.json", stride_host, ()),
        ("epoch-carry/audit-lock.json", carry, ()),
        ("epoch-carry/audit-lock.json", envelope, ()),
        ("complete-epoch-proxy/evidence-lock.json", proxy, ()),
        ("stride-arm/prediction-lock.json", stride_arm, ()),
    )
    pages = []
    if panels is None:
        pages = [
            build(root, *args) for receipt, build, args in studies if (root / receipt).is_file()
        ]
        panels = stage_specs(root)
    if not pages and not panels:
        return [], []
    image_rows, manifest, measurements = [], [], []
    pdf = io.BytesIO()
    legacy = root.name == ROOT.name
    book_title = (
        "Receiver-core detector stages" if legacy else f"{scope_title(root)} · Stage evidence"
    )
    with PdfPages(pdf, metadata=dict(Title=book_title, CreationDate=None)) as book:
        for p in pages:
            f, axes = stage.canvas(p.title, p.sample, p.note)
            for ax, (title, unit, labels, values, fmt) in zip(axes, p.plots, strict=True):
                stage.paired(ax, labels, values, title=title, xlabel=unit, fmt=fmt)
            stage.key(f, *p.series)
            img, data = f"{p.id}.png", f"{p.id}.csv"
            png = io.BytesIO()
            f.savefig(png, format="png", dpi=160, facecolor="white")
            write(out / img, png.getvalue())
            book.savefig(f, facecolor="white")
            stage.plt.close(f)
            write(out / data, export.table(p.rows))
            measurements.extend(p.rows)
            manifest.append(
                dict(
                    id=p.id,
                    title=p.title,
                    image=img,
                    csv=data,
                    sample=p.sample,
                    boundary=p.boundary,
                    sources={f"{p.study}/{k}": v for k, v in p.sources.items()},
                    artifact_sha256={name: stage.sha(out / name) for name in (img, data)},
                )
            )
            image_rows.append(
                index.Row(
                    p.id,
                    p.id,
                    p.title,
                    "Saved detector evidence",
                    p.boundary,
                    "Stage",
                    "stage",
                    "Chart ready",
                    p.sample,
                    chart=f"stage-charts/{img}",
                    evidence=f"stage-charts/{data}",
                    report=index.report_link(root / p.study, destination),
                    notes=p.note,
                )
            )
        for panel, descriptor in panels:
            row, page = add_authored_stage(root, out, book, panel, descriptor)
            if row.report and destination != root:
                row = replace(row, report=index.relative(root / row.report, destination))
            image_rows.append(row)
            manifest.append(page)
    write(out / stage.BOOK, pdf.getvalue())
    if measurements:
        write(out / "measurements.csv", export.table(measurements))
    save_json(
        out / "manifest.json",
        dict(
            version=1,
            pages=manifest,
            book=stage.BOOK,
            measurements="measurements.csv" if measurements else None,
        ),
    )
    lines = [
        "# Receiver-core detector and acquisition stages" if legacy else f"# {book_title}",
        "",
        "[Combined PDF](stage-evidence.pdf) · [Source and artifact hashes](manifest.json)",
        "",
        (
            "Each page links measured data for one detector or timing change. Matched native x86 "
            "and Cortex-A9 QEMU timings appear on separate pages."
            if legacy
            else "Each page links measured data from a named stage. "
            "Position charts use a separate index."
        ),
        "",
    ]
    for page in manifest:
        lines.append(f"- {page['title']} · [PNG]({page['image']}) · [CSV]({page['csv']})")
    if measurements:
        lines.extend(
            ("", "[Long-form values for the paired detector charts](measurements.csv)", "")
        )
    write(out / "README.md", "\n".join(lines).encode())
    return image_rows, manifest


def position_attempted(chart):
    """Retain scheduled prediction outcomes, including failure before refinement."""
    key = "one" if chart.scope == "roof" else "candidate"
    return any(
        r["result"]["metrics"].get("position_attempted") is not False
        or terminal_position_decision(r["result"])
        or (chart.version == 2 and r["result"].get("status") in POSITION_FAILURES)
        for r in chart.predictions[key].values()
    )


def position_book(root, destination=None, models=None, *, fit_titles=False):
    destination = root if destination is None else destination
    if models is None:
        if not position.available(root):
            return [], []
        models = position.charts(evidence=root)
    if root.name != ROOT.name:
        models = [model for model in models if position_attempted(model)]
    if not models:
        return [], []
    out = destination / "charts"
    figures = position.shared.render(
        out,
        ARMS,
        lambda arm: [c.page(arm) for c in models],
        title=scope_title(root),
        fit_titles=fit_titles,
    )
    atlas.write_index(
        out,
        [atlas.screening_section(figures, ARMS, folder=".")],
        ARMS,
        description="Exact scheduled recording and offer rosters for each receiver change.",
    )
    charts = {(r["id"], r["arm"]): r for r in figures}
    specs = {
        s["id"]: (f.parent, s["seal"])
        for f in sorted(root.rglob(position.SPEC))
        for s in stage.read(f)["charts"]
    }
    lines = []
    for model in models:
        key = "one" if model.scope == "roof" else "candidate"
        candidate = model.predictions[key]
        folder, seal = specs[model.id]
        relative = folder.relative_to(root).parts
        study = root / relative[0] if relative else root
        n = len(model.cases)
        captures = (
            len({r["recording"] for r in model.references.values()})
            if model.scope == "transfer"
            else n
        )
        sample = (
            f"{n} scheduled recordings"
            if model.scope == "roof"
            else f"{n} offers · {captures} recordings or scenes"
        )
        for arm in ARMS:
            counts = index.outcome([r["result"] for r in candidate.values()], arm)
            terminals = []
            for case, row in candidate.items():
                result = row["result"]
                endpoint = result.get("arms", {}).get(arm, {})
                status, reason = arm_outcome(result, endpoint)
                explicit = terminal_position_decision(result)
                if status in POSITION_FAILURES or explicit:
                    detail = f" ({reason})" if explicit or model.version == 2 else ""
                    terminals.append(f"{case} {status}{detail}")
            lines.append(
                index.Row(
                    model.method,
                    model.id,
                    model.title,
                    model.scope,
                    "Sealed position replay",
                    "Position",
                    arm,
                    "Chart ready",
                    sample,
                    scheduled=n,
                    chart=f"charts/{charts[model.id, arm]['image']}",
                    evidence=index.relative(folder / seal, destination),
                    report=index.report_link(study, destination),
                    notes=model.caption,
                    terminal_exceptions=" · ".join(terminals),
                    **counts,
                )
            )
    return lines, figures


def gallery_index(rows, links, title=TITLE):
    html = (
        index.page(rows, links)
        .replace("Acquisition and receiver evidence", title)
        .replace("Acquisition-stage results", "Detector and acquisition stages")
    )
    if title == "Receiver deadline measurements":
        html = html.replace("Detector and acquisition stages", "Stage measurements and timing")
        html = html.replace(
            "Stage plots measure detector behavior.",
            "The stage plots identify the observed or modeled boundary for each result.",
        )
    html = html.replace(' · <a href="#original">Original ten</a>', "").replace(
        '<section id="original"><h2>Original ten</h2><div class="grid"></div></section>', ""
    )
    if all(row.arm == "stage" for row in rows):
        html = html.replace('<a href="#position">Position results</a> · ', "").replace(
            '<section id="position"><h2>Position results</h2><div class="grid"></div></section>', ""
        )
    return html


def portable_zip(files):
    out = io.BytesIO()
    with ZipFile(out, "w") as result:
        for name, content in sorted(files.items()):
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError(f"ZIP path escapes the pack: {name}")
            result.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)
    return out.getvalue()


def build(root=ROOT, *, out=None, models=None, downloads=None, stage_panels=None, fit_titles=False):
    root = local_output(root)
    out = root if out is None else local_output(out)
    if stage_panels is None:
        staged, stage_manifest = stage_book(root, out)
    else:
        staged, stage_manifest = stage_book(root, out, panels=stage_panels)
    if fit_titles:
        positioned, position_manifest = position_book(root, out, models, fit_titles=True)
    else:
        positioned, position_manifest = position_book(root, out, models)
    rows = [*positioned, *staged]
    title = scope_title(root)
    names = [r.chart for r in rows]
    if not names or len(names) != len(set(names)):
        raise ValueError("the evidence must supply distinct ready PNGs")
    charter = "chart-inventory.csv"
    links, names = dict(downloads or {}), set(names)
    names.update(links.values())
    if staged:
        for label, file in (
            ("Per-stage measurement index", "README.md"),
            ("Stage chart book", stage.BOOK),
        ):
            links[label] = f"stage-charts/{file}"
        names.update(f"stage-charts/{r['csv']}" for r in stage_manifest)
        names.update(f"stage-charts/{r['stage_pdf']}" for r in stage_manifest if "stage_pdf" in r)
        names.update(("stage-charts/manifest.json", *links.values()))
        if (out / "stage-charts/measurements.csv").is_file():
            names.add("stage-charts/measurements.csv")
    if positioned:
        paths = {out / "charts" / r["csv"] for r in position_manifest}
        arm_panels = {(r.arm, r.panel_id) for r in positioned}
        write(out / "positions.csv", export.observations(arm_panels, sorted(paths)))
        links.update(
            {
                "Calibration-switch gallery": "charts/index.html",
                "All position values": "positions.csv",
            }
        )
        names.update(f"charts/{r[key]}" for key in ("pdf", "csv") for r in position_manifest)
        names.update(("charts/index.html", "charts/manifest.json", "positions.csv"))
    write(out / charter, export.table([asdict(r) for r in rows]))
    live_links = links | {"Download offline ZIP": ZIP}
    board_audit = "board-replay/README.md"
    if board_link := index.relative(root / board_audit, out):
        live_links["Board access audit"] = board_link
    write(out / "index.html", gallery_index(rows, live_links, title).encode())
    local = [
        replace(r, report="", evidence=r.evidence if r.arm == "stage" else "positions.csv")
        for r in rows
    ]
    files = {name: (out / name).read_bytes() for name in names}
    checksums = "artifact-sha256.json"
    files["index.html"] = gallery_index(
        local, links | {"Archive hashes": checksums}, title
    ).encode()
    files[charter] = export.table([asdict(r) for r in local])
    files[checksums] = (
        encoded(
            dict(files={name: sha256(data).hexdigest() for name, data in sorted(files.items())})
        )
        + b"\n"
    )
    write(out / ZIP, portable_zip(files))
    sources = {name: stage.sha(out / name) for name in sorted(names | {ZIP, charter, "index.html"})}
    roster = {
        k: sorted({r.panel_id for r in rows if (r.arm == "stage") == (k == "stage")})
        for k in ("stage", "position")
    }
    save_json(
        out / "pack-lock.json",
        dict(
            version=1,
            files=sources,
            panels=roster,
            stage_pages=len(staged),
            position_pages=len(positioned),
            source_sha256=stage.sha(Path(__file__)),
        ),
    )
    return rows


def envelope(root):
    study, name = "epoch-carry", "envelope/scores.json"
    data, hashes = sealed(root / study, "audit-lock.json", (name,))
    rows = data[name]["rows"]
    real = [r for r in rows if r["condition"] == "recorded"]
    targets = sum(r["teacher_candidates"] for r in real)
    page = Page(
        "amplitude-envelope",
        "CFO-invariant pilot power envelope",
        study,
        f"{len(real)} real dual-RX windows · {targets} archived starts",
        "Saved IQ → shadow fourth scout slot compared with the ordinary C scout",
        "The independent envelope changed none of 32 real receiver lists. It changed one "
        "of four planted lists without losing a planted start. Both noise windows were unchanged.",
        hashes,
        ("Ordinary four starts", "Envelope challenger"),
    )
    for r in rows:
        for mode, k in (("stock", "ordinary_scout_cpu_ms"), ("alternate", "prototype_cpu_ms")):
            page.add(r["id"], r["visit"], r["condition"], mode, "scout_cpu", r[k], "ms", name)
            for radius, n in r["coverage"][mode].items():
                page.add(
                    r["id"],
                    r["visit"],
                    r["condition"],
                    mode,
                    f"coverage_{radius}_samples",
                    n,
                    "target starts",
                    name,
                    r["teacher_candidates"],
                )
        page.add(
            r["id"],
            r["visit"],
            r["condition"],
            "alternate",
            "changed_lists",
            r["replaced"],
            "receiver lists",
            name,
            2,
        )
    page.plot(
        "Archive starts in scout ranges",
        f"Target starts ({targets} archived)",
        ["±1 sample", "±2 samples"],
        [
            tuple(sum(r["coverage"][m][k] for r in real) for m in ("stock", "alternate"))
            for k in ("1", "2")
        ],
        fmt="d",
    )
    page.plot(
        "Causal score cost",
        "Median CPU per dual-RX window (ms)",
        ["Recorded IQ"],
        [tuple(median(r[k] for r in real) for k in ("ordinary_scout_cpu_ms", "prototype_cpu_ms"))],
    )
    return page


def proxy(root):
    study, qual = "complete-epoch-proxy", "qualification.json"
    manifest = stage.read(root / study / "evidence-lock.json")
    files = tuple(f"{case}.json.gz" for case in manifest["cases"])
    data, hashes = sealed(root / study, "evidence-lock.json", (qual, *files))
    q = data[qual]
    page = Page(
        "complete-epoch-proxy",
        "Complete-epoch 18-tap proposal",
        study,
        f"{q['real_visits']} matched visits · {len(files)} recordings · 20 calls per method",
        "Saved IQ → short-tap proposal and exact rescoring → detector",
        "All original cells were visited at short-tap precision. The cap of 96 retained "
        "29 of 160 original coarse keys. Exact rescoring could not restore missing nominations.",
        hashes,
        ("Capture-era detector", "18-tap proposal"),
    )
    for f in files:
        receipt = data[f]
        for row in receipt["rows"]:
            page.add(
                receipt["id"], row["visit"], "recorded", "all", "status", row["status"], "status", f
            )
            for i, pair in enumerate(row.get("pairs", ()), 1):
                for mode, sample in pair["modes"].items():
                    clock = sample.get("stage_cpu_ms", {})
                    if isinstance(clock, list):
                        clock = {k: sum(rx[k] for rx in clock) for k in clock[0]}
                    for key, value in dict(
                        cpu=sample["cpu_ms"],
                        wall=sample["wall_ms"],
                        **clock,
                    ).items():
                        page.add(
                            receipt["id"],
                            f"{row['visit']}/{i}",
                            "recorded",
                            "proxy18" if mode == "thinned" else mode,
                            key,
                            value,
                            "ms",
                            f,
                        )
    cases = q["cases"]
    page.plot(
        "Original coarse keys retained",
        "Original keys (per-capture counts)",
        list(cases),
        [tuple(c["basins"][k] for k in ("original", "covered_cap96")) for c in cases.values()],
        fmt="d",
    )
    page.plot(
        "Complete hosted detector",
        "Median elapsed (ms)",
        ["CPU", "Wall"],
        [
            tuple(q["timing"][m][f"median_{clock}_ms"] for m in ("capture", "proxy18"))
            for clock in ("cpu", "wall")
        ],
    )
    return page


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--evidence", type=local_output, default=ROOT)
    args = cli.parse_args()
    rows = build(args.evidence)
    print(f"{len(rows)} individual PNGs and their measurement tables in {args.evidence / ZIP}")


if __name__ == "__main__":
    main()
