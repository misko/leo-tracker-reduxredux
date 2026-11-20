"""Score the two additional complete waveforms with four original v5 controls."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ROLES
from . import diagnostic_whole_results as diagnostic
from . import fresh_replay_results as previous
from . import new_waveforms as study
from . import screening_figures, wide_full_v5
from . import whole_center_union_results as union
from .exact_wide_iq_results import timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHODS = {"control": study.STOCK, "candidate": study.METHOD}
PREDICTIONS = "positions.jsonl.gz"
REFERENCES = previous.ROOF_REFERENCES


def original_audit(out):
    seal = previous.sealed(out, "reference-prediction-lock.json")
    frozen = whole_iq.read(out / "reference-source-lock.json")
    stored = out / "reference-binding-audit.json"
    if stored.is_file():
        ledger = whole_iq.read(stored)
        if ledger["reference_prediction_sha256"] != _sha(out / "reference-prediction-lock.json"):
            raise ValueError("v5 binding audit uses another prediction set")
        return
    records = {}
    for row in rows_from(out / "fresh-v5.jsonl.gz"):
        role = row["method"]
        result = row["result"]
        request = Path(row["service"]["command"][-2]) / "request.json"
        path = whole_iq.checked(request, frozen["requests"][role]["request_sha256"])
        job = whole_iq.read(path)
        if (
            job["job"]["evaluation_reference"] is not None
            or job["causal_snapshots"] != frozen["case"]["orbit_snapshots"]
            or job["job"]["native_input"]["sha256"] != "sha256:" + row["native_sha256"]
        ):
            raise ValueError("a capture-era fit used different native or causal factors")
        canonical = wide_full_v5.digest(job)
        if result["status"] == "ok" and result["metrics"]["request_sha256"] != canonical:
            raise ValueError("the full original role differs from its actual measured request")
        records[role] = dict(
            status=result["status"],
            request_sha256=canonical,
            bytes_sha256=frozen["requests"][role]["request_sha256"],
            causal_sha256=wide_full_v5.digest(job["causal_snapshots"]),
            native_sha256=row["native_sha256"],
            artifact_sha256=result.get("evidence", {}).get("sha256"),
        )
    if set(records) != set(ROLES):
        raise ValueError("all four genuine original roles must have a terminal receipt")
    save_json(
        stored,
        dict(
            cases=seal["cases"],
            roles=records,
            reference_prediction_sha256=_sha(out / "reference-prediction-lock.json"),
        ),
    )


def dashboard(out, groups, rows, evidence):
    charts = []
    for key, ids in groups.items():
        name = f"{key}-figure-positions.jsonl.gz"
        matches = list(diagnostic.PHYSICAL_KEYS)
        pack(out / name, [r for r in rows if r["id"] in ids])
        seal = f"{key}-figure-lock.json"
        files = {path: _sha(out / path) for path in (*evidence, name)}
        save_json(out / seal, dict(cases=ids, files=files))
        chart = dict(
            id=f"new-waveforms-{key}",
            method=study.METHOD,
            scope="roof",
            cases="sealed",
            title=(
                "Stock and fifth center on two additional complete saved-IQ recordings"
                if key == "all"
                else f"New matched whole-IQ comparison on {ids[0]}"
            ),
            caption=(
                "One roof. Complete individually selected recordings with original 25 km offer, "
                "authentic causal catalogue, same phase release and both calibration arms."
            ),
            seal=seal,
            provenance=evidence,
            series=[
                dict(
                    key="one",
                    label="Keep four + add fifth",
                    file=name,
                    value=study.METHOD,
                    native_field="paired_capture_sha256",
                ),
                dict(
                    key="stock",
                    label="Stock wide",
                    file=name,
                    value=study.STOCK,
                    native_field="paired_capture_sha256",
                    match=matches,
                ),
            ],
        )
        if any(ident.startswith("DS29") for ident in ids):
            chart["roof_references"] = REFERENCES
        charts.append(chart)
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


def score(out):
    terminal = previous.sealed(out, "prediction-lock.json")
    original_audit(out)
    rows = rows_from(out / PREDICTIONS)
    plan = whole_iq.read(out / "source-lock.json")
    (ds26,) = [ident for ident in terminal["cases"] if ident.startswith("DS26")]
    (ds29,) = [ident for ident in terminal["cases"] if ident.startswith("DS29")]
    _, archived = held_references(None, [ds26])
    refs = {ds26: archived[0], ds29: previous.references(out, plan["cases"][ds29])}
    scores = previous.geographic(rows, refs)
    csv_file(out / "scores.csv", scores)
    groups = dict(all=terminal["cases"], ds26=[ds26], ds29=[ds29])
    save_json(out / "summary.json", previous.distribution_rows(scores, groups))
    pairs, _ = union.paired_scores(scores)
    csv_file(out / "calibration.csv", pairs)
    resources = whole_iq.read(out / "resources.json")
    visits = [row for row in rows_from(out / "visits.jsonl.gz") if row["status"] == "processed"]
    csv_file(out / "deadlines.csv", timing_rows(resources, visits))
    save_json(out / "visit-coverage.json", diagnostic.visit_coverage(visits))
    evidence = [
        "prediction-lock.json",
        "raw-prediction-lock.json",
        "reference-prediction-lock.json",
        "reference-binding-audit.json",
        "fresh-v5.jsonl.gz",
        "roof-authority.json",
        "scores.csv",
        "summary.json",
        "calibration.csv",
        "deadlines.csv",
        "visit-coverage.json",
    ]
    dashboard(out, groups, rows, evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("raw-seal", "seal", "score"))
    parser.add_argument("--work", type=local_output, default=study.WORK)
    parser.add_argument("--out", type=local_output, default=study.REPORT)
    args = parser.parse_args()
    with study.context(), patch.object(previous, "METHODS", METHODS):
        if args.action == "raw-seal":
            previous.raw_seal(args.work, args.out)
        elif args.action == "seal":
            previous.seal(args.work, args.out)
        else:
            score(args.out)
