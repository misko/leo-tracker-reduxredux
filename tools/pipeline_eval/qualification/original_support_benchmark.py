"""Render and summarize sealed original-support studies at their own boundaries."""

import csv
from collections import defaultdict, deque
from pathlib import Path

from .. import whole_iq
from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distribution
from . import screening_figures, study_benchmark
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .prefix_figures import csv_file

ROOT = screening_figures.REPORT / "original-support"
SCOPES = (
    "queue-selection",
    "paced-original",
    "paced-rf",
    "frequency-schedule",
    "scheduled-waveform",
    "original-kernel",
    "lane-screen",
    "solver-reuse",
    "outside-option",
    "orbit-continuity",
    "prepared-waveform",
    "rotating-dwell",
)
TABLES = {
    "timing.csv",
    "stage.csv",
    "resources.csv",
    "scores.csv",
    "pacing.csv",
    "paced.csv",
    "arrival-decomposition.csv",
    "cache.csv",
    "costs.csv",
    "wall.csv",
}
GROUPS = (
    "method",
    "mode",
    "role",
    "policy",
    "workers",
    "cores",
    "arm",
    "cohort",
    "condition",
    "kind",
    "status",
    "clock",
    "case",
    "timing_basis",
)


def catalog(root):
    index, stages, ledger, assets, locks = [], [], {}, {}, {}
    for scope in SCOPES:
        folder = root / scope
        count = 0
        for name in ("figures.json", "stage-figure.json"):
            path = folder / name
            if not path.is_file():
                continue
            spec = whole_iq.read(path)
            charts = spec["charts"] if name == "figures.json" else [spec]
            for chart in charts:
                receipt = sealed(folder, chart["seal"])
                locks[f"{scope}/{chart['seal']}"] = _sha(folder / chart["seal"])
                for filename, digest in receipt["files"].items():
                    key = scope, filename
                    if assets.setdefault(key, digest) != digest:
                        raise ValueError(f"conflicting sealed evidence for {scope}/{filename}")
                item = dict(
                    id=chart["id"],
                    descriptor=f"original-support/{scope}/{name}",
                    descriptor_sha256=_sha(path),
                    seal=chart["seal"],
                    seal_sha256=locks[f"{scope}/{chart['seal']}"],
                )
                if name == "figures.json":
                    index.append(item)
                    count += 1
                else:
                    stages.append(
                        dict(item, **{k: chart.get(k) for k in ("boundary", "image", "csv", "pdf")})
                    )
        for name in (
            "forecast-lock.json",
            "prediction-lock.json",
            "raw-prediction-lock.json",
            "timing-lock.json",
            "result-lock.json",
            "score-lock.json",
        ):
            path = folder / name
            if path.is_file():
                receipt = sealed(folder, name)
                locks[f"{scope}/{name}"] = _sha(path)
                for filename, digest in receipt["files"].items():
                    if assets.setdefault((scope, filename), digest) != digest:
                        raise ValueError(f"conflicting sealed evidence for {scope}/{filename}")
        stage = any(row["descriptor"].startswith(f"original-support/{scope}/") for row in stages)
        state = (
            "position_charts"
            if count
            else "stage_only"
            if stage
            else "terminal_without_chart"
            if any(key.startswith(f"{scope}/") for key in locks)
            else "awaiting_seal"
        )
        ledger[scope] = dict(state=state, position_charts=count, stage_available=stage)
    if len({r["id"] for r in index}) != len(index):
        raise ValueError("benchmark source chart IDs must be unique")
    return index, stages, ledger, assets, locks


def score_charts(studies, chart_scopes):
    scores, rf, books = [], [], {}
    for arm in ARMS:
        book = books[arm] = []
        for study in studies:
            scope = chart_scopes[study.id]
            page = study.page(arm)
            book.append(page)
            output = study_benchmark.summarize(study, page, arm)
            baseline = {r.recording: r.error_km for r in page.rows if r.series == "baseline"}
            case_refs = defaultdict(deque)
            if study.scope != "roof":
                for case, query in study.references.items():
                    for series in study.predictions:
                        case_refs[query["condition"], query["recording"], series].append(case)
            rf_by_series = defaultdict(list)
            for row in page.rows:
                if row.series not in study.predictions and row.series not in ROLES:
                    continue
                case = (
                    row.recording
                    if study.scope == "roof"
                    else case_refs[row.dataset, row.recording, row.series].popleft()
                )
                if row.series in ROLES:
                    value, result = {}, {}
                    endpoint = study.references[case]["reference"][row.series][arm]
                else:
                    value = study.predictions[row.series][case]
                    result = value["result"]
                    endpoint = result.get("arms", {}).get(arm, {})
                rf_hz = endpoint.get("rf_rms_hz")
                v5_km = baseline.get(row.recording)
                match = {
                    f"within_{pct}pct": None
                    if v5_km is None
                    else row.error_km is not None and row.error_km <= (1 + pct / 100) * v5_km
                    for pct in (5, 10)
                }
                rf_by_series[row.dataset, row.series].append(rf_hz)
                rf_by_series["all", row.series].append(rf_hz)
                rf.append(
                    dict(
                        scope=scope,
                        chart=study.id,
                        arm=arm,
                        cohort=row.dataset,
                        id=case,
                        recording=row.recording,
                        series=row.series,
                        method=value.get("method", f"original_v5_{row.series}"),
                        decision=row.decision,
                        error_km=row.error_km,
                        original_v5_error_km=v5_km,
                        rf_rms_hz=rf_hz,
                        frequency_score=result.get("metrics", {}).get(f"{arm}_frequency_score"),
                        position_fit_wall_s=(value.get("position_resources") or {}).get("wall_s"),
                        **match,
                    )
                )
            for row in output:
                dist = distribution(rf_by_series[row["cohort"], row["series"]])
                scores.append(
                    dict(
                        scope=scope,
                        **row,
                        rf_n=dist["n"],
                        rf_p50_hz=dist["p50"],
                        rf_p95_hz=dist["p95"],
                    )
                )
    return scores, rf, books


