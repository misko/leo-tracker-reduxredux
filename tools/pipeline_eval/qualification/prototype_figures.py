"""Build per-sample position figures for the receiver experiments before pipeline_eval."""

import argparse
import gzip
import hashlib
import io
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path
from runpy import run_path
from textwrap import fill

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from ..__main__ import encoded, local_output, write
from ..corpus import REPO, references
from ..position_figure import COLORS, LABELS, Mark, _axis, save_png, terminal_count_label
from ..scoring import ARMS, ROLES, distance_km
from . import embedded_figures
from .prefix_figures import csv_file

REPORT = REPO / "reports/2026_11_19_position_atlas/prototypes"
EMBEDDED = "2026_11_18_embedded_prototypes"
LOCATION = "2026_11_18_location_transfer"
EVIDENCE = "evidence.json.gz"
RECEIPT = "evidence-receipt.json"
ROOF = "DS26 · original tile"
OFFERED = "DS26 · correct region offered"
OMITTED = "DS26 · correct region omitted"
WRONG_TILE = "DS26 · wrong tile supplied"
SIMULATION = "Synthetic · updated-orbit confirmation"

PAIRED = (
    ("early_stream_60s", "01_stream", "at_60s", "Streaming fix after 60 seconds"),
    ("early_stream_120s", "01_stream", "at_120s", "Streaming fix after 120 seconds"),
    ("early_blind_search", "02_pilots", "all_blind", "Always-blind pilot search replay"),
    ("early_unbalanced", "03_consensus", "unbalanced_compact", "Unbalanced family fit"),
    ("early_float64", "04_compact", "float64", "Float64 orbital table"),
    ("early_latest_anchor", "05_stationary", "latest_anchor", "Forecast from the latest fix"),
    ("early_longest_tracks", "06_coreset", "longest12", "12 longest Doppler tracks"),
    ("early_full_tracks", "06_coreset", "full", "Full Doppler track budget"),
    (
        "early_wrapped_means",
        "07_differences",
        "plus_wrapped_means",
        "Doppler changes and wrapped means",
    ),
    ("early_coarse_49", "08_grid", "49_cells", "Marginalized grid at 49 cells"),
    ("early_shape_peak", "10_network", "shape_grid_peak", "Coarse Doppler-shape grid"),
)
LOCATION_METHODS = {
    "geometry12": "early_coreset",
    "full": "early_full_tracks",
    "longest12": "early_longest_tracks",
    "random12": "early_random_tracks",
    "coordinate_network": "early_network",
    "shape_grid": "early_shape_peak",
    "refined_shape": "early_refined_shape",
    "prior_center": "early_prior_center",
    "known_ids": "early_known_ids",
}
OTHER_EMBEDDED = {
    "early_graph_compact": ("Compact fit on archived graph", "Fit the complete archived graph."),
    "early_stream_compact": (
        "Compact fit on streamed tracks",
        "Build causal tracks from saved detector output.",
    ),
    "early_stream_coreset": (
        "Streaming tracker with 12 geometry-selected tracks",
        "Retrospective integration on the same eight recordings. "
        "The matched stock uses all streamed tracks.",
    ),
    "early_random_tracks": ("12 random Doppler tracks", "Equal-budget track-selection control."),
    "early_refined_shape": (
        "Refined Doppler-shape grid",
        "Refine the best coarse cell with up to 50 new points.",
    ),
    "early_prior_center": (
        "Supplied tile center, zero radio",
        "Return the supplied center as a prior-only control.",
    ),
    "early_known_ids": (
        "Simulation with supplied satellite IDs",
        "Oracle diagnostic with clean tracks whose planted identities survived blind shortlisting.",
    ),
}
POLICIES = {"geometry12": "12 geometry-selected tracks", "full": "all eligible tracks"}


@dataclass(frozen=True)
class Page:
    id: str
    title: str
    subtitle: str
    rows: list[Mark]


def _read(path, digest=None):
    data = path.read_bytes()
    if digest is not None and hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"prototype source differs from its archive digest: {path.name}")
    return json.loads(data)


def _exact(values, expected, context):
    observed = list(values)
    if len(observed) != len(set(observed)) or set(observed) != set(expected):
        raise ValueError(f"incomplete, duplicate or unexpected sample roster for {context}")


