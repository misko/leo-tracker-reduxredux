"""Authenticate the original cavity residuals and run the sealed RF gate."""

import argparse
import gzip
import io
import json
from pathlib import Path
from time import perf_counter, process_time
from zipfile import ZipFile

from ..__main__ import encoded, local_output, save_json, write
from ..variants.late_routing import evaluate
from ..variants.v5_lean import SOURCE_SHA256
from . import late_preflight_trial as prior
from . import late_routing_sources as measured
from . import late_routing_trial as trial
from .full_receiver_comparison import seal, sha
from .pruned_finish_audit import ARCHIVE, DS29, _field, _rows
from .v5_postfit import _map, sha256
from .v5_prefix_audit import value

PREVIOUS = prior.REPORT
BLIND = "archive-predecision.json.gz"
LOCK = "archive-predecision-lock.json"


def load(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def extract(previous):
    ident = previous["id"]
    folder = (DS29 if ident.startswith("DS29") else ARCHIVE) / f"{ident}-r0"
    execution = (folder / "baseline-execution.json").read_bytes()
    record = json.loads(execution)
    worker = record["worker"]
    request = previous["request_sha256"]
    payload = (folder / "baseline/experimental-evidence.zip").read_bytes()
    if (
        sha256(execution).removeprefix("sha256:")
        != previous["execution_sha256"].removeprefix("sha256:")
        or sha256(payload) != previous["archive_sha256"]
        or worker["artifact"]["sha256"] != previous["archive_sha256"]
        or worker["source_sha256"] != SOURCE_SHA256
        or record["role"] != "baseline"
        or record["status"] != "complete"
        or record["request_sha256"] != request
        or worker["request_sha256"] != request
    ):
        raise ValueError(f"{ident}: original request, evidence or execution changed")
    with ZipFile(io.BytesIO(payload)) as archive:
        raw = archive.read("values.json")
        if _field(raw, "request_sha256") != request:
            raise ValueError(f"{ident}: payload request mismatch")
        start = raw.index(
            b'["additional_recovery",["map",[["status","additional_recovery_prepared"]'
        )
        end = raw.index(b'["residual_screen",["map",[["status","additional_candidates_screened"]')
        ptr = raw.index(b'["preflight",', start, end)
        targets = _rows(_map(prior.local_field(raw, ptr))["targets"])
        samples = [
            dict(
                times_s=value(row["times_s"], archive),
                corrected_hz={
                    a: value(coefficients, archive)
                    for a, coefficients in _map(row["corrected_hz"]).items()
                },
            )
            for row in targets
        ]
    started, cpu = perf_counter(), process_time()
    try:
        router = evaluate(samples)
    except ValueError as error:
        router = dict(run=True, targets=[], reason=f"invalid diagnostic; retain stock: {error}")
    timing = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - started)
    keep = {k: previous[k] for k in ("id", "archive_sha256", "execution_sha256", "request_sha256")}
    return dict(
        **keep,
        native_sha256=previous["native_sha256"],
        catalog_sha256=previous["catalog_sha256"],
        tile=previous["tile"],
        samples=samples,
        route=dict(router, **timing),
        original_stage_wall_s={v["stage"]: v["seconds"] for v in worker["stage_timings"]},
    )


def collect(output):
    folder = trial.REPORT
    run, sources = measured.verify_run(folder, trial.lock())
    extract_original = measured.measured_extract(sources)
    seal(PREVIOUS, "roof-lock.json", ("predecision.json.gz", "outcomes.json.gz"))
    previous = load(PREVIOUS / "predecision.json.gz")
    if sorted(row["id"] for row in previous) != run["cases"]:
        raise ValueError("archived evidence differs from the sealed roster")
    output = local_output(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for row in previous:
        rows.append(extract_original(row))
        print(row["id"], rows[-1]["route"]["run"], flush=True)
    write(output / BLIND, gzip.compress(encoded(rows), mtime=0))
    save_json(
        output / LOCK,
        dict(
            cases=run["cases"],
            files={BLIND: sha(output / BLIND)},
            run_lock_sha256=sha(folder / "run-lock.json"),
            original_evidence_lock_sha256=sha(PREVIOUS / "roof-lock.json"),
            extractor_sha256=json.loads((folder / LOCK).read_bytes())["extractor_sha256"],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    collect(parser.parse_args().output)
