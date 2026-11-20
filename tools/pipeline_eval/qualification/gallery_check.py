"""Audit a rendered position gallery, its downloads and their error rosters."""

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

from ..atlas import ARM_LABEL
from ..scoring import ARMS, POSITION_FAILURES, ROLES
from .cold_transfer_figures import TITLES as COLD_TITLES
from .pass_geometry_trials import (
    SYNTHETIC_SUBTITLE,
    SYNTHETIC_TITLE,
    SYNTHETIC_VIEWS,
    read_synthetic_scores,
    synthetic_position_label,
)
from .transfer_figures import LONGITUDE_GATE, METHOD_TITLES

MEASURED = {"published", "withheld", "diagnostic", "no_estimate"}
COUNTS = re.compile(r"(?<![\d/])(\d+)\s*/\s*(\d+)(?![\d/])")
SCORED_COUNTS = re.compile(r"(?<![\d/])(\d+)\s*/\s*(\d+)\s*·\s*(\d+)\s+scored")
TERMINAL_COUNTS = re.compile(
    r"(?<![\d/])0/(\d+)\s*·\s*(?:failed|timed out|unavailable|missing|no result)\b"
)
SYNTHETIC_STEM = "pass-geometry-synthetic"
# These earlier CSV cohorts predate explicit "no site" labels. A permutation of
# just the late blocks at a measured site still has a geographic reference.
UNLOCATED_COHORTS = {"shuffled detections", "lane shuffle", "cfo shuffled within lane"}


class Gallery(HTMLParser):
    def __init__(self):
        super().__init__()
        self.arms = []
        self.charts = {}
        self.links = set()
        self.navigation = Counter()
        self.article = None
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "article":
            self.article = values.get("id")
            if not self.article or self.article in self.charts:
                raise ValueError(f"missing or duplicate chart anchor {self.article!r}")
            self.charts[self.article] = []
        elif tag == "input" and values.get("name") == "calibration":
            self.arms.append(values["id"].removeprefix("cal-"))
        elif tag == "a" and "href" in values:
            href = values["href"]
            self.anchor = (href, values.get("class", ""))
            if href.startswith("#"):
                self.navigation[unquote(href[1:])] += 1
            else:
                self.links.add(href)
        elif tag == "img" and self.article is not None:
            self.charts[self.article].append((values, self.anchor))

    def handle_endtag(self, tag):
        if tag == "article":
            self.article = None
        elif tag == "a":
            self.anchor = None


def _output_file(root, link):
    url = urlsplit(link)
    path = (root / unquote(url.path)).resolve()
    if url.netloc or url.scheme or not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"missing or invalid local gallery target {link!r}")
    return path


def _assets(root):
    html = (root / "index.html").read_text(encoding="utf-8")
    gallery = Gallery()
    gallery.feed(html)
    arms = set(gallery.arms)
    if not arms or arms - set(ARMS) or len(gallery.arms) != len(arms):
        raise ValueError("invalid gallery calibration controls")
    if not gallery.charts or gallery.navigation != Counter(gallery.charts.keys()):
        raise ValueError("every chart needs exactly one reachable navigation link")
    group_counts = re.findall(r"<summary>[^<]*\((\d+)\)</summary>", html)
    if sum(map(int, group_counts)) != len(gallery.charts):
        raise ValueError("navigation section counts differ from the chart roster")

    images = {}
    for chart, entries in gallery.charts.items():
        displays = set()
        for image, anchor in entries:
            source = image["src"]
            if anchor is None or anchor[0] != source or not anchor[1].startswith("arm-"):
                raise ValueError(f"{chart} has no direct standalone PNG link for {source}")
            arm = anchor[1][4:]
            label = ARM_LABEL.get(arm, "Both calibration settings")
            path = _output_file(root, source)
            title, _, image_label = image.get("alt", "").rpartition(" · ")
            if arm in displays or not title or image_label != label:
                raise ValueError(f"{chart} has duplicate or mislabeled {arm} images")
            if path in images:
                raise ValueError(f"{chart} reuses another chart's standalone PNG at {source}")
            if path.parent.name in ARMS and path.parent.name != arm:
                raise ValueError(f"{chart} links {arm} to the other calibration arm")
            with Image.open(path) as png:
                if png.format != "PNG" or png.size != (int(image["width"]), int(image["height"])):
                    raise ValueError(f"{source} differs from its advertised PNG dimensions")
                png.verify()
            displays.add(arm)
            images[path] = title
        if displays != arms and displays != {"both"}:
            raise ValueError(f"{chart} is missing a calibration chart")
    links = {_output_file(root, link) for link in gallery.links}
    return len(gallery.charts), arms, images, links


