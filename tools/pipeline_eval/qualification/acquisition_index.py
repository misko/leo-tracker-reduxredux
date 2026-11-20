"""Audit acquisition-support charts against their actual sealed evidence."""

import argparse
import csv
import gzip
import io
import json
import os
from dataclasses import asdict, dataclass
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import quote

from ..__main__ import ROOT, write
from ..scoring import arm_outcome, terminal_position_decision

ACQUISITION = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support"
ATLAS = ROOT / "reports/2026_11_19_position_atlas"
ARMS = ("fitted_c", "c0")
LABELS = {"fitted_c": "Fitted c", "c0": "c = 0", "stage": "Stage only"}
TEN = {
    "v5_lean": ("Remove evidence rendering", "Saved native GLRT → original v5 numerical fit."),
    "glrt_batch": ("Batch the pilot bank", "80 saved IQ windows per recording → GLRT and fit."),
    "iq_stream": ("Stream IQ decoding", "80 saved IQ windows per recording → GLRT and fit."),
    "glrt_cascade": ("Screen pilot candidates early", "80 saved IQ windows → gated GLRT and fit."),
    "orbit_interp": ("Reuse orbital states", "Shared orbital states → single- and four-tile fit."),
    "shape_score": ("Screen below-horizon satellites", "Doppler tracks → gated orbit fit."),
    "track_reduce": ("Compress Doppler tracks", "Prepared tracks → compressed track position fit."),
    "track_link": ("Link GLRT peaks causally", "Saved native GLRT → causal tracks and local fit."),
    "iq_position": ("Fit bounded IQ replay", "80 saved IQ windows → GLRT, tracks and fit."),
    "projected_fit": ("Project out track frequency levels", "Prepared tracks → projected fit."),
}


@dataclass(frozen=True)
class Scope:
    modification: str
    cohort: str
    boundary: str
    panel_type: str = "Position"


@dataclass(frozen=True)
class Row:
    modification: str
    panel_id: str
    title: str
    cohort: str
    boundary: str
    panel_type: str
    arm: str
    state: str
    sample: str
    scheduled: int | None = None
    published: int | None = None
    forced_available: int | None = None
    withheld: int | None = None
    failed: int | None = None
    timed_out: int | None = None
    unavailable: int | None = None
    missing: int | None = None
    stage_only: int | None = None
    chart: str = ""
    evidence: str = ""
    report: str = ""
    terminal_exceptions: str = ""
    comparison_failures: str = ""
    notes: str = ""


ROOF = "Measured one-roof archive"
RF = "Historical measured capture-detector IQ"
FIELD = "Measured StarLoc field sites"
SYNTH = "Synthetic transfer sites"
SCOPES = {
    "capture-fft": Scope("capture-fft", RF, "Saved visits → installed detector response", "Stage"),
    "deadline-repeat": Scope(
        "scout-centers", ROOF, "Full saved CI16 → wide GLRT → compact fit", "Deadline repeat"
    ),
    "derivative-receiver": Scope(
        "polynomial-derivatives",
        ROOF,
        "Saved GLRT → anonymous Doppler derivatives → regional decision",
    ),
    "field-anonymous": Scope(
        "field-shared-drift",
        FIELD,
        "Released FFT-beacon Doppler and causal TLE → location decision",
    ),
    "fit-work": Scope("fit-work", ROOF, "Saved narrow factors → constrained cavity fit"),
    "folded-bank": Scope("folded-bank", RF, "Saved fold → complete coarse score bank", "Stage"),
    "fresh-waveform": Scope(
        "wide-four-center", ROOF, "Full saved CI16 → wide GLRT → compact fit", "Confirmation"
    ),
    "outside-predictive": Scope(
        "outside-predictive", ROOF, "Saved native GLRT → disjoint Graph fits → exterior test"
    ),
    "peak-null": Scope("rolled-pilot-ranking", ROOF, "Wide factors → causal re-rank → compact fit"),
    "peak-support": Scope(
        "shared-peak-support",
        ROOF,
        "Capture-era, narrow and wide factors → matched subsets → compact fit",
        "Position diagnostic",
    ),
    "phase-scout": Scope(
        "signed-scout-phase", ROOF, "Saved dual RX IQ → signed scout detector", "Stage"
    ),
    "radius-full": Scope("scout-radius", ROOF, "Full saved CI16 → wide GLRT → compact fit"),
    "scout-budget": Scope("scout-centers", ROOF, "Saved dual RX IQ → wide GLRT slate", "Stage"),
    "scout-full": Scope("scout-centers", ROOF, "Full saved CI16 → wide GLRT → compact fit"),
    "scout-radius": Scope("scout-radius", ROOF, "Saved dual RX IQ → wide GLRT slate", "Stage"),
    "selective-capture": Scope(
        "selective-capture",
        ROOF,
        "Wide/capture-era factors → whole-visit substitution → compact fit",
    ),
    "thinned-capture": Scope("thinned-capture", RF, "Saved visits → installed detector", "Stage"),
    "winner-stream": Scope("winner-stream", ROOF, "Wide GLRT → private winner handoff → fit"),
    "fractional-runtime": Scope(
        "ordered-fractional", ROOF, "Saved 20 ms IQ → ordinary native fractional response", "Stage"
    ),
}

