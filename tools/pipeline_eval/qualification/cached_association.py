"""Replay fresh, paired native joint receivers with identical frozen factors and offers."""

import argparse
import gzip
import json
import subprocess
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, distance_km, validate_result
from ..variants import cached_association as cache
from . import native_joint_full as full
from . import native_joint_trial as trial
from .native_lean_eval import _write_predictions

REPORT = full.REPORT.parent.parent / "refinement/cached-association"
WORKER = Path(__file__).with_name("cached_association_worker.py")
METHOD, STOCK = cache.METHOD, trial.METHOD
MATCHED = (
    "DS26-0036",
    "DS29-0082",
    "DS26-0187",
    "DS26-0197",
    "DS29-0519",
    "DS26-0231",
    "DS26-0223",
    "DS29-0316",
)
OMITTED = ("DS26-0036-r0", "DS29-0357-omitted")
FINGERPRINTS = ("native_sha256", "catalog_sha256", "input_sha256", "observation_sha256")
FILES = ("positions.jsonl.gz", "stock-positions.jsonl.gz")


def jobs():
    inputs = trial.phase.frozen_inputs()
    measured = {row["id"]: (row, paths) for row, paths in trial.jobs(inputs)}
    measured.update({row["id"]: (row, paths) for row, paths in full.omitted_controls(inputs)})
    return [measured[ident] for ident in (*MATCHED, *OMITTED)]


def sources(bundle):
    return dict(
        stock=trial.sources(bundle),
        changed={
            str(path.relative_to(corpus.REPO)): trial.phase.digest(path)
            for path in (Path(cache.__file__), WORKER, Path(__file__))
        },
    )


def archived():
    lock = trial.phase._read(full.REPORT / "prediction-lock.json")
    trial.secant_full._verify_files(full.REPORT, lock["files"])
    cases = {*MATCHED, *OMITTED}
    with gzip.open(full.REPORT / "positions.jsonl.gz", "rt") as stream:
        rows = {r["id"]: r for r in map(json.loads, stream) if r["id"] in cases}
    if rows.keys() != cases:
        raise ValueError("frozen native-joint archive does not cover every selected offer")
    return rows


def command(cpu, paths, bundle):
    argv = trial.command(cpu, paths, bundle)
    argv[argv.index(str(trial.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind",
        cache.__file__,
        "/worker/tools/pipeline_eval/variants/cached_association.py",
    ]
    return argv


def attempt(query, paths, cpu, bundle, archive, cached):
    ident, packet = query["id"], query["packet"]
    input_hash = corpus._sha(encoded(packet))
    if input_hash != archive["input_sha256"]:
        raise ValueError(f"{ident} input request differs from the frozen native stock")
    began = perf_counter()
    try:
        run = subprocess.run(
            command(cpu, paths, bundle),
            input=encoded(dict(packet, cache_association=cached)),
            capture_output=True,
            check=True,
            timeout=trial.CAP,
        )
        row = json.loads(run.stdout)
    except (subprocess.SubprocessError, ValueError) as error:
        stderr = (getattr(error, "stderr", None) or b"").decode(errors="replace")
        row = dict(
            result=dict(
                status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
                reason=stderr[-2200:] or str(error),
                boundary=cache.BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None) for arm in ARMS},
            )
        )
    row.update(
        id=ident,
        recording=query["recording"],
        cohort="roof" if ident in MATCHED else "omitted",
        method=METHOD if cached else STOCK,
        input_sha256=input_hash,
        catalog_sha256=packet["catalogue"]["sha256"],
        native_sha256=packet["native"]["sha256"],
        tile=packet["offer"],
        cpu=cpu,
        worker_wall_s=perf_counter() - began,
    )
    validate_result(row["result"])
    fingerprints = (*FINGERPRINTS, "tile")
    if not row.get("observation_sha256"):
        fingerprints = tuple(key for key in fingerprints if key != "observation_sha256")
    if any(row[key] != archive[key] for key in fingerprints):
        raise ValueError(f"{ident} factors, Graph or offer differ from the frozen native stock")
    print(ident, row["method"], row["result"]["status"], row.get("worker", {}), flush=True)
    return row