def freeze(sources, out=REPORT):
    """Extract saved endpoints and case labels, with no calls to a receiver."""
    sources, out = Path(sources), local_output(out)
    embedded = sources / EMBEDDED
    location = sources / LOCATION
    comparison = _read(embedded / "comparison.json")
    transfer = _read(location / "summary.json")
    panel = [r["id"] for r in references("roof16") if r["group"] == "DS26"]
    if comparison["panel"] != panel:
        raise ValueError("embedded source uses a different DS26 prototype roster")
    verified = {}

    def original(directory, path, digest):
        data = _read(directory / path, digest)
        verified[f"{directory.name}/{path}"] = digest
        return data

    rows = []

    def record(
        figure, cohort, sample, arms, *, ref=None, truth=None, series="candidate", state=None
    ):
        _exact(arms, ARMS, figure)
        for arm in ARMS:
            point = arms[arm].get("latlon")
            rows.append(
                dict(
                    figure=figure,
                    cohort=cohort,
                    sample=sample,
                    ref=ref,
                    truth=truth,
                    arm=arm,
                    series=series,
                    point=point,
                    status=state or ("published" if point else "withheld"),
                )
            )

    extractor = embedded / "paired_controls.py"
    verified[f"{EMBEDDED}/{extractor.name}"] = hashlib.sha256(extractor.read_bytes()).hexdigest()
    endpoints = run_path(str(extractor))["endpoints"]
    primary = {
        method: original(embedded, f"{method}/result.json", digest)
        for method, digest in comparison["result_sha256"].items()
    }
    for figure, primary_id, control, _ in PAIRED:
        doc = primary[primary_id]
        _exact((r["case"] for r in doc["cases"]), panel, primary_id)
        for row in doc["cases"]:
            case = row["case"]
            record(figure, ROOF, case, endpoints(primary_id, doc, row)[control], ref=case)
    controls = original(embedded, "controls.json", comparison["evidence_sha256"]["controls.json"])
    path = "stream_coreset_check/result.json"
    integrated = original(embedded, path, comparison["evidence_sha256"][path])["cases"]
    for figure, cases in (
        ("early_graph_compact", controls["controls"]["graph_compact"]),
        ("early_stream_compact", controls["controls"]["stream_compact"]),
        ("early_stream_coreset", integrated),
    ):
        _exact((r["case"] for r in cases), panel, figure)
        for row in cases:
            case = row["case"]
            record(figure, ROOF, case, row["arms"], ref=case)
            if figure == "early_stream_coreset":
                record(figure, ROOF, case, row["full_control"]["arms"], ref=case, series="stock")

    real, guard, synthetic = [
        original(location, name, transfer["input_sha256"][f"{LOCATION}/{name}"])
        for name in (
            "real-predictions.json",
            "time-shift-guard.json",
            "confirmation-predictions.json",
        )
    ]
    _exact((r["case"] for r in guard), panel, "time-shift experiment")
    _exact(
        ((r["case"], r["tile"]) for r in real),
        product(panel, ("original", "east5", "west5", "north5", "south5", "east150", "north150")),
        "regional stress replay",
    )
    unshifted = {
        (r["case"], r["tile"]): r["time_holdout"]["scores"] for r in real if "time_holdout" in r
    }
    for row in real:
        case, tile = row["case"], row["tile"]
        for method, estimate in row["methods"].items():
            figure = LOCATION_METHODS[method]
            if tile in ("east150", "north150"):
                record(figure, WRONG_TILE, f"{case}/{tile}", estimate["arms"], ref=case)
            elif tile == "original" and figure in (
                "early_random_tracks",
                "early_refined_shape",
                "early_prior_center",
            ):
                record(figure, ROOF, case, estimate["arms"], ref=case)

    later = [r for r in synthetic if r["orbit_mode"] == "later"]
    if len(later) != 32 or len({tuple(r["truth"]) for r in later}) != 32:
        raise ValueError("expected 32 distinct later-catalogue synthetic confirmation positions")
    for row in later:
        sample = "/".join((row["case"], row["region"], ",".join(map(str, row["offset"]))))
        for method, estimate in row["methods"].items():
            oracle = method == "known_ids"
            record(
                LOCATION_METHODS[method],
                SIMULATION,
                sample,
                estimate["arms"],
                truth=row["truth"],
                series="diagnostic" if oracle else "candidate",
                state="diagnostic" if oracle else None,
            )

    for row in guard:
        case = row["case"]
        for policy in POLICIES:
            for offer, cohort in (("true_offered", OFFERED), ("true_omitted", OMITTED)):
                diagnostics, publications = {}, {}
                for arm in ARMS:
                    decision = row["decisions"][policy][arm][offer]
                    winner = decision["winner"]
                    tiles = (
                        ("east150", "north150")
                        if cohort == OMITTED
                        else ("original", "east150", "north150")
                    )
                    scores = {t: unshifted[case, t][policy][arm] for t in tiles}
                    eligible = [t for t in tiles if scores[t] is not None]
                    if winner != max(eligible, key=scores.get, default=None):
                        raise ValueError(
                            f"held-out and unshifted winning regions differ for {case}"
                        )
                    point = (
                        row["regional_fits"][winner][policy][arm] if winner else {"latlon": None}
                    )
                    diagnostics[arm] = point
                    publications[arm] = point if decision["accepted"] else {"latlon": None}
                figure = f"region_guard_{policy}"
                record(figure, cohort, case, publications, ref=case)
                record(figure, cohort, case, diagnostics, ref=case, series="diagnostic")
                if cohort == OFFERED:
                    record(
                        f"region_rank_{policy}",
                        cohort,
                        case,
                        diagnostics,
                        ref=case,
                        series="diagnostic",
                    )

    raw = gzip.compress(encoded(rows) + b"\n", mtime=0)
    write(out / EVIDENCE, raw)
    write(
        out / RECEIPT,
        encoded(
            dict(
                schema_version=1,
                sha256=hashlib.sha256(raw).hexdigest(),
                rows=len(rows),
                sources=verified,
            )
        )
        + b"\n",
    )


