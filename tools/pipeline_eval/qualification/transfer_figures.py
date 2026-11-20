"""Plot each measured receiver on the paired four-region transfer panel."""

import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from shlex import quote

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

from ..__main__ import read_predictions, write
from ..corpus import FROZEN, REPO, _read_frozen, _selection, references
from ..corpus import _index as index_frozen
from ..position_figure import TITLES, best_guess_field, save_png
from ..scoring import ARMS, distance_km, thresholds, validate_result
from .prefix_figures import csv_file

ORIGINAL = REPO / "reports/2026_11_18_pipeline_eval/predictions/transfer124"
REGION_REPORT = REPO / "reports/2026_11_19_receiver_frontend/regions"
LONGITUDE_GATE = "off_region_test"
ARC_CONTROL = "arc_validation"
METHOD_TITLES = {**TITLES, LONGITUDE_GATE: "Longitude controls on Doppler arc predictions"}
SOURCES = {
    name: ORIGINAL / f"{name}.jsonl.gz"
    for name in ("orbit_interp", "shape_score", "track_reduce", "projected_fit")
}
SOURCES["shared_doppler"] = REPO / "reports/2026_11_19_shared_receiver/transfer.jsonl.gz"
SOURCES["arc_validation"] = (
    REPO / "reports/2026_11_19_receiver_streaming/field/arc_validation.jsonl.gz"
)
SOURCES[LONGITUDE_GATE] = REGION_REPORT / "predictions.jsonl.gz"
DATASETS = {
    "DS29": ("Roof", 8, "One installation"),
    "StarLoc": ("Field", 11, "Eight nearby site groups"),
    "Altrincham": ("Field", 3, "Empty track windows"),
    "Synthetic": ("Simulation", 40, "Modeled receiver locations"),
}
CONDITIONS = {True: "Correct region offered", False: "Correct region omitted"}
ARMLABEL = {"c0": "Zero calibration", "fitted_c": "Fitted calibration"}
SERIES = {
    "candidate_published": ("Modification published", "#12634f", "o", True),
    "grid_published": ("Regional grid published", "#3b506f", "s", True),
    "candidate_best_guess": ("Modification best guess", "#12634f", "o", False),
    "grid_best_guess": ("Regional grid best guess", "#3b506f", "s", False),
}
FRESH_SERIES = {
    "candidate_published": ("Longitude gate published", "#12634f", "o", True),
    "arc_published": ("Arc control published", "#3b506f", "s", True),
    "candidate_best_guess": ("Longitude gate best guess", "#12634f", "o", False),
    "arc_best_guess": ("Arc control best guess", "#3b506f", "s", False),
}


