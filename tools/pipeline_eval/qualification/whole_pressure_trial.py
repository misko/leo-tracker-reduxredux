"""Replay one whole-recording memory failure with the pinned receiver repair."""

import argparse
import gzip
import json
from pathlib import Path
from time import time

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, distance_km
from . import whole_band_results as band
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_band_trial import REPORT as PARENT

CASE = "DS29-0247"
METHOD = "constrained_lifetime_narrow_full_iq"
REPORT = PARENT.with_name("whole-pressure")
ORIGINAL_RUN = Path("/srv/bulk/leo-dev/whole-band-BCw8KqMY")
RECEIVER = Path("/srv/bulk/leo-dev/cp-v2/candidate")
RELEASE_RECEIPT_SHA = "ac225b9bb39b5d1fcbb1af7d899d7e7190770949b01a0d9a62c4491cdc0a9876"
PARENT_PREDICTION_SHA = "1d7f9fd044263e4ce231cf299b41cea897105ef753c1688fcb3333ae90ba9cca"
PARENT_FIGURE_SHA = "1779047c619bd8d823b3eecf838025076b9f22996cf563cee196dc7cc9633e14"
CHANGED = {"leo/analysis/localization_v3/feasible.py", "native/manifest.json"}
SOURCES = {
    "leo/analysis/localization_v4/native_bound.c",
    "tools/pipeline_eval/variants/orbit_projector.c",
}
SOURCE = "replay-source-lock.json"
V5_OPTIONS = ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks")
BRANCHES = {"repair": METHOD, **band.METHOD}


def parent_lock():
    # The prediction seal is truth-free. Authenticate the parent scores only after our own seal.
    lock = whole_iq.read(whole_iq.checked(PARENT / "prediction-lock.json", PARENT_PREDICTION_SHA))
    return whole_iq.read(
        whole_iq.checked(PARENT / "source-lock.json", lock["files"]["source-lock.json"])
    )


def release_files(stock, candidate, declared):
    changed = {
        path for path in stock.keys() | candidate.keys() if stock.get(path) != candidate.get(path)
    }
    if stock.keys() != candidate.keys() or changed != CHANGED or candidate != declared:
        raise ValueError(
            "receiver release differs beyond the frozen repair and manifest relocation"
        )
    return candidate


def verify_sources(receiver, original, declared):
    if declared.keys() != SOURCES:
        raise ValueError("the frozen transport must bind both native compiler sources")
    for name, digest in declared.items():
        whole_iq.checked(original / name, digest)
        whole_iq.checked(receiver / name, digest)
    return declared


def launch(work, report, receiver, release_receipt):
    lock = parent_lock()
    for path, digest in lock["sources"].items():
        whole_iq.checked(ROOT / path, digest)
    receipt = whole_iq.read(whole_iq.checked(release_receipt, RELEASE_RECEIPT_SHA))
    original = lock["cases"][CASE]
    if (original["cpus"], lock["memory_max"], lock["swap_max"], lock["limit_s"]) != (
        [0, 1],
        whole_iq.MEMORY,
        0,
        360,
    ):
        raise ValueError("the original service limits changed")
    stock_path = ORIGINAL_RUN / "receiver"
    stock = whole_iq.receiver_identity(stock_path)
    if stock != lock["receiver_files"]:
        raise ValueError("the original installed release changed")
    lock.update(
        cases={CASE: original},
        receiver=str(receiver),
        receiver_files=release_files(stock, whole_iq.receiver_identity(receiver), receipt["files"]),
        compiler_sources=verify_sources(receiver, stock_path, receipt["compiler_sources"]),
        release_receipt_sha256=RELEASE_RECEIPT_SHA,
        parent_prediction_sha256=PARENT_PREDICTION_SHA,
        protocol_sha256=_sha(report / "PROTOCOL.md"),
    )
    out = work / CASE / "narrow"
    source_path = report / SOURCE
    if out.exists() or source_path.exists():
        raise FileExistsError("the full-pressure protocol permits one candidate attempt")
    save_json(source_path, lock)
    save_json(work / "launch-lock.json", {"source_sha256": _sha(source_path)})
    detector = lock["detectors"]["narrow"]
    try:
        whole_iq.evaluate(
            CASE,
            Path(detector["path"]),
            detector["sha256"],
            receiver,
            out,
            original["cpus"],
            lock["limit_s"],
        )
    except (OSError, RuntimeError, ValueError) as error:
        save_json(out.with_name("narrow-failure.json"), dict(error=str(error), time_unix_s=time()))
        print(CASE, "failed", error, flush=True)
    else:
        print(CASE, "complete", flush=True)


