"""Compare the sealed clock fits on two pre-existing ordinary IQ donor products."""

import argparse
import json
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, read_predictions, references
from ..scoring import ARMS, distance_km, validate_result
from ..variants import joint_clock_model, native_lean
from . import iq_joint_trial as iq
from . import native_joint_trial as native
from .clock_model_trial import REPORT as PREPARED
from .clock_model_trial import _gzip
from .full_v5_check import _load_case, _sha
from .recording_to_v5 import save

REPORT = PREPARED.with_name("native-clock-donor")
DONORS = Path("/tmp/leo-iq-joint-20261119")
WORKER = Path(__file__).with_name("native_clock_model_worker.py")
METHODS = ("native_joint_clock_model", "native_joint_fixed_reference", "iq_to_joint")


def plan(bundle, cpu):
    input_lock = iq.verify_lock(iq.REPORT)
    prior = iq.read(iq.SEAL)
    if encoded(prior) != encoded(iq.source_lock(bundle)):
        raise ValueError("native IQ donor sources differ from their immutable deployment")
    locked_clock = iq.read(PREPARED / "source-lock.json")["files"]
    source = Path(joint_clock_model.__file__)
    if _sha(source) != locked_clock[str(source.relative_to(native.native.ROOT))]:
        raise ValueError("clock fitter differs from the prepared analysis")
    receipt = iq.read(iq.REPORT / "stage-receipts.json")
    queries, paths = [], []
    for ident in iq.CASES:
        donor = receipt[ident]
        factor = DONORS / ident / "native.json"
        digest = prior["inputs"][ident]["ordinary_native_sha256"]
        packet, mounts = iq.bind_fresh(_load_case(ident), factor, digest)
        if donor["native_query"] != packet or donor["raw"]["native_sha256"] != digest:
            raise ValueError(f"{ident} is not the complete sealed ordinary donor")
        queries.append(dict(
            id=ident, native_sha256=digest, catalog_sha256=packet["catalogue"]["sha256"],
            observation_sha256=donor["graph_sha256"], packet=packet,
            input_sha256=iq.sha256(encoded(packet)).hexdigest(), tile=packet["offer"],
        ))
        paths.append(mounts)
    return dict(
        queries=queries, source_iq_lock_sha256=input_lock,
        prepared_clock_lock_sha256=_sha(PREPARED / "source-lock.json"),
        runner_sha256=_sha(Path(__file__)), worker_sha256=_sha(WORKER), cpu=cpu,
        timeout_s=native.CAP,
    ), paths


def run_fit(query, paths, bundle, cpu, method):
    argv = native.command(cpu, paths, bundle)
    argv[argv.index(str(native.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind", str(Path(joint_clock_model.__file__)),
        "/worker/tools/pipeline_eval/variants/joint_clock_model.py",
    ]
    if method == METHODS[1]:
        argv.append("--clock-off")
    start = perf_counter()
    try:
        done = subprocess.run(
            argv, input=encoded(query["packet"]), check=True,
            capture_output=True, timeout=native.CAP,
        )
        out = json.loads(done.stdout)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1500:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        out = dict(result=dict(status=status, reason=detail or str(error), metrics={},
                               boundary="Ordinary detector donor through the sealed native Graph",
                               arms={arm: {"latlon": None} for arm in ARMS}))
    if out["result"]["status"] in ("ok", "withheld") and (
        out["observation_sha256"] != query["observation_sha256"]
        or out["counts"]["native_bytes"] != paths["native"].stat().st_size
        or out["address_space_limit_mib"] != native_lean.AS_LIMIT_MIB
        or any("localization_v3" in item for item in out["imported_first_party"])
    ):
        raise ValueError("measured fit escaped the mounted ordinary native source or budget")
    validate_result(out["result"])
    identity = {k: v for k, v in query.items() if k != "packet"}
    row = dict(identity | out, variant=method, cpu=cpu, worker_wall_s=perf_counter() - start)
    print(query["id"], method, out["result"]["status"], row["worker_wall_s"], flush=True)
    return row


def run(output, bundle, cpu):
    prereg, paths = plan(bundle, cpu)
    output.mkdir(parents=True, exist_ok=False)
    save(output / "plan.json", prereg)
    measurements = {method: [] for method in METHODS}
    prior = read_predictions(iq.REPORT / "positions.jsonl.gz")
    for query, mounts in zip(prereg["queries"], paths, strict=True):
        ident = query["id"]
        fresh = [run_fit(query, mounts, bundle, cpu, method) for method in METHODS[:2]]
        clock, fixed = [row["result"]["metrics"].get("clock_fit", {}) for row in fresh]
        for key in ("training_ownership", "final_c0_ownership", "final_fitted_c_ownership"):
            if key in clock and key in fixed and clock[key] != fixed[key]:
                raise ValueError("ordinary donor models received different fixed associations")
        for method, row in zip(METHODS, fresh, strict=False):
            measurements[method].append(row)
        archived = prior[ident]
        inputs = ("native_sha256", "catalog_sha256", "input_sha256", "observation_sha256")
        if any(archived[key] != query[key] for key in inputs):
            raise ValueError("archived joint result uses different ordinary or Graph inputs")
        if archived["tile"] != query["packet"]["offer"]:
            raise ValueError("archived joint used a different tile")
        measurements[METHODS[2]].append(dict(archived, variant=METHODS[2]))
    if prereg != plan(bundle, cpu)[0]:
        raise ValueError("source seal changed during the donor replays")
    files = {}
    for method, rows in measurements.items():
        path = output / f"{method}.jsonl.gz"
        _gzip(path, rows)
        files[path.name] = _sha(path)
    save(output / "prediction-lock.json", dict(
        cases=list(iq.CASES), files=files, plan_sha256=_sha(output / "plan.json"),
    ))
    refs = {row["id"]: row for row in references("smoke", None)[1]}
    scores = []
    for method, rows in measurements.items():
        for row in rows:
            record, result = row["id"], row["result"]
            for arm in ARMS:
                value = result["arms"][arm]
                held = result["metrics"].get("held_by_arm", {}).get(arm, {})
                scores.append(dict(
                    id=record, variant=method, arm=arm, status=result["status"],
                    reason=result.get("reason"),
                    error_km=distance_km(value["latlon"], refs[record]["truth"]),
                    rf_rms_hz=value.get("rf_rms_hz"), held_rms_hz=held.get("held_rf_rms_hz"),
                    worker_wall_s=row["worker_wall_s"],
                    worker_cpu_s=row.get("worker", {}).get("cpu_s"),
                ))
    save(output / "scores.json", scores)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--bundle", type=Path, default=native.BUNDLE)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    run(args.output, args.bundle, args.cpu)