def _roster():
    refs = list(references("transfer124"))
    groups = defaultdict(list)
    for case in refs:
        groups[case["recording"]].append(case)
    if len({case["id"] for case in refs}) != len(refs) or any(
        sorted(case["condition"] for case in pair) != ["missing", "present"]
        or any(pair[0][key] != pair[1][key] for key in ("group", "truth"))
        for pair in groups.values()
    ):
        raise ValueError(
            "transfer figures require one present and one missing offer per acquisition"
        )
    counts = Counter(pair[0]["group"] for pair in groups.values())
    if counts != {dataset: count for dataset, (_, count, _) in DATASETS.items()}:
        raise ValueError("acquisition counts differ from the frozen transfer roster")
    return refs


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _longitude_evidence(path):
    folder = path.parent
    lock = json.loads((folder / "prediction-lock.json").read_bytes())["files"]
    sealed = (path.name, "algorithm-lock.json", "sources.json", "holdout-receipt.json")
    for name in sealed:
        if _sha(folder / name) != lock.get(name):
            raise ValueError(f"longitude experiment file differs from its prediction seal: {name}")
    sources = json.loads((folder / "algorithm-lock.json").read_bytes())
    if sources.get(str((FROZEN / "provenance.json").relative_to(REPO))) != _sha(
        FROZEN / "provenance.json"
    ):
        raise ValueError("longitude replay used a different frozen corpus manifest")
    panels = {"transfer124": {}, "fresh80": {}}
    with gzip.open(path, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            panel = panels[record["panel"]]
            identifier = record["id"]
            if identifier in panel or set(record["results"]) != {LONGITUDE_GATE, ARC_CONTROL}:
                raise ValueError("duplicate query or unexpected method in longitude prediction")
            for result in record["results"].values():
                validate_result(result)
                if (
                    result["status"] not in ("ok", "withheld")
                    or not result.get("arms")
                    or result["arms"]["c0"] != result["arms"]["fitted_c"]
                ):
                    raise ValueError("longitude prediction must have matching calibration arms")
            endpoint = record["results"][LONGITUDE_GATE]["arms"]["c0"]
            original = record["results"][ARC_CONTROL]["arms"]["c0"]
            if endpoint.get("forced_latlon") != original.get("forced_latlon") or (
                endpoint["latlon"] is not None and endpoint["latlon"] != original["latlon"]
            ):
                raise ValueError("longitude control changed an arc nomination")
            panel[identifier] = record
    if {panel: len(rows) for panel, rows in panels.items()} != {"transfer124": 124, "fresh80": 80}:
        raise ValueError("longitude prediction roster is incomplete")
    archived = {r["observation_sha256"] for r in panels["transfer124"].values()}
    if any(r["observation_sha256"] in archived for r in panels["fresh80"].values()):
        raise ValueError("fresh confirmation reused a frozen transfer observation")
    return panels


def _longitude_transfer(records, matched_inputs):
    ids, files = _selection("transfer124")
    inputs = index_frozen(_read_frozen("inputs.jsonl", files))
    if records.keys() != set(ids):
        raise ValueError("longitude predictions do not match the archived transfer query IDs")
    matched = {}
    for case_id, record in records.items():
        archived = inputs[case_id]
        if (
            record["observation_sha256"] != archived["observation"]
            or record["catalog_sha256"] != archived["catalog"]
        ):
            raise ValueError(f"longitude experiment portable inputs differ for {case_id}")
        # The archived digest includes local adapter paths. Reuse it only after matching the
        # committed inputs and frozen offer roster by ID.
        matched[case_id] = dict(
            input_sha256=matched_inputs[case_id], result=record["results"][LONGITUDE_GATE]
        )
    return matched


def _predictions(method, refs, matched_inputs, longitude=None):
    path = SOURCES[method]
    records = (
        _longitude_transfer(longitude, matched_inputs)
        if method == LONGITUDE_GATE
        else read_predictions(path)
    )
    if records.keys() != {r["id"] for r in refs}:
        raise ValueError(f"saved {method} predictions do not cover the full transfer roster")
    if any(
        record["input_sha256"] != matched_inputs[case_id]
        or record["result"]["status"] not in ("ok", "withheld")
        or "arms" not in record["result"]
        for case_id, record in records.items()
    ):
        raise ValueError(f"saved {method} predictions contain unmatched inputs or decisions")
    return records


def _score_rows(method, arm, refs, predictions, source=None):
    rows = []
    candidates = SOURCES[method].relative_to(REPO) if source is None else source
    original = (FROZEN / "scores.csv").relative_to(REPO)
    for case in refs:
        record = predictions.get(case["id"], {})
        result = record.get("result", {})
        endpoint = result.get("arms", {}).get(arm, {})
        published = endpoint.get("latlon")
        guess_field = best_guess_field(method, endpoint)
        guess = endpoint.get(guess_field)
        if guess_field == "latlon":
            guess_field = "latlon (accepted pooled point)"
        grid = case["reference"]["grid_four"]["shape"]["latlon"]
        grid_guess = case["reference"]["grid_forced_four"]["shape"]["latlon"]
        series = (
            ("candidate_published", published, candidates, "latlon"),
            ("grid_published", grid, original, "grid_four"),
            ("candidate_best_guess", guess, candidates, guess_field),
            ("grid_best_guess", grid_guess, original, "grid_forced_four"),
        )
        for name, point, source, field in series:
            is_publication = name.endswith("_published")
            decision = (
                ("published" if point is not None else "withheld")
                if is_publication
                else ("estimate" if point is not None else "no_estimate")
            )
            if name.startswith("candidate_") and point is None:
                status = result.get("status", "ok" if "arms" in result else "missing")
                if status == "ok" and "arms" not in result:
                    decision = "stage_only"
                elif status not in ("ok", "withheld"):
                    decision = status
            rows.append(
                dict(
                    method=method,
                    arm=arm,
                    acquisition_id=case["recording"],
                    query_id=case["id"],
                    dataset=case["group"],
                    acquisition_kind=DATASETS[case["group"]][0],
                    correct_region_offered=case["condition"] == "present",
                    series=name,
                    decision=decision,
                    false_publication=point is not None and case["condition"] == "missing"
                    if is_publication
                    else None,
                    evidence=str(source),
                    source_field=field,
                    reason=result.get("reason") if name.startswith("candidate_") else None,
                    query_input_sha256=record.get("input_sha256"),
                    latitude_deg=point[0] if point is not None else None,
                    longitude_deg=point[1] if point is not None else None,
                    truth_latitude_deg=case["truth"][0],
                    truth_longitude_deg=case["truth"][1],
                    error_km=distance_km(point, case["truth"]),
                )
            )
    return rows


def _draw(rows, method, arm, *, live=False, fresh=False):
    groups = [name for name in DATASETS if any(r["dataset"] == name for r in rows)]
    single_group = len(groups) == 1
    height = {1: 6.1, 2: 7.5, 3: 9.0, 4: 10.4}[len(groups)]
    fig, panels = plt.subplots(
        len(groups), 2, figsize=(13.2, height), sharex=True, sharey=True, squeeze=False
    )
    fig.subplots_adjust(
        left=0.185,
        right=0.935,
        bottom=0.20 if single_group else 0.135,
        top=0.75 if single_group else 0.82,
        hspace=0.55,
        wspace=0.35,
    )
    fig.text(
        0.035,
        0.953,
        METHOD_TITLES.get(method, method),
        fontsize=22,
        weight="bold",
        color="#162c35",
    )
    calibration = ARMLABEL[arm] if live or method == "shared_doppler" else "Calibration-invariant"
    acquisitions = len({r["acquisition_id"] for r in rows})
    queries = len({r["query_id"] for r in rows})
    roster = f"{acquisitions} acquisitions, {queries} queries"
    comparison = "Fresh synthetic confirmation" if fresh else "Four-region transfer"
    fig.text(
        0.036,
        0.923,
        f"{comparison}  •  {calibration}  •  {roster}",
        fontsize=11,
        color="#4a5d66",
    )
    series_styles = FRESH_SERIES if fresh else SERIES
    handles = [
        Line2D(
            [],
            [],
            ls="none",
            marker=marker,
            ms=7,
            color=color,
            mfc=color if filled else "none",
            label=label,
        )
        for label, color, marker, filled in series_styles.values()
    ]
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.027, 0.903),
        ncol=4,
        fontsize=10,
        frameon=False,
        columnspacing=1.7,
        handletextpad=0.3,
    )
    for col, label in enumerate(CONDITIONS.values()):
        fig.text(
            panels[0, col].get_position().x0,
            0.788 if single_group else 0.846,
            label,
            fontsize=14,
            weight="bold",
            color="#162c35",
        )
    samples = defaultdict(list)
    for row in rows:
        samples[row["dataset"], row["correct_region_offered"], row["series"]].append(row)
    for i, dataset in enumerate(groups):
        kind, expected, description = DATASETS[dataset]
        acquisitions = len({r["acquisition_id"] for r in rows if r["dataset"] == dataset})
        area = panels[i, 0].get_position()
        simulated = dataset == "Synthetic"
        group_color = "#89540c" if simulated else "#233f4c"
        fig.text(0.036, area.y1 - 0.024, dataset, fontsize=14, weight="bold", color=group_color)
        fig.text(
            0.036,
            area.y1 - 0.047,
            f"{kind} · {acquisitions} acquisition{'s' if acquisitions != 1 else ''}",
            fontsize=9,
            color=group_color,
        )
        if acquisitions == expected:
            fig.text(0.036, area.y1 - 0.065, description, fontsize=9, color="#53656d")
        for j, offered in enumerate(CONDITIONS):
            ax = panels[i, j]
            decisions = samples[dataset, offered, "candidate_published"]
            count = len(decisions)
            if count == 0:
                ax.axis("off")
                ax.text(0.5, 0.5, "No queries", transform=ax.transAxes, ha="center")
                continue
            ax.set_facecolor("#fbf6ed" if simulated else "#eff5f7")
            ax.set_xscale("symlog", linthresh=0.1)
            ax.set_xlim(0, 22000)
            ax.set_ylim(-0.48, 3.48)
            ax.set_yticks([])
            ax.xaxis.set_major_locator(FixedLocator([0, 0.1, 1, 5, 50, 500, 5000, 20000]))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
            ax.xaxis.set_minor_locator(NullLocator())
            ax.tick_params(axis="x", labelsize=9, color="#9eadb3", labelcolor="#425964")
            ax.spines[["left", "right", "top"]].set_visible(False)
            ax.spines["bottom"].set_color("#a6b5bc")
            ax.set_axisbelow(True)
            ax.grid(axis="x", color="white", linewidth=1.0)
            ax.axvline(5, color="#a4b6bb", linewidth=0.9, linestyle=":")
            ax.axhline(1.5, color="white", linewidth=1.0)
            pub, held = [], []
            for k, (series, (_, color, marker, filled)) in enumerate(series_styles.items()):
                sample = samples[dataset, offered, series]
                errors = sorted(r["error_km"] for r in sample if r["error_km"] is not None)
                y = 3 - k
                offsets = np.resize([0, -0.16, 0.16, -0.30, 0.30], len(errors))
                ax.scatter(
                    errors,
                    y + offsets,
                    s=16,
                    marker=marker,
                    edgecolor=color,
                    facecolor=color if filled else "none",
                    linewidth=0.8,
                    alpha=0.83,
                )
                count_coordinates = ax.get_yaxis_transform()
                ax.plot(
                    1.029,
                    y,
                    marker=marker,
                    ms=4,
                    color=color,
                    mfc=color if filled else "none",
                    transform=count_coordinates,
                    clip_on=False,
                )
                ax.text(
                    1.057,
                    y,
                    f"{len(errors)}/{count}",
                    transform=count_coordinates,
                    va="center",
                    fontsize=9,
                    color=color,
                )
                if filled:
                    pub.append(thresholds(errors)["5"] if offered else len(errors))
                    held.append(sum(r["decision"] == "withheld" for r in sample))
            label = "Within 5 km" if offered else "False publications"
            count_offset = -0.15 if i < len(groups) - 1 else -0.37
            if single_group:
                count_offset = -0.13
            ax.text(
                0,
                count_offset,
                f"{label}  {pub[0]}/{count} vs {pub[1]}/{count}   |   "
                f"Withheld  {held[0]}/{count} vs {held[1]}/{count}",
                transform=ax.transAxes,
                va="top",
                fontsize=9,
                color="#384e59",
            )
            unmeasured = sum(r["decision"] not in ("published", "withheld") for r in decisions)
            if unmeasured:
                ax.text(
                    0.02,
                    0.50,
                    f"Position unmeasured on {unmeasured}/{count} queries",
                    transform=ax.transAxes,
                    va="center",
                    color="#384e59",
                    fontsize=9,
                )
    fig.supxlabel(
        "Horizontal error (km, logarithmic above 0.1 km)", y=0.041, fontsize=10, color="#384e59"
    )
    compared = "longitude gate vs arc control" if fresh else "modification vs regional grid"
    fig.text(
        0.036,
        0.014,
        "Dots show returned coordinates. Counts use all queries in each group. "
        f"Comparisons read {compared}.",
        fontsize=9,
        color="#4a5d66",
    )
    return fig


