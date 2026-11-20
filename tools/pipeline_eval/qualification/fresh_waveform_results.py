"""Seal and score fresh whole-waveform replays against the frozen roof references."""

import argparse
import gzip
import json
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, distance_km
from . import fresh_waveform as trial
from . import whole_band_results as band
from .fractional_runtime_whole import IDENTITY
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

V5_OPTIONS = ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks")


def validate_native(document, case, raw, detector):
    source, provenance = document["source"], document["provenance"]
    manifest = case["clock_authority"]
    detector = "sha256:" + detector
    probes, excluded = source["probes"], provenance["excluded_windows"]
    digest = whole_iq.recording.digest
    analysis = digest([IDENTITY, detector, manifest, probes, excluded])
    windows, skipped = provenance["processed_windows"], provenance["invalid_capture"]
    if (
        document["schema_version"] != 2
        or source["session_id"] != "fast-" + manifest[7:39]
        or source["input_manifest_sha256"] != manifest
        or provenance["detector_sha256"] != detector
        or source["analysis_manifest_sha256"] != analysis
        or provenance["run_id"] != "replay-" + analysis[7:39]
        or source["raw_recording_authority_digest"] != raw["raw_authority"]
        or digest(
            [document["clock_anchor"], document["delivery_clocks"], document["last_sample_counter"]]
        )
        != raw["clock_sha256"]
        or digest(excluded) != raw["excluded_sha256"]
        or digest([{k: v for k, v in probe.items() if k != "candidates"} for probe in probes])
        != raw["probes_sha256"]
        or windows + skipped != case["recording"]["window_count"]
        or windows != raw["dual_calls"]
        or len(probes) != 2 * windows
        or len(excluded) != skipped
    ):
        raise ValueError("full replay native archive differs from the frozen waveform or detector")


