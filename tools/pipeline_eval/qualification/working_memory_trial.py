"""Compare the live memory of ordinary compact secant and a one-association discovery path."""

import argparse
import gzip
import json
import os
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import orbit_projector, v5_discovery_memory, v5_lean
from . import secant_end_to_end, secant_fit_trial
from .full_v5_check import BULK, _load_case, _sha
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/working-memory"
PRIOR = REPORT.parent / "end-to-end"
RAW = Path("/tmp/leo-secant-end-to-end-20261119")
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/working-memory")
WORKER = Path(__file__).with_name("working_memory_worker.py")
METHODS = {"stock": "v5_secant_fit", "candidate": v5_discovery_memory.METHOD}
CAP = 180
PLAN = {
    "ordinary-DS26-0036": (10, ("stock", "candidate")),
    "ordinary-DS29-0082": (11, ("candidate", "stock")),
    "capture-era-DS29-0082": (11, ("stock", "candidate")),
}


def source_lock():
    original = secant_fit_trial.source_seal()
    if json.loads(secant_end_to_end.SOURCE.read_bytes()) != json.loads(encoded(original)):
        raise ValueError("compact secant differs from its original qualification lock")
    paths = [
        Path(v5_discovery_memory.__file__),
        WORKER,
        Path(__file__),
        secant_end_to_end.FIT_WORKER,
    ]
    frozen = v5_lean.SOURCE / "leo/analysis/localization_v3"
    paths.extend(frozen / (name + ".py") for name in ("orbits", "scan", "discovery"))
    return dict(
        sources=dict(original["compact_source_sha256"], **{p.name: _sha(p) for p in paths}),
        frozen_source=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        prior_prediction_lock_sha256=_sha(PRIOR / "prediction-lock.json"),
        plan={key: [cpu, list(order)] for key, (cpu, order) in PLAN.items()},
        cap_s=CAP,
    )


def canonical_request(path):
    data = json.loads(path.read_bytes())
    data["job"].pop("output_root")
    if data["job"]["evaluation_reference"] is not None:
        raise ValueError("truth found in receiver request")
    return sha256(encoded(data)).hexdigest()


def case_binding(key, raw):
    detector, ident = key.split("-DS", maxsplit=1)
    ident = "DS" + ident
    case = _load_case(ident)
    if detector == "ordinary":
        prior_lock = json.loads((PRIOR / "prediction-lock.json").read_bytes())
        receipt = PRIOR / "stage-receipts.json"
        if _sha(receipt) != prior_lock["files"][receipt.name]:
            raise ValueError("published whole-IQ replay receipt changed")
        row = json.loads(receipt.read_bytes())[ident]
        digest = row["raw_replay"]["native_sha256"]
        if (
            not row["same_factors_as_prior_whole_iq"]
            or digest != row["prior_complete_iq"]["native_sha256"]
        ):
            raise ValueError(
                "ordinary factor file does not bind two independent complete IQ replays"
            )
        native = raw / ident / "native.json"
        request = raw / ident / "secant" / "request.json"
        expected_request = row["paired_request_sha256"]["secant"]
        if canonical_request(request) != row["common_science_request_sha256"]:
            raise ValueError("ordinary file's bound requests differ from the prior run")
    else:
        native = BULK / case["native"]["path"]
        digest = case["native"]["sha256"]
        request = BULK / case["request"]["path"]
        expected_request = case["request"]["sha256"]
    if _sha(native) != digest or _sha(request) != expected_request:
        raise ValueError("source artifact differs from its frozen digest")
    return (
        dict(
            id=case["id"],
            panel=case["panel"],
            regions=case["regions"],
            session_id=case["session_id"],
            native_path=str(native),
            native_sha256="sha256:" + digest,
            request_path=str(request),
        ),
        dict(detector=detector, native_sha256=digest, catalog_sha256=case["catalog"]["sha256"]),
    )


def execute(key, raw, runs, report):
    seal = json.loads((report / "source-lock.json").read_bytes())
    if seal != source_lock():
        raise ValueError("working memory source differs from pre-input lock")
    cpu, order = PLAN[key]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"pin worker to CPU {cpu}")
    case, provenance = case_binding(key, raw)
    request_digest = canonical_request(Path(case["request_path"]))
    v5_lean.TIMEOUT_S = CAP
    for mode in order:
        out = runs / key / mode
        path = out / "prediction.json"
        if path.is_file():
            continue
        out.mkdir(parents=True)
        library = out / "orbit_projector.so"
        orbit_projector.compile_kernel(library)
        before = getrusage(RUSAGE_CHILDREN)
        wall = perf_counter()
        value = v5_lean.run_bound_worker(case, out, WORKER, worker_args=(str(library), mode))
        elapsed, after = perf_counter() - wall, getrusage(RUSAGE_CHILDREN)
        completed_request = out / "request.json"
        if canonical_request(completed_request) != request_digest:
            raise ValueError("compared workers did not use the same scientific request")
        validate_result(value)
        if seal != source_lock():
            raise ValueError("working memory source changed during replay")
        save_json(
            path,
            dict(
                id=case["id"],
                case_key=key,
                mode="matched-tile",
                method=METHODS[mode],
                tile=case["regions"][0],
                input_sha256=request_digest,
                request_sha256=_sha(completed_request),
                cpu=cpu,
                worker_wall_s=elapsed,
                worker_cpu_s=(after.ru_utime - before.ru_utime)
                + (after.ru_stime - before.ru_stime),
                result=value,
                **provenance,
            ),
        )
        print(key, mode, value["status"], round(elapsed, 2), flush=True)


