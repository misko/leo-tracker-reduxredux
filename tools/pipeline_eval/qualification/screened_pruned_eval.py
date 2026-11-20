"""Qualify the integrated full compact worker with authenticated aligned and v5 controls."""

import argparse
import gzip
import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from ..variants import v5_lean
from ..variants import v5_screened_pruned_finish as integrated
from . import aligned_confirmation as aligned
from . import aligned_confirmation_results as aligned_results
from . import phase_confirmation as phase
from . import secant_full
from .full_v5_check import _sha
from .pruned_finish_eval import NORMALS
from .secant_end_to_end_worker import cpu_s, stamp

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/inference/screened-pruned"
WORK = Path("/tmp/leo-screened-pruned-confirmation-20261119")
ROSTER = {"DS26-0175": 0, "DS29-0357": 7}
CAP_S = 480
STUDY_S = 720
FILES = {integrated.METHOD: "positions.jsonl.gz", aligned.METHOD: "aligned-positions.jsonl.gz"}
ROLE_FILE = {role: f"original-{role}-positions.jsonl.gz" for role in ROLES}


def read(path):
    return json.loads(path.read_bytes())


def sources():
    variants = Path(integrated.__file__).parent
    names = (
        "v5_screened_pruned_finish.py",
        "v5_screen_winner.py",
        "v5_shared_search.py",
        "v5_pruned_finish.py",
        "v5_armijo_aligned_finish.py",
        "v5_armijo_finish.py",
        "v5_armijo_fit.py",
        "compact_finish.py",
        "v5_core.py",
        "v5_lean.py",
        "orbit_projector.py",
        "orbit_projector.c",
    )
    qualifiers = (Path(__file__), Path(__file__).with_name("armijo_finish_phase_retry.py"))
    return dict(
        variant_files={name: _sha(variants / name) for name in names},
        qualifiers={path.name: _sha(path) for path in qualifiers},
        frozen_source=v5_lean.SOURCE_SHA256,
        frozen_runner=v5_lean.RUNNER_SHA256,
        protocol_sha256=_sha(OUTPUT / "PROTOCOL.md"),
    )


def original_bindings(ident, case, original):
    archive = phase.ARCHIVE if ident.startswith("DS26-") else phase.DS29
    expected = read(Path(case["request_path"]))
    values = {}
    for role in ROLES:
        directory = archive / f"{ident}-r0"
        path = directory / f"{role}-execution.json"
        request_path = directory / role / "experimental-request.json"
        saved = read(path)
        observed = read(request_path)
        digest = "sha256:" + phase.corpus._sha(encoded(observed))
        if (
            saved["status"] != "complete"
            or saved["role"] != role
            or observed["role"] != role
            or saved["request_sha256"] != digest
            or original[role]["request_sha256"] != digest
            or _sha(path) != original[role]["execution_sha256"]
        ):
            raise ValueError(f"{ident}/{role} original receipt lacks its validated request")
        for key in ("native_input", "track_config"):
            if observed["job"][key]["sha256"] != expected["job"][key]["sha256"]:
                raise ValueError(f"{ident}/{role} original {key} is not matched")
        if observed["causal_snapshots"] != expected["causal_snapshots"]:
            raise ValueError(f"{ident}/{role} original causal request is not matched")
        values[role] = dict(original[role], file=str(path))
    return values


def prepare():
    inputs = phase.frozen_inputs()
    archived = aligned.SCRATCH
    prior_plan = read(archived / "plan.json")
    if tuple(ROSTER) != NORMALS or prior_plan != aligned.prepare(inputs, aligned.source_lock()):
        raise ValueError("control roster or aligned source no longer validates")
    archive = secant_full.REPORT / "original-v5-inputs.json"
    if _sha(archive) != read(secant_full.REPORT / "receipt.json")["files"][archive.name]:
        raise ValueError("four-role source receipts differ from their seal")
    roles = read(archive)
    bindings, aligned_controls, original = {}, {}, {}
    for ident in ROSTER:
        item = inputs[ident]
        case = phase._case(item)
        bindings[ident] = dict(
            secant_full._binding(item, case),
            **aligned._request_proof(case, Path(case["request_path"])),
        )
        proof = bindings[ident]
        control = aligned_results._candidate(archived, prior_plan, ident, "confirmation")
        if (
            control["result"]["status"] != "ok"
            or control["boundary_proof"]["scientific_request_sha256"]
            != proof["scientific_request_sha256"]
            or control["boundary_proof"]["resolved_request_sha256"]
            != proof["resolved_request_sha256"]
        ):
            raise ValueError("authentic aligned control has another scientific request")
        original[ident] = original_bindings(ident, case, roles[ident])
        control_path = archived / ident / "prediction.json"
        aligned_controls[ident] = dict(
            file=str(control_path),
            sha256=_sha(control_path),
            worker_request_sha256=control["boundary_proof"]["worker_request_sha256"],
        )
    return dict(
        cases=list(ROSTER),
        cpus=ROSTER,
        bindings=bindings,
        source=sources(),
        aligned_controls=aligned_controls,
        originals=original,
        worker_deadline_s=CAP_S,
        study_deadline_s=STUDY_S,
        aligned_plan_sha256=_sha(archived / "plan.json"),
    )