def check_paired_raw(candidate, original, wide, new_row, old_row):
    if "raw_authority" not in candidate:
        return False
    band.pair_geometry(candidate, original)
    band.pair_geometry(candidate, wide)
    candidate_counts, original_counts = (
        {key: value for key, value in raw["counts"].items() if key != "detector_cpu_s"}
        for raw in (candidate, original)
    )
    if (
        candidate["dual_calls"] != 6767
        or candidate_counts != original_counts
        or candidate["input_manifest_sha256"] != original["input_manifest_sha256"]
        or candidate["detector_sha256"] != original["detector_sha256"]
        or new_row["native_sha256"] != old_row["native_sha256"]
    ):
        raise ValueError("the narrow replays do not match on complete waveform and native support")
    return True


def rows_from(path):
    with gzip.open(path, "rt") as stream:
        return list(map(json.loads, stream))


def seal(work, report):
    source_path = whole_iq.checked(
        report / SOURCE, whole_iq.read(work / "launch-lock.json")["source_sha256"]
    )
    source = whole_iq.read(source_path)
    whole_iq.checked(report / "PROTOCOL.md", source["protocol_sha256"])
    plan_path = work / CASE / "narrow/plan.json"
    if plan_path.is_file() and whole_iq.read(plan_path)["limit_s"] != source["limit_s"]:
        raise ValueError("attempt deadline differs from the frozen limit")
    parent = whole_iq.read(whole_iq.checked(PARENT / "prediction-lock.json", PARENT_PREDICTION_SHA))
    parent_paths = {
        f: whole_iq.checked(PARENT / f, parent["files"][f])
        for f in ("positions.jsonl.gz", "resources.json")
    }
    recorded = {
        row["method"]: row
        for row in rows_from(parent_paths["positions.jsonl.gz"])
        if row["id"] == CASE
    }
    controls = whole_iq.read(parent_paths["resources.json"])[CASE]
    candidate, measurement, native = band.attempt(work, CASE, "narrow", source, method=METHOD)
    identical = check_paired_raw(
        measurement,
        controls["narrow"],
        controls["wide"],
        candidate,
        recorded[band.METHOD["narrow"]],
    )
    resources = {**controls, "repair": measurement, "complete_narrow_archive_exact": identical}
    files = ["positions.jsonl.gz", "resources.json", SOURCE, "PROTOCOL.md"]
    if digest := measurement["service"].get("log_sha256"):
        log = whole_iq.checked(work / CASE / "narrow/service.log", digest)
        write(report / "repair-service.log", log.read_bytes())
        files.append("repair-service.log")
    first = work.parent / CASE / "narrow"
    if (first / "service.json").is_file():
        stopped = whole_iq.read(first / "service.json")
        whole_iq.checked(first / "service.log", stopped["log_sha256"])
        if (first / "end.json").exists() or (first / "raw.json").exists():
            raise ValueError("the transport attempt was expected to stop before raw completion")
        save_json(
            report / "transport-stop.json",
            dict(
                reason="Candidate transport lacked the manifest-bound C source",
                service=stopped,
                start=whole_iq.read(first / "start.json"),
                plan=whole_iq.read(first / "plan.json"),
            ),
        )
        files += ["transport-stop.json", "source-lock.json"]
    if native is not None:
        filename = "native.json.gz"
        write(report / filename, gzip.compress(native.read_bytes(), compresslevel=6, mtime=0))
        files.append(filename)
    pack(report / "positions.jsonl.gz", [candidate, *recorded.values()])
    save_json(report / "resources.json", resources)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=[CASE],
            files={name: _sha(report / name) for name in files},
            parent_prediction_sha256=PARENT_PREDICTION_SHA,
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score_rows(records, resources, reference):
    actual = {record["method"]: record["result"] for record in records}
    archived = reference["reference"]
    scores = []
    for arm in ARMS:
        baseline = archived["baseline"][arm]["error_km"]
        fits = {name: archived[name][arm] for name in V5_OPTIONS}
        for branch, method in BRANCHES.items():
            result = actual[method]
            endpoint = result["arms"][arm]
            fits[branch] = dict(
                endpoint,
                status=result["status"],
                error_km=distance_km(reference["truth"], endpoint["latlon"]),
                frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
            )
        for name, endpoint in fits.items():
            measurement = resources.get(name, {})
            error = endpoint["error_km"]
            latitude, longitude = endpoint["latlon"] or (None, None)
            scores.append(
                dict(
                    id=CASE,
                    branch=name,
                    arm=arm,
                    status=endpoint["status"],
                    published=latitude is not None,
                    latitude=latitude,
                    longitude=longitude,
                    error_km=error,
                    original_v5_km=baseline,
                    within_5pct=error is not None and error <= 1.05 * baseline,
                    within_10pct=error is not None and error <= 1.10 * baseline,
                    conditional_rms_hz=endpoint.get("rf_rms_hz"),
                    conditional_frequency_score=endpoint.get("frequency_score"),
                    historical_wall_s=endpoint.get("wall_s"),
                    wall_s=measurement.get("wall_s"),
                    cpu_s=measurement.get("cpu_s"),
                    raw_s=measurement.get("raw_s"),
                    position_s=measurement.get("position_s"),
                    charged_peak_bytes=measurement.get("max_bytes"),
                    wall_to_failure_s=measurement.get("wall_to_failure_s"),
                    cpu_to_failure_s=measurement.get("cpu_to_failure_s"),
                    charged_peak_to_failure_bytes=measurement.get("charged_peak_to_failure_bytes"),
                )
            )
    return scores