def _error(value):
    if value:
        error = float(value)
        if not math.isfinite(error) or error < 0:
            raise ValueError(f"invalid position error {value}")
    return bool(value)


def _rendered_counts(text, expected, *, unlocated=()):
    seen_scored = Counter(tuple(map(int, match)) for match in SCORED_COUNTS.findall(text))
    if Counter(unlocated) - seen_scored:
        raise ValueError("rendered page omits publications without a geographic score")
    regular = SCORED_COUNTS.sub("", text)
    found = Counter((int(points), int(total)) for points, total in COUNTS.findall(regular))
    if missing := Counter(expected) - found:
        raise ValueError(f"rendered page omits position counts {dict(missing)}")


def _position_counts(rows, text, *, roof=False, original=False):
    samples = defaultdict(dict)
    for row in rows:
        dataset, series, case = (row[k] for k in ("dataset", "series", "recording"))
        decisions = samples[dataset, series]
        point, state = _error(row["error_km"]), row["decision"]
        if case in decisions:
            raise ValueError(f"duplicate observation {case} in {dataset}/{series}")
        name = dataset.casefold()
        null_geography = (
            name in UNLOCATED_COHORTS or "no geographic truth" in name or "no site" in name
        )
        if point and null_geography:
            raise ValueError(f"null geographic control {case} has a position error")
        if not null_geography and (state in {"published", "diagnostic"}) != point:
            raise ValueError(f"{state} has an inconsistent error for {case}")
        decisions[case] = (state, point)

    datasets = {name for name, _ in samples}
    for dataset in datasets:
        cohort = {series: rows for (name, series), rows in samples.items() if name == dataset}
        roster = set(next(iter(cohort.values())))
        if any(roster != set(series_rows) for series_rows in cohort.values()):
            raise ValueError(f"unmatched recording roster in {dataset}")
        if roof and set(ROLES) - cohort.keys():
            raise ValueError(f"roof cohort {dataset} is missing an original v5 reference")
        if original and len(roster) != {"DS26": 127, "DS29": 8}.get(dataset):
            raise ValueError(f"incorrect original-ten roster size in {dataset}")
        if " ".join(dataset.split()) not in text:
            raise ValueError(f"rendered cohort label missing for {dataset}")
        publication_states = {
            state
            for series, decisions in cohort.items()
            if series not in ROLES and not series.endswith("_forced")
            for state, _ in decisions.values()
        }
        if roof and publication_states == {"withheld"}:
            n = len(roster)
            messages = (f"No published fixes (0/{n})", f"No global or supplied-tile fixes (0/{n}")
            if not any(message in text for message in messages):
                raise ValueError(f"fully withheld cohort {dataset} needs a zero-fix label")
    if original and datasets != {"DS26", "DS29"}:
        raise ValueError("original-ten figure requires both rooftop cohorts")

    expected, unlocated, terminal = [], [], []
    for (_, series), decisions in samples.items():
        states = {state for state, _ in decisions.values()}
        if "stage_only" in states and "unmeasured" not in text.lower():
            raise ValueError("stage-only decisions need an unmeasured label")
        terminal_series = (
            series not in ROLES and not states & MEASURED and states & POSITION_FAILURES
        )
        if terminal_series:
            terminal.append(len(decisions))
        if roof and series not in ROLES and not states & MEASURED:
            if not terminal_series and "unmeasured" not in text.lower():
                raise ValueError("unmeasured stage is unlabeled on the rendered page")
            continue
        scored = sum(point for _, point in decisions.values())
        reported = sum(state in {"published", "diagnostic"} for state, _ in decisions.values())
        if reported > scored:
            unlocated.append((reported, len(decisions), scored))
        else:
            expected.append((scored, len(decisions)))
    explicit = Counter(map(int, TERMINAL_COUNTS.findall(text)))
    if explicit:
        if explicit != Counter(terminal):
            raise ValueError("rendered page gives incorrect terminal failure counts")
        if roof:
            expected.extend((0, n) for n in terminal)
    elif roof and terminal and "unmeasured" not in text.lower():
        raise ValueError("rendered page omits terminal failure counts")
    _rendered_counts(text, expected, unlocated=unlocated)