def cost_summary(root, assets):
    """Summarize original measured fields by source file and identical scope keys."""
    out = []
    for (scope, name), digest in sorted(assets.items()):
        if name not in TABLES:
            continue
        source = whole_iq.checked(root / scope / name, digest)
        values = defaultdict(list)
        with source.open(newline="") as handle:
            for row in csv.DictReader(handle):
                identity = " ".join(f"{k}={row[k]}" for k in GROUPS if row.get(k)) or "all"
                for field, v in row.items():
                    if not v or not (
                        field in ("wall_ms", "cpu_ms", "wall_s", "cpu_s")
                        or field.endswith(("_ns", "_ms", "_s"))
                    ):
                        continue
                    if field.endswith(("utc_ns", "monotonic_ns", "sample_ns")) or field in (
                        "completed_by_300_s",
                        "pending_at_300_s",
                        "within_20ms",
                        "within_20_ms",
                    ):
                        continue
                    try:
                        number = float(v)
                    except ValueError:
                        continue
                    values[(identity, field)].append(number)
        for (identity, field), data in values.items():
            dist = distribution(data)
            evidence = clock_boundary(scope, name, field)
            out.append(
                dict(
                    scope=scope,
                    source=name,
                    group=identity,
                    metric=field,
                    samples=dist["n"],
                    evidence=evidence,
                    p50=dist["p50"],
                    p95=dist["p95"],
                    max=dist["max"],
                    sha256=digest,
                )
            )
    return out


def clock_boundary(scope, source, metric):
    if metric in ("capture_span_s", "last_due_s", "delivery_span_s"):
        return "recorded delivery span"
    if metric.startswith(("position_", "measured_position_")) or (
        source == "resources.csv"
        and scope in ("solver-reuse", "rotating-dwell", "frequency-schedule")
    ):
        return "measured position fit"
    if (
        scope == "queue-selection"
        and source == "timing.csv"
        or source
        in (
            "paced.csv",
            "pacing.csv",
        )
    ):
        return "modeled service"
    if scope in ("paced-original", "paced-rf"):
        return "measured recorded-arrival replay"
    if scope in ("original-kernel", "lane-screen", "scheduled-waveform", "prepared-waveform"):
        return "measured detector replay"
    return "sealed reported clock"


def run(out, *, root=ROOT):
    from . import original_support_overlap as overlap

    index, stages, ledger, assets, locks = catalog(root)
    save_json(out / "chart-index.json", dict(charts=index, stages=stages))
    charts = {item["id"]: item["descriptor"].split("/")[1] for item in index}
    studies = [
        study
        for scope in SCOPES
        if scope in charts.values()
        for study in screening_figures.charts(
            methods=[i for i, group in charts.items() if group == scope], evidence=root / scope
        )
    ]
    scores, rf, books = score_charts(studies, charts)
    queue, queue_positions, periodic, checks = overlap.compare(root)
    products = dict(
        summary=scores,
        **{
            "position-rf": rf,
            "timing-summary": cost_summary(root, assets),
            "queue-overlap": queue,
            "queue-position": queue_positions,
            "periodic-position": periodic,
        },
    )
    for name, rows in products.items():
        if rows:
            csv_file(out / f"{name}.csv", rows)
    save_json(out / "overlap.json", checks)
    study_benchmark.render(out, books)
    manifest = out / "charts/manifest.json"
    chart_files = {"charts/index.html", "charts/manifest.json"}
    chart_files.update(
        f"charts/{entry[key]}"
        for entry in whole_iq.read(manifest)
        for key in ("image", "csv", "pdf")
    )
    files = [
        "chart-index.json",
        "overlap.json",
        *(f"{name}.csv" for name, rows in products.items() if rows),
        *sorted(chart_files),
    ]
    save_json(
        out / "benchmark-lock.json",
        dict(
            schema="original-support/v1",
            studies=ledger,
            source_locks=locks,
            files={name: _sha(out / name) for name in files},
            chart_manifest_sha256=_sha(manifest),
            protocol_sha256=_sha(ROOT / "benchmark/PROTOCOL.md"),
            programs={path.name: _sha(path) for path in (Path(__file__), Path(overlap.__file__))},
        ),
    )
    print(f"{len(studies)} sealed position comparisons in {out / 'charts/index.html'}")
    for scope, row in ledger.items():
        print(scope, row["state"])
