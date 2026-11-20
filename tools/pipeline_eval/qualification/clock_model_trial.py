"""Seal and assess the v5 shared receiver oscillator on original archive inputs."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import ROOT, encoded, read_predictions, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from ..variants import joint_clock_model, v5_lean
from . import fresh_scenes as sandbox
from . import joint_orbits_inputs, phase_confirmation, robust_orbit_fit_trials
from .clock_model_worker import FIXED_CONTROL, METHODS
from .full_v5_check import _load_case, _sha
from .prefix_figures import TIMING_IDS
from .recording_to_v5 import save
from .robust_em_trials import load

REPORT = ROOT / "reports/2026_11_19_receiver_screening/factors/clock-model"
SALT = "receiver-clock-model/v1:"
TIMEOUT = 60
CPUS = (8, 9)


def roster():
    archived, _ = corpus._selection("ds26-common127")
    roof, _ = corpus._selection("roof16")
    native_joint = ROOT / "reports/2026_11_19_receiver_screening/inference/native-joint/roster.json"
    native_ids = {row["recording"] for row in json.loads(native_joint.read_bytes())["cases"]}
    excluded = (
        set(TIMING_IDS) | set(roof) | set(robust_orbit_fit_trials.CONFIRMATION)
        | set(joint_orbits_inputs.CONFIRMATION) | native_ids
        | {"DS26-0066", "DS26-0287", "DS26-0152", "DS26-0283", "DS26-0092",
           "DS26-0313", "DS26-0080", "DS26-0078", "DS26-0002", "DS26-0072"}
    )
    eligible = [
        ident for ident in archived if ident not in excluded and _load_case(ident).get("graph")
    ]
    held = sorted(eligible, key=lambda ident: sha256((SALT + ident).encode()).digest())[:4]
    if len(held) != 4:
        raise ValueError("four opaque confirmation IDs required")
    return dict(timing=list(TIMING_IDS), confirmation=held, wrong_offer=[TIMING_IDS[0], *held[:2]])


def seal():
    local = Path(__file__).parent
    variants = ROOT / "tools/pipeline_eval/variants"
    old = v5_lean.SOURCE / "leo/analysis"
    paths = [
        Path(__file__), local / "clock_model_worker.py", local / "robust_em_trials.py",
        *(variants / f"{name}.py" for name in METHODS if name != FIXED_CONTROL),
        ROOT / "tools/pipeline_eval/reference/grid.py", ROOT / "src/leo/sky/propagation.py",
        corpus.FROZEN / "provenance.json", corpus.FROZEN / "roof-four-offers.json",
        old / "localization_v3/marginal.py",
        old / "localization_v3/history_position.py",
        old / "localization_v3/phase_prior.py",
        old / "research/retained_track_likelihood.py",
    ]
    return dict(
        files={
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): _sha(path)
            for path in paths
        },
        cases=roster(), selected_by=SALT, methods=list(METHODS),
        cpus=list(CPUS), timeout_s=TIMEOUT, scientific_source=v5_lean.SOURCE_SHA256,
        settings=dict(width_s=20, knot_spacing_s=30, gaussian_coefficients_sd_hz=200,
                      clock_affine_projection_seconds=[0, 300], phase_prior_s=2.5,
                      fixed_assignments=True, exact_linearizations=3),
    )


def _gzip(path, rows):
    write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))


def prepare(work):
    work.mkdir(mode=0o700)
    fixed = seal()
    save(work / "source-lock.json", fixed)
    queries = []
    for cohort, ids in fixed["cases"].items():
        mode = "wrong-region" if cohort == "wrong_offer" else "matched-tile"
        for ident in ids:
            packet, source = load(ident, mode, work / "cache")
            case = ident if mode == "matched-tile" else f"{ident}-wrong-offer"
            queries.append(dict(
                id=case, recording=ident, cohort=cohort, **source, tile=packet["offer"],
                input_sha256=sha256(encoded(packet)).hexdigest(),
                packet=packet,
            ))
    save(work / "input-lock.json", dict(
        inputs={q["id"]: {k: v for k, v in q.items() if k != "packet"} for q in queries},
        source_lock_sha256=_sha(work / "source-lock.json"),
    ))
    _gzip(work / "queries.jsonl.gz", queries)


def _queries(work):
    locked = json.loads((work / "input-lock.json").read_bytes())
    if (
        json.loads((work / "source-lock.json").read_bytes()) != seal()
        or _sha(work / "source-lock.json") != locked["source_lock_sha256"]
    ):
        raise ValueError("source lock changed")
    with gzip.open(work / "queries.jsonl.gz", "rt") as file:
        queries = [json.loads(line) for line in file]
    inventory = {q["id"]: {k: v for k, v in q.items() if k != "packet"} for q in queries}
    if locked["inputs"] != inventory:
        raise ValueError("query inventory changed")
    for query in queries:
        if sha256(encoded(query["packet"])).hexdigest() != query["input_sha256"]:
            raise ValueError(f"packet for {query['id']} changed")
    return queries


def attempt(query, method, cpu):
    command = sandbox._sandbox(cpu)
    command[-2:] = ["-m", "tools.pipeline_eval.qualification.clock_model_worker"]
    started = perf_counter()
    try:
        done = subprocess.run(
            command, input=encoded(query["packet"] | {"method": method}),
            capture_output=True, timeout=TIMEOUT, check=True,
        )
        outcome = json.loads(done.stdout)
    except (ValueError, OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1500:]
        outcome = dict(
            worker_cpu_s=None, max_rss_kib=None,
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=detail or str(err), boundary=joint_clock_model.BOUNDARY, metrics={},
                arms={arm: {"latlon": None} for arm in ARMS},
            ),
        )
    validate_result(outcome["result"])
    wall = perf_counter() - started
    print(query["id"], method, outcome["result"]["status"], round(wall, 2), flush=True)
    return dict(
        {k: v for k, v in query.items() if k != "packet"}, **outcome,
        variant=method, cpu=cpu, worker_wall_s=wall,
    )


def predict(work):
    queries = _queries(work)

    def lane(index):
        return [
            attempt(q, method, CPUS[index]) for i, q in enumerate(queries) if i % 2 == index
            for method in (*METHODS[i % len(METHODS) :], *METHODS[: i % len(METHODS)])
        ]

    with ThreadPoolExecutor(2) as pool:
        rows = [r for slot in pool.map(lane, range(2)) for r in slot]
    _queries(work)
    _gzip(work / "predictions.jsonl.gz", rows)
    save(work / "prediction-lock.json", dict(
        cases=[q["id"] for q in queries], input_lock_sha256=_sha(work / "input-lock.json"),
        source_lock_sha256=_sha(work / "source-lock.json"),
        files={"predictions.jsonl.gz": _sha(work / "predictions.jsonl.gz")},
    ))


def _original(row, ref):
    case = _load_case(row["recording"])
    receipt = phase_confirmation._original_v5_bindings(case)
    root = phase_confirmation.ARCHIVE if case["id"].startswith("DS26") else phase_confirmation.DS29
    for role in ROLES:
        path = root / f"{case['id']}-r0" / f"{role}-execution.json"
        if _sha(path) != receipt[role]["execution_sha256"]:
            raise ValueError(f"{case['id']} changed original {role} execution")
        data = json.loads(path.read_bytes())
        arms = {}
        for arm in ARMS:
            recorded = data["worker"]["arms"][arm]
            endpoint = recorded["endpoint_latlon"]
            expected = ref["reference"][role][arm]["latlon"]
            if (endpoint is None) != (expected is None) or (
                endpoint is not None and distance_km(endpoint, expected) > 1e-6
            ):
                raise ValueError("original replay endpoint differs from its sealed referee")
            arms[arm] = dict(
                latlon=endpoint, rf_rms_hz=recorded["residual_rms_hz"],
                frequency_score=recorded["frequency_score"],
            )
        status = "ok" if any(a["latlon"] is not None for a in arms.values()) else "withheld"
        result = dict(status=status, boundary="Original v5 historical execution", metrics={},
                      arms=arms, reason=None if status == "ok" else "original saved null")
        validate_result(result)
        yield dict(
            row, variant=role, result=result, execution=receipt[role],
            worker_wall_s=data["process"]["wall_seconds"],
            worker_cpu_s=data["process"].get("cpu_seconds"),
        )


def export(work, output):
    from .projector_roof import roster as references

    queries = _queries(work)
    lock = json.loads((work / "prediction-lock.json").read_bytes())
    archive = work / "predictions.jsonl.gz"
    if (
        lock["cases"] != [q["id"] for q in queries]
        or lock["source_lock_sha256"] != _sha(work / "source-lock.json")
        or lock["input_lock_sha256"] != _sha(work / "input-lock.json")
        or _sha(archive) != lock["files"][archive.name]
    ):
        raise ValueError("scoring inputs differ from the immutable predictions")
    with gzip.open(archive, "rt") as file:
        rows = {(r["id"], r["variant"]): r for r in map(json.loads, file)}
    if rows.keys() != {(q["id"], m) for q in queries for m in METHODS}:
        raise ValueError("predictions do not cover every scheduled case and method")
    refs = {r["id"]: r for r in references()}
    groups, scores = {}, []
    for query in queries:
        ident, cohort, rec = (query[k] for k in ("id", "cohort", "recording"))
        public = {k: v for k, v in query.items() if k != "packet"}
        current = [rows[ident, method] for method in METHODS]
        for row in current:
            if any(row[key] != value for key, value in public.items()):
                raise ValueError(f"prediction {ident} does not match the sealed input")
        clock, control = [r["result"]["metrics"].get("clock_fit", {}) for r in current[:2]]
        for key in ("training_ownership", "final_c0_ownership", "final_fitted_c_ownership"):
            if key in clock and key in control and clock[key] != control[key]:
                raise ValueError("clock and matched control did not use identical assignments")
        ref = refs[rec]
        if cohort != "wrong_offer":
            current.extend(_original(public, ref))
        elif distance_km(query["tile"]["center"], ref["truth"]) <= 2**0.5 * 12.5:
            raise ValueError(f"declared wrong tile for {ident} may contain the referee")
        for row in current:
            group = groups.setdefault(cohort, {})
            group.setdefault(row["variant"], []).append(row)
            for arm in ARMS:
                value = row["result"]["arms"][arm]
                held = row["result"]["metrics"].get("held_by_arm", {}).get(arm, {})
                scores.append(dict(
                    id=ident, cohort=cohort, variant=row["variant"], arm=arm,
                    status=row["result"]["status"], seconds=row["worker_wall_s"],
                    error_km=distance_km(value["latlon"], ref["truth"]),
                    forced_error_km=distance_km(value.get("forced_latlon"), ref["truth"]),
                    rf_rms_hz=value.get("rf_rms_hz"), held_score=held.get("held_score"),
                    held_rms_hz=held.get("held_rf_rms_hz"), held_orbits=held.get("held_orbits"),
                ))
    output.mkdir(parents=True, exist_ok=True)
    for from_file in ("source-lock.json", "input-lock.json", "prediction-lock.json", archive.name):
        write(output / from_file, (work / from_file).read_bytes())
    for cohort, methods in groups.items():
        path = output / cohort
        path.mkdir(exist_ok=True)
        files = {}
        for method, group in methods.items():
            name = f"{method}.jsonl.gz"
            _gzip(path / name, group)
            files[name] = _sha(path / name)
            read_predictions(path / name)
        save(path / "prediction-lock.json", dict(
            cases=[r["id"] for r in queries if r["cohort"] == cohort], files=files,
            root_lock_sha256=_sha(output / "prediction-lock.json"),
        ))
    save(output / "scores.json", scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "predict", "export"))
    parser.add_argument("--work", type=Path, default=Path("/tmp/leo-joint-clock-model-20261119"))
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.work)
    elif args.mode == "predict":
        predict(args.work)
    else:
        export(args.work, args.output)


if __name__ == "__main__":
    main()