def measure(work, ident):
    plan = read(work / "plan.json")
    if os.sched_getaffinity(0) != {ROSTER[ident]} or sources() != plan["source"]:
        raise ValueError("measured core or source changed")
    binding = plan["bindings"][ident]
    case = phase._case(phase.frozen_inputs()[ident])
    if secant_full._binding(phase.frozen_inputs()[ident], case) != {
        key: binding[key]
        for key in (
            "id",
            "input_sha256",
            "native_sha256",
            "catalog_sha256",
            "frozen_request_sha256",
            "tile",
        )
    }:
        raise ValueError("candidate no longer has the sealed roof packet")
    path = work / ident / "position"
    v5_lean.TIMEOUT_S = CAP_S - 5
    wall, cpu = perf_counter(), cpu_s()
    result = integrated.run(case, path)
    resources = stamp(wall, cpu)
    proof = (
        aligned._request_proof(case, path / "request.json")
        if (path / "request.json").exists()
        else None
    )
    if result["status"] == "ok" and (
        not proof or proof["scientific_request_sha256"] != binding["scientific_request_sha256"]
    ):
        raise ValueError("completed integrated result has no aligned request proof")
    if result["status"] != "ok":
        if "exceeded its " in result.get("reason", ""):
            result["status"] = "timed_out"
        result["arms"] = {key: {"latlon": None} for key in ARMS}
    validate_result(result)
    save_json(
        work / ident / "prediction.json",
        dict(
            binding,
            method=integrated.METHOD,
            cpu=ROSTER[ident],
            result=result,
            boundary_proof=proof,
            resources=resources,
            worker_cpu_s=resources["cpu_s"],
            worker_wall_s=resources["wall_s"],
            plan_sha256=_sha(work / "plan.json"),
        ),
    )


def supervise(work, ident, deadline):
    folder = work / ident
    folder.mkdir(exist_ok=False)
    command = [
        "taskset",
        "-c",
        str(ROSTER[ident]),
        sys.executable,
        "-B",
        "-m",
        f"{__package__}.screened_pruned_eval",
        "measure",
        "--case",
        ident,
        "--work",
        str(work),
    ]
    started = perf_counter()
    with (folder / "supervisor.log").open("wb") as log:
        child = subprocess.Popen(
            command,
            env={**os.environ, **THREAD_ENV},
            cwd=ROOT,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            child.wait(timeout=min(CAP_S, deadline - started))
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            failure = "timed_out"
        else:
            failure = "failed"
    receipt = folder / "prediction.json"
    if not receipt.is_file():
        plan = read(work / "plan.json")
        result = dict(
            status=failure,
            reason=(folder / "supervisor.log").read_text()[-1800:] or failure,
            boundary=integrated.BOUNDARY,
            metrics={},
            arms={key: {"latlon": None} for key in ARMS},
        )
        save_json(
            receipt,
            dict(
                plan["bindings"][ident],
                method=integrated.METHOD,
                cpu=ROSTER[ident],
                result=result,
                worker_wall_s=perf_counter() - started,
                worker_cpu_s=None,
                plan_sha256=_sha(work / "plan.json"),
            ),
        )
    row = read(receipt)
    print(ident, row["result"]["status"], round(row["worker_wall_s"], 3), flush=True)
    return row


def run(work):
    work = local_output(work)
    work.mkdir(exist_ok=False)
    plan = prepare()
    save_json(work / "plan.json", plan)
    save_json(OUTPUT / "plan.json", plan)
    save_json(OUTPUT / "source-lock.json", plan["source"])
    write(OUTPUT / "sealed-supervisor.py.gz", gzip.compress(Path(__file__).read_bytes(), mtime=0))
    deadline = perf_counter() + STUDY_S
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda ident: supervise(work, ident, deadline), ROSTER))
    if plan["source"] != sources():
        raise ValueError("integrated source changed during the measured run")
    _pack(OUTPUT / FILES[integrated.METHOD], rows)
    files = ("plan.json", "source-lock.json", FILES[integrated.METHOD])
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(cases=list(ROSTER), files={name: _sha(OUTPUT / name) for name in files}),
    )


