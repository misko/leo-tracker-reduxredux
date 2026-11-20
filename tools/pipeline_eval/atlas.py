"""Browse the measured position distributions and compare paired recording errors."""

import csv
import struct
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import quote

from .__main__ import write
from .position_figure import TITLES
from .qualification.prefix_figures import csv_file
from .scoring import ROLES, distribution

ARM_LABEL = {"fitted_c": "Fitted calibration", "c0": "Zero calibration"}


@dataclass(frozen=True)
class Chart:
    name: str
    title: str
    images: dict[str, str]
    caption: str = ""


@dataclass(frozen=True)
class Section:
    name: str
    title: str
    charts: list[Chart]
    links: dict[str, str]


def paired_accuracy(path):
    """Score published fixes against no-repair v5 on the same recording and arm."""
    with Path(path).open(newline="") as stream:
        groups = defaultdict(lambda: defaultdict(dict))
        for row in csv.DictReader(stream):
            group = groups[row["figure"], row["arm"], row["dataset"]][row["series"]]
            recording = row["recording"]
            if recording in group:
                raise ValueError(f"duplicate position decision for {recording}")
            error = float(row["error_km"]) if row["error_km"] else None
            group[recording] = (row["decision"], error)

    summaries = []
    for (method, arm, dataset), series in groups.items():
        baseline = series["baseline"]
        for mode, decisions in series.items():
            if mode in (*ROLES, "stock") or mode.endswith("_forced"):
                continue
            if decisions.keys() != baseline.keys():
                raise ValueError(f"unmatched position records for {method} on {dataset}")
            errors = []
            pairs = []
            for recording, (state, error) in decisions.items():
                if state != "published":
                    continue
                if error is None:
                    raise ValueError(f"published position without error for {recording}")
                errors.append(error)
                ref_state, ref_error = baseline[recording]
                if ref_state == "published" and ref_error is not None:
                    pairs.append((error, ref_error))
            stats = distribution(errors)
            summaries.append(
                dict(
                    figure=method,
                    arm=arm,
                    dataset=dataset,
                    series=mode,
                    recordings=len(baseline),
                    published=len(errors),
                    withheld=sum(state == "withheld" for state, _ in decisions.values()),
                    paired_fixes=len(pairs),
                    error_at_most_105pct_v5=sum(a <= 1.05 * b for a, b in pairs),
                    error_at_most_110pct_v5=sum(a <= 1.10 * b for a, b in pairs),
                    median_published_km=stats["p50"],
                    p95_published_km=stats["p95"],
                )
            )
    return summaries


def _link(url, label):
    return f'<a href="{escape(quote(url, safe="/#"), quote=True)}">{escape(label)}</a>'


def book_links(folder, arms):
    links = {}
    for arm in arms:
        links[f"{ARM_LABEL[arm]} PDF"] = f"{folder}/{arm}/modifications.pdf"
        links[f"{ARM_LABEL[arm]} data"] = f"{folder}/{arm}/modifications.csv"
    return links


STYLE = """
:root {color-scheme:light; font:16px/1.5 'Atkinson Hyperlegible Next','Segoe UI',sans-serif;
       color:#192c36; background:#fafbf9}
* {box-sizing:border-box}
body {margin:0 auto; max-width:1650px; padding:1.5rem clamp(1rem,3vw,3rem)}
a {color:#075e52; text-underline-offset:.15em}
a:focus-visible,summary:focus-visible,label:focus-visible
{outline:3px solid #be761c; outline-offset:3px} h1,h2,h3 {line-height:1.17; text-wrap:balance}
h1 {margin:0 0 .7rem; font-size:clamp(1.8rem,4vw,3rem)} header p {max-width:80ch}
.layout {display:grid; grid-template-columns:minmax(13rem,19rem) minmax(0,1fr);
         gap:2rem; margin-top:1.25rem}
nav {position:sticky; top:1rem; max-height:92vh; overflow:auto; padding:.5rem 1rem .7rem 0}
.chart-search {margin-bottom:.8rem}
.chart-search label {display:block; font-weight:650}
.chart-search input {width:100%; font:inherit; padding:.3rem .5rem; border:1px solid #72877c;
  border-radius:.25rem}
.chart-search output {font-size:.9rem}
[hidden] {display:none!important}
nav details {margin-bottom:.65rem} summary {cursor:pointer; font-weight:650}
nav ul {list-style:none; margin:.3rem 0; padding:0 0 0 .8rem} nav li {margin:.35rem 0}
main {min-width:0} section {margin-bottom:2.4rem} section>h2 {margin:.45rem 0}
article {border-top:1px solid #c8d3ce; padding:.6rem 0 1.4rem; scroll-margin-top:1rem}
article:target {border-top:3px solid #00785f} h3 {margin:.45rem 0; font-size:1.2rem}
.exports {margin:.5rem 0; font-size:.92rem}
.sr-only {position:absolute; width:1px; height:1px; padding:0; overflow:hidden;
  clip-path:inset(50%); white-space:nowrap}
.exports a {display:inline-block; margin-right:1rem}
img {display:block; max-width:100%; height:auto; margin-top:.4rem; background:white}
label {margin-right:1.15rem; cursor:pointer} input {accent-color:#00785f}
#cal-c0:checked ~ .layout .arm-fitted_c, #cal-fitted_c:checked ~ .layout .arm-c0 {display:none}
@media(max-width:850px) {.layout {display:block}
  nav {position:static; max-height:13rem; margin-bottom:1rem}}
@media print {nav,header,input,label,.exports {display:none}
  .layout {display:block} article {break-inside:avoid}}
"""