# Stage-only rows have source receipts even when their shared figure book is still being built.
STAGES = (
    (
        "folded-bank",
        "folded-bank",
        "Shared overlap-save FFT acquisition bank",
        "1 real 20 ms first-RX window and 2 synthetic controls",
        "receipt.json",
    ),
    (
        "capture-fft",
        "capture-fft",
        "Exhaustive FFT grid in installed capture detectors",
        "8 scheduled dual-RX visits across 2 different capture releases, plus controls",
        "detector-lock.json",
    ),
    (
        "thinned-capture",
        "thinned-capture",
        "Two-frame, four-anchor proposal with full rescore",
        "10 admitted dual-RX visits across 4 recordings, 1 retained exclusion",
        "evidence-lock.json",
    ),
    (
        "phase-scout",
        "phase-scout",
        "Signed differential phase to narrow the CFO grid",
        "16 complete dual-RX windows across 2 recordings, plus plants and nulls",
        "prediction-lock.json",
    ),
    (
        "phase-scout",
        "phase-scout-coherent",
        "Coherent odd/even phase shortlist",
        "512 real neighborhoods from the same 16 windows, plus 192 strong planted neighborhoods",
        "coherent-lock.json",
    ),
    (
        "scout-budget",
        "scout-budget",
        "Sixteen distinct scout centers instead of four",
        "23 admitted dual-RX visits across 2 recordings, 113 paired warm calls",
        "prediction-lock.json",
    ),
    (
        "scout-radius",
        "scout-radius",
        "Two samples around each of four scout centers",
        "23 admitted dual-RX visits across 2 recordings, 113 paired warm calls",
        "prediction-lock.json",
    ),
)


def local(folder, name):
    path = (folder / name).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError(f"evidence path leaves study directory: {name}")
    return path


def read_json(path):
    return json.loads(path.read_bytes())


def matches(path, digest):
    return path.is_file() and sha256(path.read_bytes()).hexdigest() == digest


def relative(path, out):
    return Path(os.path.relpath(path, out)).as_posix() if path.is_file() else ""


def report_link(folder, out):
    return relative(folder / "README.md", out) or relative(folder / "PROTOCOL.md", out)


def rendered(root):
    """Prefer the common renderer's output when both local and aggregate images exist."""
    aggregate = root / "charts" / "manifest.json"
    found = {}
    for path in sorted(root.rglob("manifest.json"), key=lambda p: (p == aggregate, p)):
        if path.parent.name not in {"charts", "plots"}:
            continue
        manifest = read_json(path)
        for page in manifest if isinstance(manifest, list) else []:
            image = local(path.parent, page["image"])
            if image.is_file():
                found[page["id"], page["arm"]] = image
    for panel in ("reserve", "field"):
        for arm in ARMS:
            path = root / "derivative-receiver" / f"{panel}-{arm}.png"
            if path.is_file():
                found.setdefault((f"derivative_receiver-{panel}", arm), path)
    for arm in ARMS:
        path = root.parent / "streamlined" / "charts" / arm / "fractional_runtime_position.png"
        if path.is_file():
            found.setdefault(("fractional_runtime_position", arm), path)
    return found


