"""Score another sealed receiver study through the same position-figure entry point."""

from collections import Counter, defaultdict
from hashlib import sha256
from json import loads
from pathlib import Path

from .. import atlas
from ..scoring import ARMS, ROLES, distribution
from . import screening_figures
from .prefix_figures import csv_file


def summarize(study, page, arm):
    summaries = []
    reference = {(r.dataset, r.recording): r.error_km for r in page.rows if r.series == "baseline"}
    by_series = defaultdict(list)
    for r in page.rows:
        # A forced coordinate can coexist with a withholding. It has its own row in the dot data.
        if r.series in study.predictions or r.series in ROLES:
            by_series[r.dataset, r.series].append(r)
            if study.scope == "roof":
                by_series["all", r.series].append(r)
    for (group, series), sample in by_series.items():
        counts = Counter(r.decision for r in sample)
        published = [r for r in sample if r.decision == "published"]
        dist = distribution(r.error_km for r in published)
        row = dict(
            figure=study.id,
            arm=arm,
            cohort=group,
            series=series,
            label=study.labels.get(series, series),
            scheduled=len(sample),
            published=len(published),
            withheld=counts["withheld"],
            failed=counts["failed"],
            timed_out=counts["timed_out"],
            unavailable=counts["unavailable"],
            missing=counts["missing"],
            stage_only=counts["stage_only"],
            median_km=dist["p50"],
            p95_km=dist["p95"],
        )
        pairs = [
            (r.error_km, reference[r.dataset, r.recording])
            for r in published
            if reference.get((r.dataset, r.recording)) is not None
        ]
        row["recordings_with_v5_reference"] = sum(
            reference.get((r.dataset, r.recording)) is not None for r in sample
        )
        for pct in (5, 10):
            row[f"within_{pct}pct"] = (
                sum(e <= (1 + pct / 100) * ref for e, ref in pairs)
                if row["recordings_with_v5_reference"]
                else None
            )
        summaries.append(row)
    return summaries


def render(out, books):
    charts = screening_figures.shared.render(
        out / "charts", ARMS, books.__getitem__, title="Receiver study position errors"
    )
    atlas.write_index(
        out / "charts",
        [atlas.screening_section(charts, ARMS, folder=".")],
        ARMS,
        description="Select a measured receiver change and its calibration setting.",
    )


def render_indexed(out, evidence=screening_figures.REPORT):
    """Render the named benchmark's exact set of verified study descriptors."""
    root = Path(evidence).resolve()
    entries = loads((out / "chart-index.json").read_bytes())["charts"]
    descriptors = defaultdict(list)
    for item in entries:
        descriptor = (root / item["descriptor"]).resolve()
        if descriptor.name != screening_figures.SPEC or not descriptor.is_relative_to(root):
            raise ValueError("indexed position descriptor is outside the evidence directory")
        seal = descriptor.with_name(item["seal"])
        for path, digest in (
            (descriptor, item["descriptor_sha256"]),
            (seal, item["seal_sha256"]),
        ):
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"indexed position evidence changed: {path}")
        descriptors[descriptor].append(item["id"])
    by_id = {
        study.id: study
        for descriptor, ids in descriptors.items()
        for study in screening_figures.charts(methods=ids, evidence=descriptor.parent)
    }
    ids = [item["id"] for item in entries]
    if len(ids) != len(by_id) or set(ids) != by_id.keys():
        raise ValueError("indexed position chart roster changed")
    render(out, {arm: [by_id[ident].page(arm) for ident in ids] for arm in ARMS})
    print(f"Paired position figures in {out / 'charts' / 'index.html'}")


def run(source, out):
    studies = screening_figures.charts(evidence=source)
    books = {arm: [study.page(arm) for study in studies] for arm in ARMS}
    scores = [
        r
        for arm, book in books.items()
        for study, page in zip(studies, book, strict=True)
        for r in summarize(study, page, arm)
    ]
    csv_file(out / "study-summary.csv", scores)
    render(out, books)
    scopes = {study.id: study.scope for study in studies}
    for r in scores:
        roof = scopes[r["figure"]] == "roof"
        if r["series"] != ("one" if roof else "candidate") or (roof and r["cohort"] != "all"):
            continue
        km = f"{r['median_km']:.3f} km" if r["median_km"] is not None else "—"
        paired = (
            f", {r['within_10pct']}/{r['scheduled']} within +10% of v5"
            if r["recordings_with_v5_reference"]
            else ""
        )
        decisions = "".join(
            f", {r[state]} {state.replace('_', ' ')}"
            for state in ("withheld", "failed", "timed_out", "unavailable", "missing", "stage_only")
            if r[state]
        )
        print(
            f"{r['figure']}  {r['arm']}  {r['cohort']}  "
            f"{r['published']}/{r['scheduled']} fixes, median {km}{decisions}{paired}"
        )
    print(f"Paired position figures in {out / 'charts' / 'index.html'}")
    return scores