SEARCH = """
<div class="chart-search" hidden><label for="find-chart">Find a modification</label>
<input id="find-chart" type="search" autocomplete="off">
<output for="find-chart" aria-live="polite"></output></div>
"""

FILTER = r"""
<script>
const field = document.getElementById('find-chart');
const normalize = text => text.toLowerCase().replace(/[_-]+/g, ' ').trim();
const sections = document.querySelectorAll('main section');
const groups = Array.from(document.querySelectorAll('nav details'), (details, i) => {
  const items = Array.from(details.querySelectorAll('li'), item => {
    const link = item.querySelector('a');
    const article = document.getElementById(decodeURIComponent(link.hash.slice(1)));
    return {item, article, text: normalize(article.id + ' ' + article.textContent)};
  });
  return {details, items, section: sections[i]};
});
let previous;
field.addEventListener('input', () => {
  const query = normalize(field.value);
  const terms = query.split(/\s+/);
  if (query && !previous) previous = groups.map(group => group.details.open);
  let count = 0;
  groups.forEach(({details, items, section}, i) => {
    let shown = 0;
    for (const {item, article, text} of items) {
      const keep = terms.every(term => text.includes(term));
      item.hidden = article.hidden = !keep;
      if (keep) shown++;
    }
    details.hidden = section.hidden = !shown;
    if (query) details.open = Boolean(shown);
    else if (previous) details.open = previous[i];
    count += shown;
  });
  field.nextElementSibling.value = query
    ? (count ? count + (count === 1 ? ' chart' : ' charts') : 'No matching charts') : '';
  if (!query) previous = null;
});
field.parentElement.hidden = false;
</script>
"""


def write_index(out, sections, arms, *, description, filename="index.html"):
    out = Path(out)
    nav, main = [], []
    for index, section in enumerate(sections):
        nav.append(
            f"<details{' open' if index == 0 else ''}><summary>{escape(section.title)} "
            f"({len(section.charts)})</summary><ul>"
        )
        main.append(f'<section><h2>{escape(section.title)}</h2><p class="exports">')
        for label, path in section.links.items():
            if not (out / path).is_file():
                raise FileNotFoundError(out / path)
            main.append(_link(path, label))
        main.append("</p>")
        seen = set()
        for chart_index, chart in enumerate(section.charts):
            if chart.name in seen:
                raise ValueError(f"duplicate chart {section.name}/{chart.name}")
            seen.add(chart.name)
            anchor = section.name + "-" + chart.name
            nav.append("<li>" + _link("#" + anchor, chart.title) + "</li>")
            main.append(
                f'<article id="{escape(anchor, quote=True)}"><h3 class="sr-only">'
                f"{escape(chart.title)}</h3>"
            )
            if chart.caption:
                main.append(f'<p class="sr-only">{escape(chart.caption)}</p>')
            for arm, path in chart.images.items():
                with (out / path).open("rb") as png:
                    header = png.read(24)
                if not header.startswith(b"\x89PNG\r\n\x1a\n") or header[12:16] != b"IHDR":
                    raise ValueError(f"invalid chart PNG in {path}")
                width, height = struct.unpack(">II", header[16:24])
                url = escape(quote(path), quote=True)
                alt = escape(
                    f"{chart.title} · {ARM_LABEL.get(arm, 'Both calibration settings')}", quote=True
                )
                eager = index == 0 and chart_index == 0
                loading, decoding = ("eager", "sync") if eager else ("lazy", "async")
                main.append(
                    f'<a class="arm-{arm}" href="{url}"><img width="{width}" height="{height}" '
                    f'loading="{loading}" decoding="{decoding}" '
                    f'src="{url}" alt="{alt}"></a>'
                )
            main.append("</article>")
        main.append("</section>")
        nav.append("</ul></details>")
    arm_inputs = "".join(
        f'<input type="radio" id="cal-{arm}" name="calibration"{" checked" if i == 0 else ""}>'
        f'<label for="cal-{arm}">{ARM_LABEL[arm]}</label>'
        for i, arm in enumerate(arms)
    )
    searchable = sum(len(section.charts) for section in sections) > 1
    html = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Position error by modification</title><style>{STYLE}</style><body><header>"
        f"<h1>Position error by modification</h1><p>{escape(description)}</p></header>"
        f'{arm_inputs}<div class="layout"><nav aria-label="Charts">'
        f"{SEARCH if searchable else ''}{''.join(nav)}</nav><main>{''.join(main)}</main></div>"
        f"{FILTER if searchable else ''}</body></html>\n"
    )
    write(out / filename, html.encode())