def endpoint_rows(folder, spec, series):
    seal = read_json(local(folder, spec["seal"]))
    planned = seal["cases"]
    if len(set(planned)) != len(planned):
        raise ValueError("repeated scheduled query in figure seal")
    if isinstance(spec["cases"], list) and set(spec["cases"]) != set(planned):
        raise ValueError("figure descriptor and seal schedule differ")
    path = local(folder, series["file"])
    if not matches(path, seal["files"].get(series["file"])):
        raise ValueError("prediction bytes differ from figure seal")
    query = {series.get("field", "method"): series["value"]} | series.get("where", {})
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        rows = [r for r in map(json.loads, stream) if all(r.get(k) == v for k, v in query.items())]
    received = {r["id"] for r in rows}
    if len(received) != len(rows) or received != set(planned):
        raise ValueError("positions do not cover the sealed roster exactly")
    sample = f"{len(planned)} recording" + ("" if len(planned) == 1 else "s")
    if name := spec.get("queries"):
        queries = local(folder, name)
        if not matches(queries, seal["files"].get(name)):
            raise ValueError("geographic query bytes differ from figure seal")
        offered = read_json(queries)["queries"]
        if len(offered) != len(planned) or {q["id"] for q in offered} != received:
            raise ValueError("geographic queries do not cover the sealed roster exactly")
        recordings = len({q["recording"] for q in offered})
        offers = f"{len(planned)} offer" + ("" if len(planned) == 1 else "s")
        units = "recording or scene" if recordings == 1 else "recordings or scenes"
        sample = f"{offers} · {recordings} {units}"
    return len(planned), sample, rows


def outcome(results, arm):
    counts = dict.fromkeys(
        (
            "published",
            "forced_available",
            "withheld",
            "failed",
            "timed_out",
            "unavailable",
            "missing",
            "stage_only",
        ),
        0,
    )
    for result in results:
        endpoint = result.get("arms", {}).get(arm, {})
        status, _ = arm_outcome(result, endpoint)
        genuine = result.get("metrics", {}).get("position_attempted") is not False
        if endpoint.get("latlon") is not None:
            if not genuine or status != "ok":
                raise ValueError("published coordinate on an unmeasured or unsuccessful arm")
            counts["published"] += 1
        elif status in {"failed", "timed_out", "missing", "unavailable"}:
            counts[status] += 1
        elif not genuine and not terminal_position_decision(result):
            counts["stage_only"] += 1
        elif status in {"ok", "withheld"}:
            counts["withheld"] += 1
        else:
            raise ValueError(f"unknown prediction status {status}")
        if endpoint.get("forced_latlon") is not None:
            if not genuine or status not in {"ok", "withheld"}:
                raise ValueError("forced coordinate on an unmeasured or unsuccessful arm")
            counts["forced_available"] += 1
    return counts


def scope_for(folder, panel):
    scope = SCOPES.get(folder, Scope(folder, "See sealed cohort", "See study protocol"))
    panel = panel.removesuffix("-curvature-only")
    if folder == "fit-work" and panel == "constrained-cavity-phase-fit-work-held-ds29-0357":
        return Scope(scope.modification, ROOF, "Saved capture-era factors → constrained cavity fit")
    if folder == "capture-fft":
        return Scope(
            "capture-fft",
            RF,
            "Four substituted IQ visits per recording → full capture-era factors → fit",
            "Position diagnostic",
        )
    if folder == "fractional-runtime":
        return Scope(
            scope.modification,
            ROOF,
            "12 substituted IQ visits and remaining saved ordinary factors → position",
            "Prior position",
        )
    if folder == "derivative-receiver" and panel.endswith("-field"):
        return Scope(scope.modification, FIELD, "Prepared measured tones → derivative orbit search")
    if panel.endswith(("-simulated", "-fresh-synthetic")):
        return Scope(scope.modification, SYNTH, scope.boundary)
    return scope