def _v5(ref, arm, cohort):
    return [
        Mark(
            cohort,
            ref["recording"],
            role,
            "published" if out["latlon"] else out["status"],
            out["error_km"],
        )
        for role in ROLES
        for out in (ref["reference"][role][arm],)
    ]


def _grid(ref, cohort, role, series, diagnostic=False):
    endpoint = ref["reference"][role]["shape"]
    value = distance_km(endpoint["latlon"], ref["truth"])
    state = "diagnostic" if diagnostic else "published"
    if value is None:
        state = endpoint["status"]
    return Mark(cohort, ref["recording"], series, state, value)


def _blind_pages(arm, roof):
    queries = list(references("transfer124"))
    recorded = {
        r["recording"]: r for r in queries if r["group"] == "DS29" and r["condition"] == "present"
    }
    rows = []
    for ref in roof:
        cohort = "DS26 · common roof panel" if ref["group"] == "DS26" else "DS29 · blind roof panel"
        four = recorded[ref["recording"]] if ref["group"] == "DS29" else ref
        if four["truth"] != ref["truth"]:
            raise ValueError(f"blind and roof scoring coordinates differ for {ref['recording']}")
        rows.extend(_v5(ref, arm, cohort))
        for result, mode in ((ref, "one"), (four, "four")):
            rows.append(_grid(result, cohort, f"grid_{mode}", mode))
            rows.append(
                _grid(result, cohort, f"grid_forced_{mode}", f"{mode}_forced", diagnostic=True)
            )

    transfer = []
    for dataset, condition in product(
        ("DS29", "StarLoc", "Altrincham", "Synthetic"), ("present", "missing")
    ):
        offer = "true tile offered" if condition == "present" else "true tile omitted"
        cohort = f"{dataset} · {offer}"
        for ref in queries:
            if (ref["group"], ref["condition"]) == (dataset, condition):
                transfer.append(_grid(ref, cohort, "grid_four", "four"))
                transfer.append(
                    _grid(ref, cohort, "grid_forced_four", "four_forced", diagnostic=True)
                )
    return [
        Page(
            "blind_grid_roof",
            "Original blind Doppler grid on the roof",
            "Retrospective replay on 127 common DS26 recordings. The eight DS29 recordings use "
            "original blind results. The four v5 controls use their production tile.",
            rows,
        ),
        Page(
            "blind_grid_transfer",
            "Original blind Doppler grid in geographic transfer",
            "Each of 62 acquisitions had two four-region queries. DS29, StarLoc and Altrincham are "
            "measured inputs. Synthetic contains 40 modeled locations. "
            "The grid is calibration-invariant.",
            transfer,
        ),
    ]