def _transfer_counts(rows, text):
    samples = defaultdict(dict)
    acquisitions = defaultdict(set)
    for row in rows:
        offered = row["correct_region_offered"]
        series = row["series"]
        group = samples[row["dataset"], offered, series]
        if offered not in {"True", "False"} or row["query_id"] in group:
            raise ValueError("invalid or duplicated geographic query binding")
        point = _error(row["error_km"])
        if point != (row["decision"] in {"published", "estimate"}):
            raise ValueError("transfer decision has inconsistent position error")
        if series.endswith("_published"):
            false_fix = offered == "False" and row["decision"] == "published"
            if row["false_publication"] != str(false_fix):
                raise ValueError("wrong-region publication flag differs from the reported fix")
        group[row["query_id"]] = point
        acquisitions[row["dataset"], series, offered].add(row["acquisition_id"])
    for dataset, _, series in samples:
        if acquisitions[dataset, series, "True"] != acquisitions[dataset, series, "False"]:
            raise ValueError(f"correct and omitted offers use different acquisitions in {dataset}")
    for label in ("Correct region offered", "Correct region omitted", "False publications"):
        if label not in text:
            raise ValueError(f"rendered geographic label missing for {label}")
    _rendered_counts(text, [(sum(group.values()), len(group)) for group in samples.values()])


def _cold_counts(rows, text):
    samples = defaultdict(dict)
    for row in rows:
        cohort = row["cohort"]
        group = samples[row["arm"], cohort]
        if row["id"] in group:
            raise ValueError("duplicate cold-start query")
        published = row["published"] == "True"
        if cohort == "shuffle" and (row["error_km"] or row["forced_error_km"]):
            raise ValueError("a shuffled control has no geographic reference")
        if row["false_publication"] != str(published and cohort in {"omitted", "shuffle"}):
            raise ValueError("cold-start false-publication flag differs from the reported fix")
        group[row["id"]] = published
    for _, cohort in tuple(samples):
        if samples["c0", cohort].keys() != samples["fitted_c", cohort].keys():
            raise ValueError(f"cold-start calibration arms differ in the {cohort} cohort")
    for label in (*ARM_LABEL.values(), "Correct region omitted", "No reference position"):
        if label not in text:
            raise ValueError(f"rendered cold-start label missing for {label}")
    _rendered_counts(text, [(sum(group.values()), len(group)) for group in samples.values()])


def _synthetic_book(pdf, reader):
    source_path = pdf.with_name(f"{pdf.stem}-scores.json")
    source, rows = read_synthetic_scores(source_path)
    digest = hashlib.sha256(source).hexdigest()
    if reader.metadata is None or reader.metadata.subject != f"SHA-256 {digest}":
        raise ValueError(f"{pdf} does not bind the linked synthetic score bytes")
    if len(reader.pages) != 1:
        raise ValueError(f"{pdf} must hold the two-case synthetic chart on one page")
    text = " ".join(reader.pages[0].extract_text().split())
    labels = (
        SYNTHETIC_TITLE,
        SYNTHETIC_SUBTITLE,
        *(label for _, _, label in SYNTHETIC_VIEWS),
        "Withheld · no geographic distance",
        "No frequency fit",
        "Position error (km, log scale)",
        "Conditional Doppler RMS (Hz)",
        "Zero calibration",
        "Fitted calibration",
        "Returned fix",
        "Forced estimate (withheld)",
    )
    if missing := [label for label in labels if label not in text]:
        raise ValueError(f"{pdf} is missing synthetic chart labels {missing}")
    expected = Counter()
    for case, mode, _ in SYNTHETIC_VIEWS[:2]:
        for values in rows[case, mode]["arms"].values():
            expected[synthetic_position_label(values["forced_km"])] += 1
            expected[f"{values['conditional_rms_hz']:.1f}"] += 1
    if missing := expected - Counter(text.split()):
        raise ValueError(f"{pdf} omits rendered synthetic scores {list(missing)}")
    return 1, {pdf.stem: set(rows)}