def positions(root, images):
    manifests = sorted(root.rglob("figures.json"))
    former = root.parent / "streamlined" / "fractional-runtime" / "figures.json"
    if former.is_file():
        manifests.append(former)
    for manifest in manifests:
        folder = manifest.parent
        study = folder if manifest == former else root / folder.relative_to(root).parts[0]
        for spec in read_json(manifest)["charts"]:
            if spec.get("scope") not in {"roof", "transfer"}:
                continue
            panel = spec["id"]
            if manifest == former and panel != "fractional_runtime_position":
                continue
            scope = scope_for(study.name, panel)
            candidate = "one" if spec["scope"] == "roof" else "candidate"
            (primary,) = [s for s in spec["series"] if s["key"] == candidate]
            mod = (
                "polynomial-curvature-only"
                if primary["value"] == "polynomial_curvature_only"
                else scope.modification
            )
            title = spec["title"]
            try:
                archives = [(s, endpoint_rows(folder, spec, s)) for s in spec["series"]]
                scheduled, sample, data = next(e for s, e in archives if s == primary)
                results = [r["result"] for r in data]
                by_arm = {arm: outcome(results, arm) for arm in ARMS}
                exceptions = [
                    f"{r['id']} {r['result']['status']}"
                    for r in data
                    if r["result"]["status"] in {"failed", "timed_out", "missing", "unavailable"}
                ]
                comparisons = [
                    f"{s.get('label', s['value'])} · {r['id']} {r['result']['status']}"
                    for s, (_, _, control) in archives
                    if s != primary
                    for r in control
                    if r["result"]["status"] in {"failed", "timed_out"}
                ]
                issue = None
            except (ValueError, KeyError, OSError) as failure:
                issue = str(failure)
            for arm in ARMS:
                path = images.get((panel, arm))
                columns = dict(
                    chart=relative(path, root) if path else "",
                    report=report_link(study, root),
                    evidence=relative(local(folder, spec["seal"]), root),
                    notes=spec["caption"],
                )
                base = (mod, panel, title, scope.cohort, scope.boundary, scope.panel_type, arm)
                if issue is not None:
                    columns.update(chart="", notes=f"Evidence check failed. {issue}")
                    yield Row(*base, "Unverified", "Roster unavailable", **columns)
                    continue
                yield Row(
                    *base,
                    "Chart ready" if path else "Sealed replay · chart pending",
                    sample,
                    scheduled=scheduled,
                    terminal_exceptions=" · ".join(exceptions),
                    comparison_failures=" / ".join(comparisons),
                    **by_arm[arm],
                    **columns,
                )


def stage_pages(root, repo):
    manifest = root / "stage-charts" / "manifest.json"
    if not manifest.is_file():
        return {}
    return {
        p["id"]: (p, local(manifest.parent, p["image"]))
        for p in read_json(manifest)["pages"]
        if p["sources"]
        and all(matches(local(repo, name), digest) for name, digest in p["sources"].items())
    }


def stages(root, repo):
    plots = stage_pages(root, repo)
    for folder, key, title, sample, receipt in STAGES:
        scope = SCOPES[folder]
        measurement = root / folder / receipt
        plot, chart = plots.pop(key, (None, None))
        mod = "coherent-scout-phase" if key == "phase-scout-coherent" else scope.modification
        boundary = (
            scope.boundary
            if mod == scope.modification
            else ("Saved dual RX IQ → hypothetical cell admission only")
        )
        exists = chart is not None and chart.is_file()
        state = "Stage receipt · chart pending" if measurement.is_file() else "Evidence pending"
        evidence = root / "stage-charts" / "manifest.json" if plot else measurement
        yield Row(
            mod,
            key,
            title,
            scope.cohort,
            boundary,
            "Stage",
            "stage",
            "Chart ready" if exists else state,
            sample,
            chart=relative(chart, root) if exists else "",
            evidence=relative(evidence, root),
            report=report_link(root / folder, root),
            notes="Position replay outside this boundary.",
        )
    companion = root.parent / "streamlined" / "fractional-runtime"
    plot, chart = plots.pop("fractional-runtime", (None, None))
    if chart is not None and chart.is_file():
        scope = SCOPES["fractional-runtime"]
        yield Row(
            scope.modification,
            plot["id"],
            plot["title"],
            scope.cohort,
            scope.boundary,
            "Stage",
            "stage",
            "Chart ready",
            "12 admitted visits of 16 across 2 recordings",
            chart=relative(chart, root),
            evidence=relative(root / "stage-charts" / "manifest.json", root),
            report=report_link(companion, root),
        )
    for panel, (plot, chart) in sorted(plots.items()):
        if not chart.is_file():
            continue
        yield Row(
            panel,
            panel,
            plot["title"],
            plot.get("cohort", RF),
            plot.get("boundary", "Acquisition stage evidence"),
            "Stage",
            "stage",
            "Chart ready",
            plot.get("sample", "See plotted denominator"),
            chart=relative(chart, root),
            evidence=relative(root / "stage-charts" / "manifest.json", root),
        )