def write_run_figures(refs, predictions, folder, method):
    for arm in ARMS:
        rows = _score_rows(method, arm, refs, predictions, source="predictions.jsonl")
        fig = _draw(rows, method, arm, live=True)
        try:
            save_png(fig, folder / f"position-errors-{arm}.png")
        finally:
            plt.close(fig)


def _fresh_score_rows(predictions, source, arm):
    path = source.with_name("scores.json")
    labels = [
        row
        for row in json.loads(path.read_bytes())["cases"]
        if row["panel"] == "fresh80" and row["arm"] == arm
    ]
    scored = {(r["id"], r["method"]): r for r in labels}
    expected = {(case_id, m) for case_id in predictions for m in (LONGITUDE_GATE, ARC_CONTROL)}
    if len(scored) != len(labels) or set(scored) != expected:
        raise ValueError("fresh score rows do not match the sealed predictions")
    outcomes = (
        ("candidate_published", LONGITUDE_GATE, "latlon", "error_km"),
        ("arc_published", ARC_CONTROL, "latlon", "error_km"),
        ("candidate_best_guess", LONGITUDE_GATE, "forced_latlon", "forced_error_km"),
        ("arc_best_guess", ARC_CONTROL, "forced_latlon", "forced_error_km"),
    )
    pairs = defaultdict(list)
    rows = []
    for case_id, record in predictions.items():
        pair = record["observation_sha256"]
        label = scored[case_id, LONGITUDE_GATE]
        if (
            not record.get("query_sha256")
            or label["condition"] not in ("present", "missing")
            or label["condition"] != scored[case_id, ARC_CONTROL]["condition"]
            or label["group"] != scored[case_id, ARC_CONTROL]["group"]
        ):
            raise ValueError("fresh matched offers lack scoring metadata")
        pairs[pair].append((label["condition"], label["group"], record["catalog_sha256"]))
        offered = label["condition"] == "present"
        for series, method, point_key, error_key in outcomes:
            result = record["results"][method]
            point = result["arms"][arm].get(point_key)
            score = scored[case_id, method]
            error = score[error_key]
            if (point is None) != (error is None) or score["published"] != (
                result["arms"][arm]["latlon"] is not None
            ):
                raise ValueError("fresh score and sealed publication disagree")
            published = point_key == "latlon"
            decision = (
                ("published" if point is not None else "withheld")
                if published
                else ("estimate" if point is not None else "no_estimate")
            )
            rows.append(
                dict(
                    method=method,
                    arm=arm,
                    acquisition_id=pair,
                    query_id=case_id,
                    dataset="Synthetic",
                    acquisition_kind="Simulation",
                    scene=label["group"],
                    correct_region_offered=offered,
                    series=series,
                    decision=decision,
                    false_publication=(point is not None and not offered) if published else None,
                    evidence=str(source.relative_to(REPO)),
                    scoring_evidence=str(path.relative_to(REPO)),
                    source_field=point_key,
                    reason=result["reason"],
                    query_input_sha256=record["query_sha256"],
                    latitude_deg=point[0] if point is not None else None,
                    longitude_deg=point[1] if point is not None else None,
                    error_km=error,
                )
            )
    if len(pairs) != 40 or any(
        sorted(item[0] for item in pair) != ["missing", "present"] or pair[0][1:] != pair[1][1:]
        for pair in pairs.values()
    ):
        raise ValueError("fresh confirmation requires exactly 40 matched acquisition pairs")
    return rows