def roof_charts(pages, arms, prefix=""):
    return [
        Chart(
            p.name,
            TITLES.get(p.method, p.method),
            {a: f"{prefix}{a}/{p.name}.png" for a in arms},
            p.subtitle,
        )
        for p in pages
    ]


def write_roof(out, pages, arms):
    """The regular figures command also leaves a browser index and paired counts."""
    out = Path(out)
    paired = []
    for arm in arms:
        paired.extend(paired_accuracy(out / arm / "modifications.csv"))
    if paired:
        csv_file(out / "paired-v5.csv", paired)
    links = book_links(".", arms)
    if paired:
        links["Paired 5% and 10% counts"] = "paired-v5.csv"
    write_index(
        out,
        [Section("roof", "Roof recordings", roof_charts(pages, arms), links)],
        arms,
        description="Each page compares the receiver with four v5 options on the same recordings. "
        "Curves count every recording, including withheld fixes. Dots show individual position "
        "errors and diamonds show their median. Select a chart to open the full-size figure.",
    )


def _manifest_charts(manifest, arms, folder):
    charts = {}
    for row in manifest:
        arm = row["arm"]
        if arm not in arms:
            continue
        name = row["id"]
        chart = charts.setdefault(name, Chart(name, row["title"], {}))
        if chart.title != row["title"] or arm in chart.images:
            raise ValueError(f"mismatched chart for {folder}/{name}")
        chart.images[arm] = f"{folder}/{row['image']}"
    if any(set(c.images) != set(arms) for c in charts.values()):
        raise ValueError(f"pages in {folder} have different calibration rosters")
    return list(charts.values())


def short_receiver_sections(manifest, arms, folder="short-receiver"):
    sections = []
    for scope, title in (("roof", "New roof comparisons"), ("transfer", "New location trials")):
        rows = [r for r in manifest if r["scope"] == scope]
        if not rows:
            continue
        charts = _manifest_charts(rows, arms, folder)
        links = {}
        for row in rows:
            arm = row["arm"]
            if arm in arms:
                links[f"{ARM_LABEL[arm]} PDF"] = f"{folder}/{row['pdf']}"
                links[f"{ARM_LABEL[arm]} data"] = f"{folder}/{row['csv']}"
        sections.append(Section(f"short-{scope}", title, charts, links))
    return sections


def _study_section(manifest, arms, section, title, folder):
    links = {}
    for row in manifest:
        arm, scope = row["arm"], row["scope"].capitalize()
        if arm in arms:
            for kind, label in (("pdf", "PDF"), ("csv", "data")):
                links[f"{scope} · {ARM_LABEL[arm]} {label}"] = f"{folder}/{row[kind]}"
    return Section(section, title, _manifest_charts(manifest, arms, folder), links)


def convergence_section(manifest, arms, folder="convergence"):
    return _study_section(manifest, arms, "convergence", "Receiver convergence", folder)


def screening_section(manifest, arms, folder="screening"):
    return _study_section(manifest, arms, "screening", "Receiver screening", folder)