def comparison(rows):
    stock, candidate = rows
    for key in (
        "id",
        "case_key",
        "detector",
        "cpu",
        "input_sha256",
        "native_sha256",
        "catalog_sha256",
        "tile",
    ):
        if stock[key] != candidate[key]:
            raise ValueError(f"paired input differs in {key}")
    results = [r["result"] for r in rows]
    if any(r["status"] != "ok" for r in results):
        return dict(status=[r["status"] for r in results])
    memory = [r["metrics"]["working_memory"] for r in results]
    keys = ("source_indices_sha256", "selected_source_indices", "selected_norad", "arrays_sha256")
    bank_equal = all(memory[0]["regional_bank"][k] == memory[1]["regional_bank"][k] for k in keys)
    scalar = ("track_sha256", "observation_sha256")
    tracks_equal = all(memory[0][k] == memory[1][k] for k in scalar)
    sequence = ("first_rows_sha256", "projected_visibility_sha256", "output_sha256")
    traces = [[tuple(e[k] for k in sequence) for e in m["explorations"]] for m in memory]
    return dict(
        bank_exact=bank_equal,
        tracks_exact=tracks_equal,
        discovery_exact=traces[0] == traces[1],
        endpoints_rf_exact=results[0]["arms"] == results[1]["arms"],
        spherical_endpoint_delta_m={
            arm: 1000 * distance_km(*(r["arms"][arm]["latlon"] for r in results)) for arm in ARMS
        },
        conditional_rms_delta_hz={
            arm: results[1]["arms"][arm]["rf_rms_hz"] - results[0]["arms"][arm]["rf_rms_hz"]
            for arm in ARMS
        },
    )


def publish(runs, report):
    pairs = {
        key: [json.loads((runs / key / mode / "prediction.json").read_bytes()) for mode in METHODS]
        for key in PLAN
    }
    exact = {key: comparison(rows) for key, rows in pairs.items()}
    files = {}
    for mode, method in METHODS.items():
        path = report / f"{mode}-positions.jsonl.gz"
        rows = [r for pair in pairs.values() for r in pair if r["method"] == method]
        write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
        files[path.name] = _sha(path)
    save_json(report / "comparison.json", exact)
    files["comparison.json"] = _sha(report / "comparison.json")
    save_json(
        report / "prediction-lock.json",
        dict(cases=list(PLAN), files=files, source_lock_sha256=_sha(report / "source-lock.json")),
    )
    return exact


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    if any(_sha(report / name) != digest for name, digest in lock["files"].items()):
        raise ValueError("sealed predictions changed before geographic scoring")
    truth = {}
    for panel, case in (("ds26-common127", "DS26-0036"), ("roof16", "DS29-0082")):
        truth[case] = references(panel, [case])[1][0]["truth"]
    scores = []
    for mode in METHODS:
        rows = list(
            map(
                json.loads,
                gzip.decompress((report / f"{mode}-positions.jsonl.gz").read_bytes()).splitlines(),
            )
        )
        for row in rows:
            for arm in ARMS:
                a = row["result"]["arms"][arm]
                scores.append(
                    dict(
                        id=row["id"],
                        detector=row["detector"],
                        method=row["method"],
                        arm=arm,
                        status=row["result"]["status"],
                        error_km=distance_km(truth[row["id"]], a["latlon"]),
                        conditional_rms_hz=a.get("rf_rms_hz"),
                    )
                )
    csv_file(report / "scores.csv", scores)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "publish", "score"))
    p.add_argument("--case", choices=PLAN)
    for name, default in (("report", REPORT), ("raw", RAW), ("runs", RUNS)):
        p.add_argument("--" + name, type=local_output, default=default)
    a = p.parse_args()
    if a.action == "seal":
        path = a.report / "source-lock.json"
        source = source_lock()
        if path.exists() and json.loads(path.read_bytes()) != source:
            raise ValueError("refuse to replace the original pre-input source lock")
        if not path.exists():
            save_json(path, source)
    elif a.action == "replay":
        if not a.case:
            p.error("--case is required")
        execute(a.case, a.raw, a.runs, a.report)
    elif a.action == "publish":
        print(json.dumps(publish(a.runs, a.report), indent=2))
    else:
        score(a.report)


if __name__ == "__main__":
    main()
