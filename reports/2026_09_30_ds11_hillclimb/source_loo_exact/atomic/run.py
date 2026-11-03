"""Individually bounded, persisted exact source-deletion fits for index zero."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def job_key(job):
    return f"{job['index']:02d}_{job['family']}_{job['norad']}"


def load_plan():
    plan = json.loads((HERE / "plan.json").read_text())
    if plan["schema"] != "ds11-source-loo-atomic-plan/v1":
        raise ValueError("unexpected atomic plan schema")
    for path, expected in plan["sources"].items():
        if digest(path) != expected:
            raise ValueError(f"changed plan dependency: {path}")
    keys = [job_key(job) for job in plan["jobs"]]
    if len(keys) != len(set(keys)) or any(job["index"] != 0 for job in plan["jobs"]):
        raise ValueError("duplicate job or unsupported scan")
    return plan


def one(key):
    started = time.monotonic()
    plan = load_plan()
    job = next(row for row in plan["jobs"] if job_key(row) == key)
    if job["cache"] is not None:
        raise ValueError("cached fits must not be repeated")
    pilot = module("ds11_atomic_pilot", PARENT / "run.py")
    pilot.fast.baseline.profile = pilot.fast.profile
    diagnose = module("ds11_atomic_diagnose", pilot.HILL / "source_loo" / "diagnose.py")
    exact = module("ds11_atomic_exact", pilot.HILL / "source_loo" / "exact_audit.py")
    _, baseline_plan, entry, documents, _, norad_map = diagnose.validate_inputs(job["index"])
    source = module("ds11_atomic_source", pilot.HILL / "source_balance" / "model.py")
    robust = module("ds11_atomic_robust", pilot.HILL / "robust" / "model.py")
    iid_family = diagnose.FAMILIES["iid_t4_scale100"]
    _, _, _, iid_x, _, _ = diagnose.load_endpoint("iid_t4_scale100", iid_family, 0, entry["session_id"])
    assignments = source.freeze_assignments(documents, baseline_plan["config"], iid_x, norad_map)
    groups = pilot.eligible_groups(assignments)
    if job["norad"] not in groups:
        raise ValueError("planned source is not eligible")
    weights = source.derive_weights(assignments, "source_receiver_equal")
    subset = pilot.retained_fold(assignments, weights, job["norad"])
    ids = [assignments[i]["track_id"] for i in subset["omitted_indices"]]
    if ids != job["source_track_ids"]:
        raise ValueError("planned source membership changed")
    family = diagnose.FAMILIES[job["family"]]
    endpoint_path, _, _, full_x, _, _ = diagnose.load_endpoint(job["family"], family, 0, entry["session_id"])
    if full_x.tolist() != job["full_endpoint_x"] or str(endpoint_path.resolve()) not in plan["sources"]:
        raise ValueError("planned endpoint changed or is not digest-bound")
    retained = diagnose.subset_document(documents[0], subset["retained_indices"])
    weighted = family["kind"] == "source"
    model = diagnose.build_evaluator(
        family["kind"], family["variant"], retained, baseline_plan["config"],
        {"source": source, "robust": robust},
        weights=subset["retained_weights"] if weighted else None,
        assignments=subset["retained_assignments"] if weighted else None,
    )
    sources = {**plan["sources"], str(HERE / "plan.json"): digest(HERE / "plan.json"),
               str(HERE / "run.py"): digest(HERE / "run.py"),
               str(HERE / "PLAN_PROTOCOL.md"): digest(HERE / "PLAN_PROTOCOL.md")}
    counts = {"training_observation_count": sum(int(documents[0]["tracks"][i]["mask"].sum()) for i in subset["omitted_indices"]),
              "held_observation_count": sum(int((~documents[0]["tracks"][i]["mask"]).sum()) for i in subset["omitted_indices"])}
    fold = dict(norad=job["norad"], track_ids=ids, track_indices=subset["omitted_indices"],
                retained_track_count=len(subset["retained_indices"]),
                weights_preserved_without_renormalization=weighted, **counts)
    try:
        result, qualification = pilot.fit_local(model, full_x, diagnose.BOUNDS, exact.qualify)
        held = exact.common_held_score(documents[0], subset["omitted_indices"], result.x, baseline_plan["config"])
        if held["held_observation_count"] != counts["held_observation_count"]:
            raise ValueError("held coverage changed")
        fold.update(x=np.asarray(result.x).tolist(), retained_score=float(-result.fun),
                    common_held_score=held["score"],
                    optimizer={**qualification, "nfev": int(result.nfev), "nit": int(result.nit)})
    except Exception as exc:
        fold.update(optimizer={"qualified": False}, failure=f"{type(exc).__name__}: {exc}")
    record = dict(schema="ds11-source-loo-atomic-fold/v1", job_key=key, index=0,
                  family=job["family"], norad=job["norad"], session_id=entry["session_id"],
                  reference_used=False, full_endpoint_x=full_x.tolist(), fold=fold,
                  elapsed_s=time.monotonic() - started, sources=sources)
    folder = HERE / "runs"
    folder.mkdir(exist_ok=True)
    with (folder / f"{key}.json").open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
    print(json.dumps({"job": key, "qualified": fold["optimizer"]["qualified"],
                      "elapsed_s": record["elapsed_s"]}), flush=True)


def launch(job):
    key = job_key(job)
    folder = HERE / "runs"
    folder.mkdir(exist_ok=True)
    receipt_path = folder / f"{key}.receipt.json"
    log_path = folder / f"{key}.log"
    if receipt_path.exists():
        return {"existing_terminal_attempt": True, **json.loads(receipt_path.read_text())}
    if log_path.exists() or (folder / f"{key}.json").exists():
        raise RuntimeError(f"unreceipted attempt requires inspection: {key}")
    hashes = {"run_sha256": digest(HERE / "run.py"), "plan_sha256": digest(HERE / "plan.json"),
              "protocol_sha256": digest(HERE / "PLAN_PROTOCOL.md")}
    command = ["sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "90s", "nice", "-n", "19",
               PYTHON, str(HERE / "run.py"), "one", key]
    started = time.monotonic()
    with log_path.open("x") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    receipt = dict(job_key=key, index=job["index"], family=job["family"], norad=job["norad"],
                   exit_code=completed.returncode, wall_s=time.monotonic() - started,
                   command=command, **hashes)
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    single = sub.add_parser("one")
    single.add_argument("key")
    batch = sub.add_parser("batch")
    batch.add_argument("--workers", type=int, default=3, choices=(1, 2, 3))
    args = parser.parse_args()
    if args.mode == "one":
        one(args.key)
    else:
        jobs = [job for job in load_plan()["jobs"] if job["cache"] is None]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(launch, job) for job in jobs]
            for future in as_completed(futures):
                print(json.dumps(future.result()), flush=True)


if __name__ == "__main__":
    main()