def _write_fresh(out, predictions, arms):
    source = SOURCES[LONGITUDE_GATE]
    for arm in arms:
        rows = _fresh_score_rows(predictions, source, arm)
        fig = _draw(rows, LONGITUDE_GATE, arm, fresh=True)
        try:
            save_png(fig, out / arm / "fresh80.png")
            pdf = io.BytesIO()
            fig.savefig(pdf, format="pdf", metadata=dict(CreationDate=None, ModDate=None))
            write(out / arm / "fresh80.pdf", pdf.getvalue())
        finally:
            plt.close(fig)
        csv_file(out / arm / "fresh80.csv", rows)


def _index(out, methods, arms):
    content = [
        "# Position transfer by receiver modification",
        "",
        "The 124 four-region queries come from 62 acquisitions. Each acquisition appears once",
        "with its correct region offered and once with it omitted. The DS29 roof recordings",
        "also appear in the roof comparison. StarLoc supplies 11 captures across eight nearby",
        "site groups. The three Altrincham field windows have no usable tracks. The 40 synthetic",
        "acquisitions are simulations. This is a retrospective replay of the original blind study.",
        "",
        "Each dot is a returned coordinate. Each count uses all attempts in its group and offer",
        "condition. A published coordinate is a false publication whenever the correct region was",
        "omitted. The best-guess series show the diagnostic coordinates the receivers recorded.",
        "Withholding can leave a best guess or no estimate. Projected fit saves its accepted",
        "pooled point as the published coordinate. When withholding, it records a diagnostic",
        "point if available. The four-offer controls are the original regional grid's published",
        "and best-guess coordinates. The original v5 reference applies to the fixed roof tile.",
        "",
        "Orbital reuse, horizon screening, track compression, projected fit, later-sample",
        "validation, longitude controls and the regional grid use the same outputs in both",
        "calibration settings.",
        "Shared Doppler has a matched zero-versus-fitted calibration comparison. Each",
        "retrospective CSV has four rows per query and method, including attempts without",
        "coordinates. Coordinates and truth are in degrees. Error is horizontal distance in km.",
        "",
    ]
    for arm in arms:
        content.extend(
            [
                f"## {ARMLABEL[arm]}",
                "",
                f"[Figure book]({arm}/modifications.pdf) · "
                f"[Query-level data]({arm}/modifications.csv)",
                "",
                *(f"- [{METHOD_TITLES[method]}]({arm}/{method}.png)" for method in methods),
                "",
            ]
        )
        if LONGITUDE_GATE in methods:
            content.extend(
                [
                    f"[Fresh synthetic confirmation figure]({arm}/fresh80.png) · "
                    f"[PDF]({arm}/fresh80.pdf) · "
                    f"[Fresh query-level data]({arm}/fresh80.csv)",
                    "",
                    "The fresh figure uses the matched arc control from the new 40-acquisition",
                    "draw. The retrospective figure compares with the archived regional grid.",
                    "The fresh CSV lists publications and best guesses for both methods.",
                    "",
                ]
            )
    output = out.resolve()
    if output.is_relative_to(REPO):
        output = output.relative_to(REPO)
    arm_option = "--arm both" if len(arms) == 2 else f"--arm {arms[0]}"
    requested = " ".join(f"--variant {quote(method)}" for method in methods)
    content.extend(
        [
            "Rebuild from the saved predictions and frozen reference scores.",
            "",
            "```sh",
            ".venv/bin/python -m tools.pipeline_eval figures --panel transfer124 "
            f"{arm_option} {requested} --out {quote(str(output))}",
            "```",
            "",
        ]
    )
    write(out / "README.md", "\n".join(content).encode())