def score(report):
    prediction = whole_iq.read(report / "prediction-lock.json")
    for name, digest in prediction["files"].items():
        whole_iq.checked(report / name, digest)
    parent = whole_iq.read(whole_iq.checked(PARENT / "six-figure-lock.json", PARENT_FIGURE_SHA))
    for name, digest in parent["files"].items():
        whole_iq.checked(PARENT / name, digest)
    _, (reference,) = held_references(None, [CASE])
    records = rows_from(report / "positions.jsonl.gz")
    scores = score_rows(records, whole_iq.read(report / "resources.json"), reference)
    csv_file(report / "scores.csv", scores)
    provenance = ["prediction-lock.json", "resources.json", "scores.csv"]
    save_json(
        report / "figure-lock.json",
        dict(
            cases=[CASE],
            files={name: _sha(report / name) for name in ["positions.jsonl.gz", *provenance]},
            parent_figure_sha256=PARENT_FIGURE_SHA,
        ),
    )
    matches = ["tile", "catalog_sha256", "original_request_sha256", "mode"]
    series = [
        dict(
            key=key,
            label=label,
            file="positions.jsonl.gz",
            value=BRANCHES[branch],
            native_authority="ordinary",
            native_field="paired_ordinary_sha256",
            **({"match": matches} if branch != "repair" else {}),
        )
        for key, label, branch in (
            ("one", "Narrow GLRT · release fit buffers", "repair"),
            ("stock", "Original narrow GLRT", "narrow"),
            ("all_visits", "Wide GLRT · ±800 kHz", "wide"),
        )
    ]
    chart = dict(
        id="whole-pressure",
        method=METHOD,
        scope="roof",
        cases=[CASE],
        title="Full recorded-IQ replay after releasing constrained-fit buffers",
        caption=(
            "One reserve recording through the public raw-IQ receiver under 512 MiB and zero swap. "
            "The two narrow runs use the same detector. Original v5 uses capture-era factors."
        ),
        seal="figure-lock.json",
        provenance=provenance,
        series=series,
    )
    save_json(report / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "seal", "score"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=REPORT)
    args = parser.parse_args()
    if args.action == "run":
        launch(args.work, args.out, RECEIVER, RECEIVER.with_name("candidate-lock.json"))
    elif args.action == "seal":
        seal(args.work, args.out)
    else:
        score(args.out)