def seal(work, report, recovery=None):
    source_path = whole_iq.checked(
        report / "source-lock.json", whole_iq.read(work / "launch-lock.json")["source_sha256"]
    )
    study = whole_iq.read(source_path)
    for path, digest in study["sources"].items():
        whole_iq.checked(ROOT / path, digest)
    rows, measurements = [], {}
    files = ["source-lock.json", "positions.jsonl.gz", "resources.json", "PROTOCOL.md"]
    recovered = {}
    if recovery is not None:
        incident = whole_iq.read(recovery)
        ident = incident["case"]
        old_attempt = work / ident / "wide"
        if (
            ident not in study["cases"]
            or not incident["supervisor_exited"]
            or incident["initial_service_created"]
            or Path(incident["initial_work"]) != work
            or (old_attempt.exists() and any(old_attempt.iterdir()))
            or incident["source_sha256"] != _sha(source_path)
        ):
            raise ValueError("expected recovery of a frozen case before any scientific service")
        recovered[ident] = local_output(incident["work"])
        write(report / "storage-incident.json", recovery.read_bytes())
        files.append("storage-incident.json")
    for ident, case in study["cases"].items():
        attempt = recovered.get(ident, work)
        run = attempt / ident / "wide"
        if (run / "plan.json").exists():
            plan = whole_iq.read(run / "plan.json")
            if (
                plan["receiver"] != study["receiver"]
                or plan["native_sources"] != study["native_sources"]
                or plan["limit_s"] != study["limit_s"]
                or plan["detector"] != study["detectors"]["wide"]["path"]
            ):
                raise ValueError("service plan differs from the prospective receiver")
        row, resource, native = band.attempt(attempt, ident, "wide", study, method=trial.METHOD)
        row.pop("paired_ordinary_sha256")
        row.update(
            capture_era_native_sha256=case["capture_era_native_sha256"],
            input_manifest_sha256=case["clock_authority"],
        )
        if digest := resource["service"].get("log_sha256"):
            name = f"{ident}-service.log"
            path = whole_iq.checked(run / "service.log", digest)
            write(report / name, path.read_bytes())
            files.append(name)
        if native is not None:
            blob = native.read_bytes()
            validate_native(json.loads(blob), case, resource, study["detectors"]["wide"]["sha256"])
            name = f"native/{ident}.json.gz"
            write(report / name, gzip.compress(blob, compresslevel=6, mtime=0))
            files.append(name)
        measurements[ident] = resource
        rows.append(row)
    pack(report / "positions.jsonl.gz", rows)
    save_json(report / "resources.json", measurements)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(study["cases"]),
            files={name: _sha(report / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score_rows(records, references, measurements):
    if references.keys() != measurements.keys() or references.keys() != records.keys():
        raise ValueError("fresh-waveform scoreboard must retain the complete case roster")
    rows = []
    for ident, row in records.items():
        reference = references[ident]
        result, resource = row["result"], measurements[ident]
        for arm in ARMS:
            no_repair = reference["reference"]["baseline"][arm]["error_km"]
            fits = {name: reference["reference"][name][arm] for name in V5_OPTIONS}
            endpoint = result["arms"][arm]
            fits[trial.METHOD] = dict(
                endpoint,
                error_km=distance_km(reference["truth"], endpoint["latlon"]),
                status=result["status"],
                frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
            )
            for method, fit in fits.items():
                measurement = resource if method == trial.METHOD else {}
                distance = fit["error_km"]
                latitude, longitude = fit["latlon"] or (None, None)
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        status=fit["status"],
                        published=latitude is not None,
                        latitude=latitude,
                        longitude=longitude,
                        error_km=distance,
                        no_repair_km=no_repair,
                        within_5pct=distance is not None
                        and no_repair is not None
                        and distance <= no_repair * 1.05,
                        within_10pct=distance is not None
                        and no_repair is not None
                        and distance <= no_repair * 1.10,
                        conditional_rms_hz=fit.get("rf_rms_hz"),
                        conditional_frequency_score=fit.get("frequency_score"),
                        original_worker_wall_s=fit.get("wall_s"),
                        full_wall_s=measurement.get("wall_s"),
                        full_cpu_s=measurement.get("cpu_s"),
                        raw_s=measurement.get("raw_s"),
                        position_s=measurement.get("position_s"),
                        max_bytes=measurement.get("max_bytes"),
                        wall_to_failure_s=measurement.get("wall_to_failure_s"),
                        cpu_to_failure_s=measurement.get("cpu_to_failure_s"),
                        charged_peak_to_failure_bytes=measurement.get(
                            "charged_peak_to_failure_bytes"
                        ),
                    )
                )
    return rows


def score(report):
    prediction = whole_iq.read(report / "prediction-lock.json")
    for name, digest in prediction["files"].items():
        whole_iq.checked(report / name, digest)
    cases = prediction["cases"]
    _, references = held_references(None, cases)
    with gzip.open(report / "positions.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    if [row["id"] for row in rows] != cases:
        raise ValueError("predictions differ from the prospective case roster")
    scores = score_rows(
        {row["id"]: row for row in rows},
        {ref["id"]: ref for ref in references},
        whole_iq.read(report / "resources.json"),
    )
    csv_file(report / "scores.csv", scores)
    provenance = ["prediction-lock.json", "source-lock.json", "resources.json", "scores.csv"]
    save_json(
        report / "figure-lock.json",
        dict(
            cases=cases,
            files={name: _sha(report / name) for name in ["positions.jsonl.gz", *provenance]},
        ),
    )
    chart = dict(
        id="fresh-waveform-wide",
        method=trial.METHOD,
        scope="roof",
        cases=cases,
        title="Wide four-center GLRT on two new full-IQ replays",
        caption=(
            "One DS26 and one DS29 waveform selected by capture-manifest hash. Both receivers "
            "use every eligible visit. Original v5 uses capture-era factors. One physical roof."
        ),
        seal="figure-lock.json",
        provenance=provenance,
        series=[
            dict(
                key="one",
                label="Wide GLRT · four centers",
                file="positions.jsonl.gz",
                value=trial.METHOD,
                native_field="capture_era_native_sha256",
            )
        ],
    )
    save_json(report / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    parser.add_argument("--recovery", type=local_output)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.out, args.recovery)
    else:
        score(args.out)