def generate(out, arms, methods=None):
    methods = list(dict.fromkeys(methods or SOURCES))
    if any(method not in SOURCES for method in methods):
        raise ValueError(f"choose a measured transfer124 variant from {', '.join(SOURCES)}")
    if not arms or set(arms) - set(ARMS):
        raise ValueError("choose the c0 or fitted_c calibration arm")
    refs = _roster()
    matched_inputs = {
        case_id: r["input_sha256"]
        for case_id, r in read_predictions(SOURCES["orbit_interp"]).items()
    }
    longitude = _longitude_evidence(SOURCES[LONGITUDE_GATE]) if LONGITUDE_GATE in methods else {}
    predictions = {
        method: _predictions(method, refs, matched_inputs, longitude.get("transfer124"))
        for method in methods
    }
    out = Path(out)
    for arm in arms:
        destination = out / arm
        rows, pdf = [], io.BytesIO()
        metadata = dict(Title="Four-region position transfer", CreationDate=None, ModDate=None)
        with PdfPages(pdf, metadata=metadata) as book:
            for method, records in predictions.items():
                sample = _score_rows(method, arm, refs, records)
                rows.extend(sample)
                fig = _draw(sample, method, arm)
                try:
                    save_png(fig, destination / f"{method}.png")
                    book.savefig(fig, facecolor="white")
                finally:
                    plt.close(fig)
        write(destination / "modifications.pdf", pdf.getvalue())
        csv_file(destination / "modifications.csv", rows)
    if longitude:
        _write_fresh(out, longitude["fresh80"], arms)
    _index(out, methods, arms)