def _pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def score():
    lock = read(OUTPUT / "prediction-lock.json")
    for name, digest in lock["files"].items():
        if _sha(OUTPUT / name) != digest:
            raise ValueError("integrated predictions changed after sealing")
    plan = read(OUTPUT / "plan.json")
    frozen_supervisor = gzip.decompress((OUTPUT / "sealed-supervisor.py.gz").read_bytes())
    if (
        phase.corpus._sha(frozen_supervisor)
        != plan["source"]["qualifiers"]["screened_pruned_eval.py"]
    ):
        raise ValueError("the preserved measurement supervisor differs from the run lock")
    candidate = read_predictions(OUTPUT / FILES[integrated.METHOD])
    references = {r["id"]: r for r in phase.projector_roof.roster()}
    aligned_rows, originals, summary = [], {key: [] for key in ROLES}, []
    for ident in lock["cases"]:
        binding = plan["bindings"][ident]
        expected = plan["aligned_controls"][ident]
        path = Path(expected["file"])
        if _sha(path) != expected["sha256"]:
            raise ValueError("aligned receipt changed after the integrated request lock")
        control = read(path)
        control.update(
            scientific_request_sha256=binding["scientific_request_sha256"],
            control_receipt_sha256=expected["sha256"],
        )
        aligned_rows.append(control)
        originals_for_case = {}
        for role in ROLES:
            source = plan["originals"][ident][role]
            raw = Path(source["file"])
            if _sha(raw) != source["execution_sha256"]:
                raise ValueError("original archive execution differs from the study lock")
            result = read(raw)["worker"]
            arms = {
                arm: dict(
                    latlon=result["arms"][arm]["endpoint_latlon"],
                    published_rms_hz=result["arms"][arm].get("residual_rms_hz"),
                    published_objective=result["arms"][arm].get("frequency_score"),
                )
                for arm in ARMS
            }
            for arm in ARMS:
                if (
                    distance_km(
                        arms[arm]["latlon"], references[ident]["reference"][role][arm]["latlon"]
                    )
                    > 1e-6
                ):
                    raise ValueError(
                        "original endpoint differs from the published location archive"
                    )
            originals_for_case[role] = arms
            row = dict(
                binding,
                method=f"original-{role}",
                receipt=source,
                result=dict(
                    status="ok", boundary="Archived original v5 publication", arms=arms, metrics={}
                ),
            )
            originals[role].append(row)
        summary.append(
            compare(candidate[ident], control, originals_for_case, references[ident]["truth"])
        )
    _pack(OUTPUT / FILES[aligned.METHOD], aligned_rows)
    for role, rows in originals.items():
        _pack(OUTPUT / ROLE_FILE[role], rows)
    save_json(OUTPUT / "comparison.json", summary)
    files = (
        *lock["files"],
        FILES[aligned.METHOD],
        *ROLE_FILE.values(),
        "comparison.json",
        "prediction-lock.json",
        "sealed-supervisor.py.gz",
    )
    save_json(
        OUTPUT / "figure-lock.json",
        dict(cases=list(ROSTER), files={name: _sha(OUTPUT / name) for name in files}),
    )


def compare(candidate, control, originals, truth):
    pair = {}
    for key, row in (("candidate", candidate), ("aligned", control)):
        metrics = row["result"]["metrics"]
        names = (
            "native_observations",
            "tracks",
            "observations",
            "cavity_offered",
            "addition_status",
            "checked_residual_addition",
            "reassociation_targets",
            "reassociation_admitted",
            "reassociation_selected",
            "ordered_phase_seeds",
            "position_optimizer",
            "initial_screen",
            "discovery_sharing",
            "finish_eligibility",
            "stage_s",
            "numerical_worker_peak_rss_kib",
        )
        arms = {}
        for arm in ARMS:
            endpoint = row["result"]["arms"][arm]["latlon"]
            arms[arm] = dict(
                latlon=endpoint,
                error_km=distance_km(endpoint, truth),
                rf_rms_hz=metrics.get(f"{arm}_conditional_rms_hz"),
                frequency_score=metrics.get(f"{arm}_frequency_score"),
                associated=metrics.get(f"{arm}_associated_observations"),
            )
        pair[key] = dict(
            status=row["result"]["status"],
            cpu=row["cpu"],
            arms=arms,
            work={name: metrics[name] for name in names if name in metrics},
            wall_s=row["worker_wall_s"],
            cpu_s=row["worker_cpu_s"],
            resources=row.get("resources"),
        )
    for arm in ARMS:
        first, second = (pair[k]["arms"][arm] for k in ("candidate", "aligned"))
        first["aligned_shift_km"] = distance_km(first["latlon"], second["latlon"])
        first["originals"] = {
            role: dict(
                values[arm],
                error_km=distance_km(values[arm]["latlon"], truth),
                shift_km=distance_km(values[arm]["latlon"], first["latlon"]),
            )
            for role, values in originals.items()
        }
    return dict(id=candidate["id"], **pair)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "measure", "score"))
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--case", choices=ROSTER)
    args = parser.parse_args()
    if args.command == "measure":
        measure(args.work, args.case)
    elif args.command == "run":
        run(args.work)
    else:
        score()


if __name__ == "__main__":
    main()
