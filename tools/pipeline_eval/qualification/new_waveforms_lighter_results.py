"""Compare the qualified lighter whole-IQ arm on the same fixed new waveforms."""

import argparse
import gzip
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import diagnostic_whole_results as diagnostic
from . import fifth_crossover_results as crossover
from . import fresh_replay_results as paired
from . import frontier_whole_replay_results as traces
from . import new_waveforms as study
from . import new_waveforms_lighter as lighter
from . import screening_figures
from . import whole_band_results as measured
from . import whole_center_union_results as union
from .exact_wide_iq_results import encoded, normalized_document, timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .winner_stream_results import scientific_result

REPORT = study.REPORT / "lighter-comparison"
ROWS = "positions.jsonl.gz"
VISITS = "lighter-visits.jsonl.gz"


def seal(work, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("the separately qualified third arm is already sealed")
    source, active = lighter.binding(work)
    base = paired.sealed(study.REPORT, "prediction-lock.json")
    link = paired.sealed(study.REPORT, "raw-prediction-lock.json")
    rows = rows_from(study.REPORT / "positions.jsonl.gz")
    controls = {r["id"]: r for r in rows if r["method"] == study.METHOD}
    (old_native, old_resources) = (
        whole_iq.read(study.REPORT / name) for name in ("raw-authority.json", "resources.json")
    )
    original_traces = rows_from(study.REPORT / "visits.jsonl.gz")
    audit, resources, lighter_traces, names = {}, {}, [], []
    for ident, case in source["cases"].items():
        run = work / ident / lighter.CANDIDATE
        row, receipt, archive = measured.attempt(
            work,
            ident,
            lighter.CANDIDATE,
            source,
            method=lighter.METHOD,
        )
        rows.append(row)
        resources[ident] = dict(lighter=receipt)
        baseline = controls[ident]
        if any(row[key] != baseline[key] for key in diagnostic.PHYSICAL_KEYS):
            raise ValueError("lighter detector changed the paired waveforms or capture request")
        check = audit[ident] = dict(
            original_status=baseline["result"]["status"],
            lighter_status=row["result"]["status"],
            raw_complete=archive is not None,
        )
        if archive is not None:
            diagnostic.matched_physical(old_resources[ident]["candidate"], receipt, case)
            _, actual = diagnostic.trace_bundle(ident, "lighter", run, receipt)
            check["telemetry"] = traces.scout_trace(run, actual)
            check["union_admission"] = union.union_telemetry(actual)
            stock = [r for r in original_traces if r["id"] == ident and r["role"] == "candidate"]
            check["same_scout"] = crossover.compare_hints(stock, actual)
            check.update(traces.compare_probes(stock, actual))
            raw_native = whole_iq.read(run / "raw.json")
            observed = normalized_document(whole_iq.read(archive))
            digest = sha256(encoded(observed)).hexdigest()
            check["same_normalized_native"] = (
                digest == old_native[ident]["candidate"]["logical_native_sha256"]
            )
            check["lighter_native_sha256"] = raw_native["native_sha256"]
            name = f"native/{ident}.json.gz"
            write(out / name, gzip.compress(archive.read_bytes(), mtime=0))
            names.append(name)
            lighter_traces.extend(actual)
        check["exact_scientific_positions"] = (
            encoded(scientific_result(baseline["result"]))
            == encoded(scientific_result(row["result"]))
            if baseline["result"]["status"] == row["result"]["status"] == "ok"
            else None
        )
        log = run / "service.log"
        if log.is_file():
            name = f"{ident}.service.log"
            write(out / name, whole_iq.checked(log, receipt["service"]["log_sha256"]).read_bytes())
            names.append(name)
    traces.protect_resources(resources)
    pack(out / ROWS, rows)
    pack(out / VISITS, lighter_traces)
    save_json(out / "parity.json", audit)
    save_json(out / "resources.json", resources)
    save_json(
        out / "pair-authority.json",
        dict(
            paired_prediction_sha256=_sha(study.REPORT / "prediction-lock.json"),
            paired_raw_sha256=_sha(study.REPORT / "raw-prediction-lock.json"),
            paired_cases=link["cases"],
            lighter_source_sha256=_sha(study.REPORT / lighter.PIN),
            qualification_sha256=active["qualification_sha256"],
        ),
    )
    for name in (lighter.PIN, lighter.WITNESS):
        write(out / name, (study.REPORT / name).read_bytes())
        names.append(name)
    names.extend((ROWS, VISITS, "pair-authority.json", "resources.json", "parity.json"))
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=base["cases"],
            files={name: _sha(out / name) for name in names},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score(out):
    lock = paired.sealed(out, "prediction-lock.json")
    reference = study.REPORT / "reference-prediction-lock.json"
    paired.sealed(study.REPORT, reference.name)
    rows = rows_from(out / ROWS)
    (ds26,) = [ident for ident in lock["cases"] if ident.startswith("DS26")]
    (ds29,) = [ident for ident in lock["cases"] if ident.startswith("DS29")]
    _, original = held_references(None, [ds26])
    plan = whole_iq.read(study.REPORT / "source-lock.json")
    refs = {ds26: original[0], ds29: paired.references(study.REPORT, plan["cases"][ds29])}
    csv_file(out / "scores.csv", paired.geographic(rows, refs))
    pair = whole_iq.read(study.REPORT / "resources.json")
    evidence = whole_iq.read(out / "resources.json")
    roles = {case: dict(pair[case], **evidence[case]) for case in lock["cases"]}
    trace = rows_from(study.REPORT / "visits.jsonl.gz") + rows_from(out / VISITS)
    times = timing_rows(roles, [r for r in trace if r["status"] == "processed"])
    csv_file(out / "deadlines.csv", times)
    reference_files = tuple(paired.ROOF_REFERENCES.values())
    for name in reference_files:
        write(out / name, (study.REPORT / name).read_bytes())
    files = [
        ROWS,
        "prediction-lock.json",
        "pair-authority.json",
        "scores.csv",
        "deadlines.csv",
        "parity.json",
        *reference_files,
    ]
    save_json(
        out / "figure-lock.json",
        dict(
            cases=lock["cases"],
            files={name: _sha(out / name) for name in files},
        ),
    )
    common = list(diagnostic.PHYSICAL_KEYS)
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="new-waveforms-lighter",
                    method=lighter.METHOD,
                    scope="roof",
                    cases="sealed",
                    title="A lighter fifth center on the same two complete saved-IQ recordings",
                    caption=(
                        "The three methods use the same saved IQ, causal catalogue and "
                        "compact release. The four original v5 options use capture-era factors."
                    ),
                    seal="figure-lock.json",
                    provenance=files,
                    roof_references=paired.ROOF_REFERENCES,
                    series=[
                        dict(
                            key="one",
                            file=ROWS,
                            label="Lighter fifth center",
                            value=lighter.METHOD,
                            native_field="paired_capture_sha256",
                        ),
                        dict(
                            key="one_native_factors",
                            file=ROWS,
                            label="Released fifth center",
                            value=study.METHOD,
                            native_field="paired_capture_sha256",
                            match=common,
                        ),
                        dict(
                            key="stock",
                            file=ROWS,
                            label="Stock wide",
                            value=study.STOCK,
                            native_field="paired_capture_sha256",
                            match=common,
                        ),
                    ],
                )
            ],
        ),
    )
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output, default=study.WORK)
    parser.add_argument("--out", type=local_output, default=REPORT)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.out)
    else:
        score(args.out)