def pending(root, existing):
    for name, title, samples in (
        ("scout-full", "Sixteen scout centers through position", 8),
        ("radius-full", "Two-sample radius through position", 2),
        ("selective-capture", "Causal capture-era visit substitution · 1/128 and 1/16", 4),
    ):
        folder = root / name
        scope = SCOPES[name]
        if not folder.is_dir() or (scope.modification, scope.boundary) in existing:
            continue
        for arm in ARMS:
            yield Row(
                scope.modification,
                name,
                title,
                scope.cohort,
                scope.boundary,
                "Position",
                arm,
                "Evidence pending",
                f"{samples} scheduled recordings",
                samples,
                report=report_link(folder, root),
                notes="Scheduled roster. Terminal counts pending.",
            )


def originals(root, atlas):
    for arm in ARMS:
        source = atlas / "roof" / arm / "original-ten.csv"
        data = {}
        if source.is_file():
            with source.open(newline="") as stream:
                for row in csv.DictReader(stream):
                    if row["series"] in {"one", "four"}:
                        data.setdefault((row["figure"], row["series"]), []).append(row["decision"])
        for panel, (title, boundary) in TEN.items():
            plot = source.with_name(f"{panel}.png")
            four_tile = data.get((panel, "four"), [])
            values = four_tile or data.get((panel, "one"), [])
            series = "four-tile" if four_tile else "single-tile"
            statuses = ("published", "withheld", "failed", "timed_out", "unavailable", "missing")
            outcomes = {k: values.count(k) for k in statuses} if values else {}
            yield Row(
                panel,
                panel,
                title,
                ROOF,
                boundary,
                "Original ten",
                arm,
                "Chart ready" if plot.is_file() else "Presentation pending",
                "135 recordings · DS26 127, DS29 8",
                len(values) or None,
                **outcomes,
                chart=relative(plot, root),
                evidence=relative(source, root),
                report=relative(atlas / "original-ten.html", root),
                notes=f"Counts follow the chart’s primary {series} curve.",
            )


def inventory(root, atlas, repo):
    actual = list(positions(root, rendered(root)))
    complete = {(r.modification, r.boundary) for r in actual if r.state != "Unverified"}
    remaining = pending(root, complete)
    return [*actual, *remaining, *stages(root, repo), *originals(root, atlas)]


def anchor(path, label):
    return f'<a href="{escape(quote(path, safe="/"))}">{escape(label)}</a>' if path else ""


