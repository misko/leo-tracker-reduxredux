"""Describe how the sealed compact and exception-retry results vary across capture dates."""

import argparse
import csv
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .. import corpus
from ..__main__ import local_output, save_json
from ..scoring import ARMS, distribution
from .full_receiver_comparison import seal, sha
from .prefix_figures import csv_file

STUDY = corpus.REPO / "reports/2026_11_19_receiver_screening/integration"
METHODS = ("baseline", "stock", "router")


def grouped(rows, dates):
    yield "full", "all", rows
    for day in sorted(set(dates.values()) - {None}):
        yield "day", day, [r for r in rows if dates[r["id"]] == day]
        yield "omit", day, [r for r in rows if dates[r["id"]] != day]
    missing = [r for r in rows if dates[r["id"]] is None]
    if missing:
        yield "day", "unknown", missing


def measurements(rows, method):
    column = method + "_error_km"
    published = [float(r[column]) for r in rows if r[column]]
    pairs = [
        (float(r["baseline_error_km"]), float(r[column]))
        for r in rows
        if r["baseline_error_km"] and r[column]
    ]
    quantiles = distribution(published)
    base_q = distribution([b for b, _ in pairs])
    test_q = distribution([t for _, t in pairs])
    return dict(
        offered=len(rows),
        published=len(published),
        within_5km=sum(x <= 5 for x in published),
        median_km=quantiles["p50"],
        p95_km=quantiles["p95"],
        paired=len(pairs),
        paired_within_110pct=sum(t <= 1.10 * b for b, t in pairs),
        paired_test_p50=test_q["p50"],
        paired_original_p50=base_q["p50"],
        paired_test_p95=test_q["p95"],
        paired_original_p95=base_q["p95"],
    )


def publish(out):
    source = STUDY / "failed-only"
    receipt = seal(source, "score-lock.json", ("scores.csv",))
    if receipt["prediction_lock_sha256"] != sha(source / "prediction-lock.json"):
        raise ValueError("scored exception routing differs from the locked predictions")
    ids, authority = corpus._selection("ds26-all159")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", authority))
    dates = {}
    for ident in ids:
        stamp = inputs[ident].get("cutoff_utc_ns")
        dates[ident] = (
            datetime.fromtimestamp(stamp // 10**9, UTC).date().isoformat()
            if stamp is not None
            else None
        )
    with (source / "scores.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    if Counter((r["id"], r["arm"]) for r in rows) != Counter((i, a) for i in ids for a in ARMS):
        raise ValueError("incomplete or duplicated calibration and recording rows")
    summary = []
    for arm in ARMS:
        for scope, day, subset in grouped([r for r in rows if r["arm"] == arm], dates):
            for method in METHODS:
                summary.append(
                    dict(
                        scope=scope,
                        date_utc=day,
                        method=method,
                        arm=arm,
                        **measurements(subset, method),
                    )
                )
    csv_file(out / "by-date.csv", summary)
    save_json(
        out / "receipt.json",
        dict(
            date_basis="cutoff_utc_ns",
            input_manifest=authority["inputs.jsonl"],
            source_score_sha256=sha(source / "scores.csv"),
            predictions=receipt["prediction_lock_sha256"],
            scored_output=sha(out / "by-date.csv"),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=STUDY / "time-sensitivity")
    publish(local_output(parser.parse_args().out))