def pages(arm, evidence=REPORT):
    receipt = _read(evidence / RECEIPT)
    raw = (evidence / EVIDENCE).read_bytes()
    if receipt["schema_version"] != 1 or hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
        raise ValueError("compact prototype predictions differ from their receipt")
    data = json.loads(gzip.decompress(raw))
    if len(data) != receipt["rows"]:
        raise ValueError("compact prototype row count differs")

    roof = list(references("ds26-common127")) + [
        r for r in references("roof16") if r["group"] == "DS29"
    ]
    refs = {r["id"]: r for r in references("roof16") if r["group"] == "DS26"}
    archived = defaultdict(list)
    for row in data:
        if row["arm"] != arm:
            continue
        ref = refs[row["ref"]] if row["ref"] else None
        error = distance_km(row["point"], ref["truth"] if ref else row["truth"])
        status = (
            row["status"] if error is not None or row["status"] != "diagnostic" else "no_estimate"
        )
        archived[row["figure"]].append(
            Mark(row["cohort"], row["sample"], row["series"], status, error)
        )
    result = []
    for page in embedded_figures.pages(arm, None):
        rows = [
            replace(m, dataset=ROOF, series="candidate" if m.series == "one" else m.series)
            for m in page.rows
        ]
        rows.extend(archived.pop(page.name, ()))
        result.append(Page(page.name, embedded_figures.TITLES[page.name], page.subtitle, rows))

    entries = dict(OTHER_EMBEDDED)
    for figure, source, _, title in PAIRED:
        subtitle = (
            "Saved endpoint from the original paired prototype replay. V5 uses the full recording."
        )
        if source == "05_stationary":
            subtitle = (
                "Forecast from the most recent prior anchor, using zero current-scan radio samples."
            )
        entries[figure] = title, subtitle
    for policy, label in POLICIES.items():
        entries[f"region_rank_{policy}"] = (
            f"Held-out region ranking with {label}",
            "Early positions ranked on later whole tracks. The rankings are diagnostic. "
            "V5 uses its original tile.",
        )
        entries[f"region_guard_{policy}"] = (
            f"Shifted-time withholding with {label}",
            "Publish an early position when its later score beats all 19 time-shift controls. "
            "V5 is shown for the same recordings with the original tile available.",
        )
    _exact(archived, entries, "early variants")
    for name, (title, subtitle) in entries.items():
        rows = archived[name]
        for cohort in (ROOF, OFFERED):
            samples = {m.recording for m in rows if m.dataset == cohort}
            if samples:
                _exact(samples, refs, name)
                rows.extend(m for ref in refs.values() for m in _v5(ref, arm, cohort))
        result.append(Page(name, title, subtitle, rows))
    return result + _blind_pages(arm, roof)


SERIES = {
    **{role: (LABELS[role], COLORS[role]) for role in ROLES},
    "candidate": ("Prototype · published", "#00785f"),
    "stock": ("Matched stock · published", "#a65a12"),
    "diagnostic": ("Prototype · diagnostic", "#447d8a"),
    "stock_forced": ("Matched stock · forced", "#be8e63"),
    "one": ("One tile · published", "#a65a12"),
    "one_forced": ("One tile · forced", "#bc7a40"),
    "four": ("Four tiles · published", "#00785f"),
    "four_forced": ("Four tiles · forced", "#447d8a"),
}


def _cohorts(page):
    cohorts = {}
    for row in page.rows:
        cohorts.setdefault(row.dataset, defaultdict(list))[row.series].append(row)
    for cohort, series in cohorts.items():
        expected = {row.recording for row in next(iter(series.values()))}
        for key, rows in series.items():
            _exact((r.recording for r in rows), expected, f"{page.id} / {cohort} / {key}")
    return cohorts