def _book(pdf, image_titles):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as error:
        raise RuntimeError("gallery PDF verification requires pypdf") from error

    try:
        reader = PdfReader(pdf)
        pages = reader.pages
    except PdfReadError as error:
        raise ValueError(f"cannot open the chart book at {pdf}: {error}") from error
    if pdf.stem == SYNTHETIC_STEM:
        return _synthetic_book(pdf, reader)
    arm = pdf.parent.name
    csv_path = pdf.with_suffix(".csv") if arm in ARMS else pdf.parent / "per-case.csv"
    with csv_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if not rows or any(row["arm"] not in ARMS or arm in ARMS and row["arm"] != arm for row in rows):
        raise ValueError(f"empty or mismatched calibration roster in {csv_path}")
    groups = defaultdict(list)
    for row in rows:
        name = pdf.stem if pdf.stem == "fresh80" else row.get("figure", row.get("method"))
        groups[name].append(row)
    if len(pages) != len(groups) or (pdf.stem == "original-ten" and len(pages) != 10):
        raise ValueError(f"rendered page count differs from {csv_path}")

    for (name, rows), page in zip(groups.items(), pages, strict=True):
        text = " ".join(page.extract_text().split())
        try:
            title = image_titles.get(pdf.with_name(f"{name}.png"))
            if arm not in ARMS:
                title = COLD_TITLES.get(name, title)
            elif pdf.stem == "fresh80":
                title = METHOD_TITLES[LONGITUDE_GATE]
            if title and title.casefold() not in text.casefold():
                raise ValueError("rendered chart title differs from the gallery image title")
            if arm not in ARMS:
                _cold_counts(rows, text)
            elif "correct_region_offered" in rows[0]:
                if ARM_LABEL[arm] not in text and "Calibration-invariant" not in text:
                    raise ValueError("rendered geographic calibration label differs")
                _transfer_counts(rows, text)
            else:
                calibration = "c = 0" if arm == "c0" else "fitted c"
                label = (
                    f"v5 uses {calibration}. Curves count every recording."
                    if "Fraction of all recordings" in text
                    else f"{calibration}. Counts include all attempts in each row."
                )
                if label not in text:
                    raise ValueError("rendered position calibration label differs")
                _position_counts(
                    rows,
                    text,
                    roof="Fraction of all recordings" in text,
                    original=pdf.stem == "original-ten",
                )
        except ValueError as error:
            raise ValueError(f"{pdf} / {name}: {error}") from error
    roster = {
        name: {
            (r.get("dataset", r.get("cohort")), r.get("recording", r.get("query_id", r.get("id"))))
            for r in rows
        }
        for name, rows in groups.items()
    }
    if pdf.stem == "original-ten" and any(
        cases != next(iter(roster.values())) for cases in roster.values()
    ):
        raise ValueError(f"original-ten pages use different rooftop rosters in {pdf}")
    return len(pages), roster


def check(root):
    root = Path(root).resolve()
    count, arms, images, links = _assets(root)
    for image in (path for path in images if path.stem == SYNTHETIC_STEM):
        downloads = {image.with_suffix(".pdf"), image.with_name(f"{image.stem}-scores.json")}
        if not downloads <= links:
            raise ValueError("the pass-geometry synthetic chart needs linked PDF and score data")
    linked = {path for path in links if path.suffix == ".pdf"}
    standalone = {path.with_suffix(".pdf") for path in images if path.with_suffix(".pdf").is_file()}
    books = {}
    covered = set()
    paired = {}
    for pdf in sorted(linked | standalone):
        pages, roster = _book(pdf, images)
        if pdf.parent.name in ARMS:
            key = pdf.parent.parent / pdf.name
            if key in paired and paired[key] != roster:
                raise ValueError(f"PDF calibration arms have different recording rosters for {key}")
            paired[key] = roster
        covered.update(pdf.with_name(f"{name}.png") for name in roster)
        books[str(pdf.relative_to(root))] = pages
    return dict(
        charts=count,
        arms=sorted(arms),
        standalone_pngs=len(images),
        pdf_pages=books,
        unlinked_standalone_pdfs=sorted(str(p.relative_to(root)) for p in standalone - linked),
        charts_without_pdf_data=sorted(str(p.relative_to(root)) for p in images.keys() - covered),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gallery", type=Path)
    parser.add_argument("--expected-charts", type=int)
    args = parser.parse_args()
    try:
        result = check(args.gallery)
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))
    if args.expected_charts is not None and result["charts"] != args.expected_charts:
        parser.error(f"expected {args.expected_charts} charts, found {result['charts']}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