def measure(candidate, stock, archive):
    result, control, history = (row["result"] for row in (candidate, stock, archive))
    status = (result["status"], result["reason"])
    same_decision = (
        status == (control["status"], control["reason"]) == (history["status"], history["reason"])
    )
    completed = result["status"] in ("ok", "withheld") and control["status"] in ("ok", "withheld")
    same_owners = bool(completed and candidate.get("ownership_passes")) and (
        candidate["ownership_passes"] == stock["ownership_passes"]
    )
    summary = dict(
        id=candidate["id"],
        same_decision=same_decision,
        same_owners=same_owners,
        status_candidate=result["status"],
        status_control=control["status"],
        arms={},
        same_graph=bool(candidate.get("observation_sha256"))
        and (candidate["observation_sha256"] == stock.get("observation_sha256")),
        candidate_cpu_s=candidate.get("worker", {}).get("cpu_s"),
        control_cpu_s=stock.get("worker", {}).get("cpu_s"),
        candidate_association=candidate.get("association"),
        control_association=stock.get("association"),
    )
    for arm in ARMS:
        a, b, ref = (row["arms"][arm] for row in (result, control, history))
        a_point, b_point, ref_point = (r.get("forced_latlon") for r in (a, b, ref))
        summary["arms"][arm] = dict(
            endpoint_shift_m=None
            if a_point is None or b_point is None
            else 1000 * distance_km(a_point, b_point),
            archived_endpoint_shift_m=None
            if a_point is None or ref_point is None
            else 1000 * distance_km(a_point, ref_point),
            endpoint_presence_equal=(a_point is None) == (b_point is None) == (ref_point is None),
            rms_delta_hz=None
            if "rf_rms_hz" not in a or "rf_rms_hz" not in b
            else a["rf_rms_hz"] - b["rf_rms_hz"],
            objective_delta=None
            if "frequency_score" not in a or "frequency_score" not in b
            else a["frequency_score"] - b["frequency_score"],
        )
    return summary


def run(work, cpu, bundle, output, repeat):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    frozen = sources(bundle)
    inputs = jobs()
    old = archived()
    save_json(
        work / "plan.json",
        dict(cases=[query for query, _ in inputs], cpu=cpu, repeat=repeat, source=frozen),
    )
    start = perf_counter()
    pairs = {ident: [] for ident in old}
    for index in range(repeat):
        for slot, (query, paths) in enumerate(inputs):
            ident = query["id"]
            modes = (False, True) if (index + slot) % 2 == 0 else (True, False)
            pair = {}
            for mode in modes:
                row = attempt(query, paths, cpu, bundle, old[ident], mode)
                save_json(work / f"{ident}-{index}-{row['method']}.json", row)
                pair[mode] = row
            pairs[ident].append(pair)
    if sources(bundle) != frozen:
        raise ValueError("sources changed during the paired study")
    output = local_output(output)
    report = dict(
        cpu=cpu,
        paired_repetitions=repeat,
        wall_s=perf_counter() - start,
        pairs={
            ident: [measure(pair[True], pair[False], old[ident]) for pair in values]
            for ident, values in pairs.items()
        },
    )
    save_json(output / "measurements.json", report)
    save_json(output / "plan.json", trial.phase._read(work / "plan.json"))
    save_json(output / "source-lock.json", frozen)
    for mode, filename in zip((True, False), FILES, strict=True):
        _write_predictions(
            output / filename, [pairs[ident][0][mode] for ident in (*MATCHED, *OMITTED)]
        )
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=(*MATCHED, *OMITTED),
            files={
                name: trial.phase.digest(output / name)
                for name in (*FILES, "plan.json", "source-lock.json", "measurements.json")
            },
            frozen_native_lock_sha256=trial.phase.digest(full.REPORT / "prediction-lock.json"),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--bundle", type=Path, default=trial.BUNDLE)
    parser.add_argument("--cpu", type=int, default=23)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    run(args.work, args.cpu, args.bundle, args.out, args.repeat)


if __name__ == "__main__":
    main()