def draw(page, arm, *, series_labels=None, show_terminal_counts=False):
    cohorts = _cohorts(page)
    labels = series_labels or {}
    columns = min(len(cohorts), 2)
    bands = (len(cohorts) + columns - 1) // columns
    if len(cohorts) == 3:
        fig = plt.figure(figsize=(15.9, 7.8))
        grid = fig.add_gridspec(2, 2)
        axes = [
            fig.add_subplot(grid[:, 0]),
            fig.add_subplot(grid[0, 1]),
            fig.add_subplot(grid[1, 1]),
        ]
    else:
        fig, grid = plt.subplots(
            bands, columns, squeeze=False, figsize=(7.4 * columns + 1.1, 3.2 * bands + 2.0)
        )
        axes = list(grid.flat)
    fig.subplots_adjust(
        left=0.27 if columns == 1 else 0.15,
        right=0.97,
        top=1 - 1.13 / fig.get_figheight(),
        bottom=0.74 / fig.get_figheight(),
        wspace=0.64,
        hspace=0.48,
    )
    fig.text(
        0.025,
        1 - 0.42 / fig.get_figheight(),
        page.title,
        ha="left",
        fontsize=19,
        fontweight="bold",
        color="#192c36",
    )
    caption = fill(page.subtitle, 95 if columns == 1 else 175)
    fig.text(
        0.025,
        1 - 0.56 / fig.get_figheight(),
        caption,
        ha="left",
        va="top",
        fontsize=9.5,
        color="#384d58",
    )
    for i, (cohort, grouped) in enumerate(cohorts.items()):
        ax = axes[i]
        points = [
            m.error_km for values in grouped.values() for m in values if m.error_km is not None
        ]
        lo = min(0.055, 0.8 * min(points)) if points else 0.055
        hi = max(12, 1.15 * max(points)) if points else 12
        _axis(ax, lo, hi, by_decade=hi > 1000)
        ax.axvline(5, ls=":", lw=1.0, color="#95a8b0")
        ax.set_title(cohort, fontsize=11.5, fontweight="bold", loc="left", pad=10, color="#192c36")
        ax.set_xlabel("Horizontal error (km)", fontsize=9.5)
        ticks = []
        for y, (key, (label, color)) in enumerate(
            item for item in SERIES.items() if item[0] in grouped
        ):
            label = labels.get(key, label)
            rows = grouped[key]
            estimates = [m for m in rows if m.error_km is not None]
            reported = sum(m.decision in {"published", "diagnostic"} for m in rows)
            if labels and reported > len(estimates):
                ticks.append(f"{label}  {reported}/{len(rows)} · {len(estimates)} scored")
            else:
                terminal = terminal_count_label(rows) if show_terminal_counts else None
                count = terminal or f"{len(estimates)}/{len(rows)}"
                ticks.append(f"{label}  {count}")
            if estimates:
                j = np.array(
                    [
                        int(hashlib.sha256(m.recording.encode()).hexdigest()[:4], 16) / 65535
                        for m in estimates
                    ]
                )
                xs = [m.error_km for m in estimates]
                if labels and (key == "diagnostic" or key.endswith("_forced")):
                    ax.scatter(
                        xs,
                        y + 0.52 * (j - 0.5),
                        s=18,
                        facecolors="none",
                        edgecolors=color,
                        linewidth=0.8,
                        alpha=0.73,
                    )
                else:
                    ax.scatter(xs, y + 0.52 * (j - 0.5), s=18, color=color, linewidth=0, alpha=0.61)
                ax.scatter(
                    np.median(xs),
                    y,
                    s=37,
                    marker="D",
                    facecolor="white",
                    edgecolor=color,
                    linewidth=1.5,
                    zorder=4,
                )
        ax.set_yticks(range(len(ticks)), ticks, fontsize=8.3)
        ax.set_ylim(len(ticks) - 0.42, -0.58)
    for ax in axes[len(cohorts) :]:
        ax.axis("off")
    c = "c = 0" if arm == "c0" else "fitted c"
    note = "Diamonds mark medians of available points."
    if (
        show_terminal_counts
        and "unmeasured" not in page.subtitle.casefold()
        and any(row.decision == "stage_only" for row in page.rows)
    ):
        note = "Totals include unmeasured positions. Diamonds mark medians."
    fig.text(
        0.025,
        0.16 / fig.get_figheight(),
        f"{c}. Counts include all attempts in each row. {note}",
        fontsize=8.7,
        color="#394d58",
    )
    return fig