def page(rows, links):
    sections = {
        "position": (
            "Position results",
            {
                "Position",
                "Position diagnostic",
                "Confirmation",
                "Prior position",
                "Deadline repeat",
            },
        ),
        "stage": ("Acquisition-stage results", {"Stage"}),
        "original": ("Original ten", {"Original ten"}),
    }
    nav = " · ".join(f'<a href="#{key}">{name}</a>' for key, (name, _) in sections.items())
    blocks = []
    for key, (title, types) in sections.items():
        groups = {}
        for row in rows:
            if row.panel_type in types:
                groups.setdefault(row.panel_id, []).append(row)
        cards = []
        for group in groups.values():
            first = group[0]
            resources = " · ".join(
                filter(
                    None,
                    (
                        anchor(first.report, "Study"),
                        anchor(first.evidence, "Evidence receipt or data"),
                    ),
                )
            )
            arms = []
            for arm in group:
                key_label = LABELS[arm.arm]
                graphic = anchor(arm.chart, key_label) or escape(key_label)
                diagnostic = (
                    ("published", arm.published),
                    ("forced available", arm.forced_available),
                    ("withheld", arm.withheld),
                    ("failed", arm.failed),
                    ("timed out", arm.timed_out),
                    ("unavailable", arm.unavailable),
                    ("missing", arm.missing),
                    ("stage only", arm.stage_only),
                )
                status = ", ".join(
                    f"{count} {label}"
                    for label, count in diagnostic
                    if count is not None and (count or label == "published")
                )
                exceptions = arm.terminal_exceptions
                detail = f"<br>{escape(exceptions)}" if exceptions else ""
                arms.append(
                    f"<li>{graphic} <span>{escape(arm.state)}"
                    f"{escape(' · ' + status) if status else ''}{detail}</span></li>"
                )
            cards.append(
                f'<article id="{escape(first.panel_id)}"><h3>{escape(first.title)}</h3>'
                f'<p class="scope">{escape(first.panel_type)} · {escape(first.cohort)} · '
                f"{escape(first.sample)}</p><p>{escape(first.boundary)}</p>"
                f"<ul>{''.join(arms)}</ul><p>{resources}</p>"
                "<details><summary>Panel notes</summary>"
                f"<p>{escape(first.notes)}</p>"
                + (
                    f"<p>Comparison failures · {escape(first.comparison_failures)}</p>"
                    if first.comparison_failures
                    else ""
                )
                + "</details></article>"
            )
        blocks.append(
            f'<section id="{key}"><h2>{title}</h2><div class="grid">'
            f"{''.join(cards)}</div></section>"
        )
    extras = " · ".join(anchor(path, label) for label, path in links.items() if path)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Acquisition and receiver evidence</title>
<style>
*{{box-sizing:border-box}} body{{margin:auto;max-width:83rem;padding:2.8rem 4vw;background:#f6f7f4;
font:1rem/1.5 system-ui,sans-serif;color:#172f30}} h1{{font-size:clamp(2rem,4vw,3.2rem);margin:0}}
h2{{margin-top:2.3rem}} h3{{margin:0;line-height:1.24}} p{{margin:.55rem 0}} a{{color:#135d57}}
nav{{margin:1rem 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(24rem,100%),1fr));gap:1rem}}
article{{padding:1rem;background:#fff;border:1px solid #d7e0d9;
border-radius:.35rem;scroll-margin:1rem}}
.scope,span,details{{font-size:.89rem;color:#435f5c}} ul{{margin:.7rem 0;padding-left:1.25rem}}
li>span{{overflow-wrap:anywhere}}
summary{{cursor:pointer}} a:focus-visible,summary:focus-visible{{outline:2px solid #0b725e}}
</style></head>
<body><header><h1>Acquisition and receiver evidence</h1>
<p>Use the calibration links to open each measured position plot. Forced locations are diagnostic
coordinates and may include published fixes. Each stage chart identifies the operation measured.</p>
<p><a href="chart-inventory.csv">Chart inventory CSV</a>{" · " + extras if extras else ""}</p>
<nav aria-label="Evidence sections">{nav}</nav></header><main>{"".join(blocks)}</main></body></html>
"""


def build(root=ACQUISITION, atlas=ATLAS, repo=ROOT):
    rows = inventory(root, atlas, repo)
    chart_paths = [r.chart for r in rows if r.chart]
    if len(chart_paths) != len(set(chart_paths)):
        raise ValueError("An image is linked from multiple index rows")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(Row.__dataclass_fields__))
    writer.writeheader()
    writer.writerows(asdict(row) for row in rows)
    write(root / "chart-inventory.csv", buffer.getvalue().encode())
    links = {
        "Download PNGs and data": relative(root / "modification-charts.zip", root),
        "Position gallery": relative(root / "charts" / "index.html", root),
        "Stage chart book": relative(root / "stage-charts" / "stage-evidence.pdf", root),
        "Original ten gallery": relative(atlas / "original-ten.html", root),
    }
    write(root / "index.html", page(rows, links).encode())
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=ACQUISITION)
    parser.add_argument("--atlas", type=Path, default=ATLAS)
    args = parser.parse_args()
    rows = build(args.evidence.resolve(), args.atlas.resolve())
    print(f"Indexed {len(rows)} arm and stage entries in {args.evidence}")


if __name__ == "__main__":
    main()