def generate(out, arms):
    """Rebuild every chart from its original paired recordings or geographic queries."""
    from . import figure_books
    from .qualification import (
        atlas_roof,
        cold_transfer_figures,
        convergence_figures,
        pass_geometry_trials,
        prototype_figures,
        screening_figures,
        transfer_figures,
    )

    out = Path(out)
    roof = figure_books.generate(out / "roof", arms, panel="published")
    transfer_figures.generate(out / "transfer", arms)
    prototypes = prototype_figures.generate(out / "prototypes", arms=arms)
    short_receiver = figure_books.generate(out / "short-receiver", arms, panel="short-receiver")
    convergence = (
        figure_books.generate(out / "convergence", arms, panel="convergence")
        if convergence_figures.available()
        else []
    )
    screening = (
        figure_books.generate(out / "screening", arms, panel="screening")
        if screening_figures.available()
        else []
    )
    cold_transfer_figures.generate(out / "cold-transfer")
    pass_geometry_scores = atlas_roof.REPORT / "pass-geometry/synthetic-scores.json"
    pass_geometry_trials.write_synthetic_figure(
        pass_geometry_scores,
        out / "cold-transfer/pass-geometry-synthetic.png",
        pdf_path=out / "cold-transfer/pass-geometry-synthetic.pdf",
    )
    write(
        out / "cold-transfer/pass-geometry-synthetic-scores.json", pass_geometry_scores.read_bytes()
    )

    roof_links = book_links("roof", arms)
    roof_links["Paired 5% and 10% counts"] = "roof/paired-v5.csv"
    first = [p for p in roof if p.method in figure_books.TEN]
    prototype_names = {entry["id"] for entry in prototypes}
    others = [p for p in roof if p.method not in figure_books.TEN and p.name not in prototype_names]
    original_methods = list(figure_books.TEN)
    for arm in arms:
        book = figure_books.published_pages(arm, original_methods)
        # The ten individual PNGs already exist in the roof directory.
        figure_books.write_book(book, out / "roof" / arm, "original-ten", arm, images=False)

    sections = [
        Section(
            "original",
            "Ten full-pipeline modifications",
            roof_charts(first, arms, "roof/"),
            {
                f"{ARM_LABEL[a]} {label}": f"roof/{a}/original-ten.{suffix}"
                for a in arms
                for suffix, label in (("pdf", "PDF"), ("csv", "data"))
            },
        ),
        *short_receiver_sections(short_receiver, arms),
        *([convergence_section(convergence, arms)] if convergence else []),
        *([screening_section(screening, arms)] if screening else []),
        Section("roof", "Other roof modifications", roof_charts(others, arms, "roof/"), roof_links),
        Section(
            "prototype",
            "Early variants and regional search",
            _manifest_charts(prototypes, arms, "prototypes"),
            book_links("prototypes", arms),
        ),
    ]
    originals = sections[0]
    write_index(
        out,
        [originals],
        arms,
        filename="original-ten.html",
        description="One chart for each of the ten pipeline changes. Every chart uses the "
        "same 127 DS26 and eight DS29 roof recordings and the four original v5 options. "
        "Select an image to see it at full size. The curves include withheld attempts in "
        "the denominator. Diamonds mark the median among the positions in each row.",
    )
    originals.links["Gallery of these ten charts"] = "original-ten.html"
    transfer = [
        Chart(
            method,
            transfer_figures.METHOD_TITLES[method],
            {a: f"transfer/{a}/{method}.png" for a in arms},
        )
        for method in transfer_figures.SOURCES
    ]
    transfer.append(
        Chart(
            "fresh80",
            "Longitude controls on 40 fresh simulated acquisitions",
            {a: f"transfer/{a}/fresh80.png" for a in arms},
            "Each simulated acquisition was evaluated with the correct region offered and omitted.",
        )
    )
    transfer_links = book_links("transfer", arms)
    for arm in arms:
        transfer_links[f"Fresh simulation · {ARM_LABEL[arm]} PDF"] = f"transfer/{arm}/fresh80.pdf"
        transfer_links[f"Fresh simulation · {ARM_LABEL[arm]} data"] = f"transfer/{arm}/fresh80.csv"
    sections.append(
        Section("transfer", "Correct region offered and omitted", transfer, transfer_links)
    )
    cold = [
        Chart(method, TITLES[method], {"both": f"cold-transfer/{method}.png"})
        for method in cold_transfer_figures.TITLES
    ]
    cold.append(
        Chart(
            "pass_geometry",
            "Doppler pass geometry at one fresh simulated location",
            {"both": "cold-transfer/pass-geometry-synthetic.png"},
            "One positive scene and one shuffled control. The shuffle has no geographic reference.",
        )
    )
    sections.append(
        Section(
            "cold",
            "Cold-start location tests",
            cold,
            {
                "Three cold-start receivers PDF": "cold-transfer/modifications.pdf",
                "Three-receiver per-case data": "cold-transfer/per-case.csv",
                "Pass-geometry synthetic PDF": "cold-transfer/pass-geometry-synthetic.pdf",
                "Pass-geometry synthetic data": "cold-transfer/pass-geometry-synthetic-scores.json",
            },
        )
    )
    write_index(
        out,
        sections,
        arms,
        description="The original ten changes share 127 DS26 and eight DS29 recordings from the "
        "same roof. Later trials use the recordings named on each figure. The curves count every "
        "attempt. A forced estimate is the receiver’s best guess when it withholds a fix. "
        "The regional tests show the offered and omitted conditions separately.",
    )
    print(
        f"Browse all {sum(len(s.charts) for s in sections)} comparison charts: {out / 'index.html'}"
    )