def generate(out=REPORT, *, arms=ARMS, evidence=REPORT):
    """Write both prototype books and return their image manifest."""
    arms = tuple(arms)
    if not arms or len(arms) != len(set(arms)) or set(arms) - set(ARMS):
        raise ValueError("select one or both distinct calibration arms")
    out, evidence = local_output(out), Path(evidence)
    manifest = []
    for arm in arms:
        directory = out / arm
        book_pages = pages(arm, evidence)
        rows = []
        pdf = io.BytesIO()
        with PdfPages(
            pdf,
            metadata=dict(Title="Early receiver position errors", CreationDate=None, ModDate=None),
        ) as book:
            for page in book_pages:
                image_name = f"{page.id}.png"
                fig = draw(page, arm)
                try:
                    save_png(fig, directory / image_name)
                    book.savefig(fig, facecolor="white")
                finally:
                    plt.close(fig)
                manifest.append(
                    dict(
                        id=page.id,
                        title=page.title,
                        arm=arm,
                        datasets=list(_cohorts(page)),
                        image=f"{arm}/{image_name}",
                        pdf=f"{arm}/modifications.pdf",
                        csv=f"{arm}/modifications.csv",
                    )
                )
                rows.extend(
                    dict(
                        figure=page.id,
                        arm=arm,
                        dataset=m.dataset,
                        recording=m.recording,
                        series=m.series,
                        decision=m.decision,
                        error_km=m.error_km,
                    )
                    for m in page.rows
                )
        write(directory / "modifications.pdf", pdf.getvalue())
        csv_file(directory / "modifications.csv", rows)
    write(out / "manifest.json", encoded(manifest) + b"\n")
    introduction = [
        "# Position errors from the early receiver prototypes",
        "",
        "The ten original embedded methods reuse their eight frozen DS26 recordings. "
        "The paired variants and the tracker-to-12-track integration use the same recordings. "
        "Where shown, all four v5 roles use the same recordings and the original tile.",
        "",
        "Wrong-tile panels contain 16 queries from eight DS26 captures. Shifted-time experiments "
        "use eight captures per offer. The 32 confirmation locations use tracks generated with "
        "later orbital elements. The receiver saw causal elements. The source study also reports "
        "earlier 48-case catalogue tests and four neighboring tiles. "
        "[Location-transfer protocol](../../2026_11_18_location_transfer/protocol.json)",
        "",
        "The original regional receiver has a matched roof page and a geographic transfer page. "
        "The latter reports both offer conditions for 62 acquisitions. DS26 and DS29 share one "
        "roof. StarLoc contributes 11 captures across eight nearby site groups, and Altrincham "
        "contributes three windows with zero qualifying tracks. External recordings, simulated "
        "locations and missing-region queries have no portable v5 fit. "
        "[Blind study protocol]"
        "(../../2026_11_18_blind_regional_receiver/holdout_private/protocol.json)",
        "",
        "The scheduler recall and sampled-IQ pilot check measured acquisition on 108,052 probes "
        "and 16 short IQ windows respectively. The pass-event prototype withheld all eight "
        "recorded fixes in both arms. The event fixture, stationary relocation check and network "
        "validation summary provide aggregate or fixture outcomes with no per-sample coordinates. "
        "[Saved embedded results](../../2026_11_19_receiver_duty/embedded/primary-results.zip)",
        "",
        "Rebuild the figures from the compact evidence with `.venv/bin/python -m "
        "tools.pipeline_eval.qualification.prototype_figures --out /tmp/prototype-figures`.",
        "",
    ]
    labels = {"c0": "Zero calibration", "fitted_c": "Fitted calibration"}
    columns = ["Modification", *(labels[arm] for arm in arms)]
    introduction.extend(("| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)))
    for item in (m for m in manifest if m["arm"] == arms[0]):
        links = [f"[Figure]({arm}/{item['id']}.png)" for arm in arms]
        introduction.append("| " + " | ".join((item["title"], *links)) + " |")
    for arm in arms:
        introduction.extend(
            (
                "",
                f"[{labels[arm]} PDF]({arm}/modifications.pdf) · "
                f"[{labels[arm]} samples]({arm}/modifications.csv)",
            )
        )
    write(out / "README.md", ("\n".join(introduction) + "\n").encode())
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--evidence", type=Path, default=REPORT)
    parser.add_argument("--arm", choices=(*ARMS, "both"), default="both")
    parser.add_argument(
        "--freeze-from", type=Path, help="archive saved outcomes from historical report trees"
    )
    args = parser.parse_args()
    if args.freeze_from:
        freeze(args.freeze_from, args.evidence)
    arms = ARMS if args.arm == "both" else (args.arm,)
    manifest = generate(args.out, arms=arms, evidence=args.evidence)
    print(f"{len(manifest) // len(arms)} prototype figures per calibration arm in {args.out}")


if __name__ == "__main__":
    main()
