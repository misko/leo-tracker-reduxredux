"""Freeze the GLRT distillation rule and replay held whole native streams."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .. import compact_cut, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, validate_result
from ..variants import pilot_distill as admission
from . import one_lane_roster
from . import pilot_distill_labels as labels
from .full_v5_check import BULK, _sha
from .peak_support_trial import BAND, prior_directory

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-deadline/pilot-distillation"
TRAIN = ("DS26-0036", "DS29-0082")
HELD = ("DS26-0237", "DS29-0174", "DS26-0122", "DS29-0247")
SUPPLEMENT = ("DS26-0144", "DS29-0491")
METHODS = ("stock", "learned", "strength", "oracle")
CPUS = (18, 19, 20, 21)
LIMIT = 150
MEMORY = 512 * 2**20
ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "OPENBLAS_NUM_THREADS")
WORKER = Path(__file__).with_name("pilot_distill_worker.py").resolve()


def sources():
    return {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (
            Path(__file__).resolve(),
            WORKER,
            Path(admission.__file__),
            Path(labels.__file__),
            Path(compact_cut.__file__),
            REPORT / "PROTOCOL.md",
            BAND / "prediction-lock.json",
            one_lane_roster.ROSTER,
            one_lane_roster.RECONSTRUCTION / "prediction-lock.json",
            one_lane_roster.FRESH / "raw-prediction-lock.json",
        )
    }


def narrow_sources():
    lock = whole_iq.read(BAND / "prediction-lock.json")
    return whole_iq.read(
        whole_iq.checked(BAND / "source-lock.json", lock["files"]["source-lock.json"])
    )["cases"]


def recording(ident, narrow, media, extensions):
    case, request = one_lane_roster.bind(ident, extensions)
    is_narrow = ident in narrow
    if is_narrow:
        entry = narrow[ident]
        if (
            entry["capture_native_sha256"] != case["native"]["sha256"]
            or entry["request_sha256"] != case["request"]["sha256"]
            or entry["history"] != request["causal_snapshots"]
        ):
            raise ValueError("narrow recording provenance disagrees with the common causal request")
        expected = entry["ordinary_sha256"]
        fast = dict(
            path=str(prior_directory(ident) / "native.json"),
            file_sha256=expected,
            native_sha256=expected,
        )
    else:
        fast = media[ident]
    teacher = dict(
        path=str(BULK / case["native"]["path"]),
        file_sha256=case["native"]["sha256"],
        native_sha256=case["native"]["sha256"],
    )
    job = request["job"]
    if job["search_center"] != case["regions"][0]["center"]:
        raise ValueError("compact offer differs from the original truth-free request")
    return dict(
        id=ident,
        session=case["session_id"],
        fast=fast,
        teacher=teacher,
        detector_range="narrow" if is_narrow else "wide",
        tile=dict(case["regions"][0], width_km=25),
        original_request_sha256=case["request"]["sha256"],
        screen_center=job["screen_center"],
        archive=job["tle_root"],
        history=request["causal_snapshots"],
        catalog_sha256=case["catalog"]["sha256"],
        track_config=job["track_config"]["path"],
        track_config_sha256=job["track_config"]["sha256"],
    )


def bound_bytes(entry):
    path = whole_iq.checked(Path(entry["path"]), entry["file_sha256"])
    body = path.read_bytes()
    if path.suffix == ".gz":
        body = gzip.decompress(body)
    if sha256(body).hexdigest() != entry["native_sha256"]:
        raise ValueError(f"unexpected native factors {path}")
    return body


def stream(entry):
    return json.loads(bound_bytes(entry))


def freeze(report=REPORT):
    model = report / "frozen-model.json"
    if model.exists():
        raise FileExistsError("GLRT pilot rule is already frozen")
    narrow = narrow_sources()
    train = {ident: recording(ident, narrow, {}, {}) for ident in TRAIN}
    cohorts = [
        labels.training_rows(
            labels.probe_pairs(stream(binding["teacher"]), stream(binding["fast"]))
        )
        for binding in train.values()
    ]
    rule, diagnostics = labels.fit(cohorts)
    save_json(
        model,
        dict(
            features=admission.FEATURES,
            rule=asdict(rule),
            training=train,
            train_counts={ident: row[2] for ident, row in zip(TRAIN, cohorts, strict=True)},
            diagnostics=diagnostics,
            held=HELD,
            supplementary=SUPPLEMENT,
            sources=sources(),
        ),
    )
    print("Froze", model, _sha(model), flush=True)


def chosen_digest(selected):
    return sha256(json.dumps(sorted(selected.items())).encode()).hexdigest()


def stage_authority(work, binding, model):
    ident = binding["id"]
    folder = work / ident
    folder.mkdir()
    fast_bytes = bound_bytes(binding["fast"])
    fast = json.loads(fast_bytes)
    fast_path = folder / "fast-native.json"
    write(fast_path, fast_bytes)
    rate = fast["source"]["sample_rate_hz"]
    frame, tolerance = round(rate / 750), rate * 0.2e-6
    probes = [row["candidates"] for row in fast["source"]["probes"]]
    rule = admission.Rule(**whole_iq.read(Path(model["path"]))["rule"])
    selections = dict(
        stock={
            i: winner
            for i, rows in enumerate(probes)
            if (winner := admission.stock_winner(rows)) is not None
        },
        learned={
            i: winner
            for i, rows in enumerate(probes)
            if (winner := rule.select(rows, frame, tolerance)) is not None
        },
    )
    selections["strength"] = admission.strongest(probes, len(selections["learned"]))
    save_json(folder / "fast-selections.json", {k: chosen_digest(v) for k, v in selections.items()})
    pairs = labels.probe_pairs(stream(binding["teacher"]), fast)
    oracle, counts, agreements = labels.agreements(pairs, selections)
    selections["oracle"] = oracle
    local_archive = folder / "tle"
    shared = {
        k: binding[k] for k in ("session", "tile", "screen_center", "track_config_sha256")
    } | {
        "fast": {"native_sha256": binding["fast"]["native_sha256"], "local": str(fast_path)},
        "archive": str(local_archive),
    }
    for source in Path(binding["archive"]).rglob("*.tle"):
        relative = source.relative_to(binding["archive"])
        target = local_archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        whole_iq.checked(target, binding["history"][source.name])
    config = folder / "track-config.json"
    shutil.copyfile(binding["track_config"], config)
    whole_iq.checked(config, shared["track_config_sha256"])
    shared["track_config"] = str(config)
    inputs = {}
    for arm, selection in selections.items():
        input_file = folder / f"{arm}.json"
        payload = shared | {"counts": {arm: len(selection)}}
        if arm != "stock":
            payload["selection_sha256"] = {arm: chosen_digest(selection)}
        if arm == "learned":
            payload["rule"] = model
        if arm == "oracle":
            payload["oracle_members"] = sorted(selection.items())
        save_json(input_file, payload)
        inputs[arm] = {"path": str(input_file), "sha256": _sha(input_file)}
    return dict(
        binding=binding,
        inputs=inputs,
        fast_selections_sha256=_sha(folder / "fast-selections.json"),
        counts=counts,
        agreements=agreements,
    )


def run_one(work, bundle, case, arm, cpu):
    ident, inputs = case["binding"]["id"], case["inputs"][arm]
    private = whole_iq.checked(Path(inputs["path"]), inputs["sha256"])
    folder = work / ident / arm
    folder.mkdir()
    unit = "leo-pilot-distill-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={folder}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        f"--property=RuntimeMaxSec={LIMIT}s",
        f"--setenv=TMPDIR={folder}",
        *(f"--setenv={name}=1" for name in ENV),
        "/usr/bin/taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-IB",
        str(WORKER),
        str(bundle),
        str(private),
        arm,
        str(cpu),
        unit,
    ]
    started = perf_counter()
    output, log = folder / "output.json", folder / "service.log"
    with output.open("wb") as stdout, log.open("wb") as stderr:
        try:
            exit_code = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=LIMIT + 12, check=False
            ).returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=6)
            exit_code = 124
    service_wall_s = perf_counter() - started
    service_log = log.read_text(errors="replace")
    if exit_code == 0:
        payload = whole_iq.read(output)
    else:
        timed_out = exit_code == 124 or "result: timeout" in service_log
        payload = dict(
            result=dict(
                status="timed_out" if timed_out else "failed",
                reason="position service deadline" if timed_out else "position service failed",
                boundary="Whole stored ordinary GLRT factors through compact position",
                metrics={},
                arms={name: {"latlon": None} for name in ARMS},
            ),
            service_tail=service_log.splitlines()[-10:],
        )
    validate_result(payload["result"])
    binding = case["binding"]
    row = dict(
        id=ident,
        method=f"pilot_distill_{arm}",
        condition=arm,
        mode="matched-tile",
        cpu=cpu,
        exit_code=exit_code,
        service_wall_s=service_wall_s,
        service_log_sha256=_sha(log),
        detector_range=binding["detector_range"],
        original_request_sha256=binding["original_request_sha256"],
        paired_capture_sha256=binding["teacher"]["native_sha256"],
        paired_ordinary_sha256=binding["fast"]["native_sha256"],
        catalog_sha256=binding["catalog_sha256"],
        tile={k: v for k, v in binding["tile"].items() if k != "width_km"},
        **payload,
    )
    save_json(folder / "receipt.json", row)
    print(ident, arm, row["result"]["status"], round(service_wall_s, 2), flush=True)
    return row


def load_model(report=REPORT):
    path = report / "frozen-model.json"
    declaration = whole_iq.read(path)
    if declaration["sources"] != sources() or declaration["held"] != list(HELD):
        raise ValueError("held trial differs from the frozen model and protocol")
    return dict(path=str(path), sha256=_sha(path))


def replay(work, report=REPORT):
    if (report / "prediction-lock.json").exists():
        raise FileExistsError("GLRT pilot predictions are already frozen")
    model = load_model(report)
    work.mkdir(parents=True, exist_ok=False)
    bundle = compact_cut.install(work / "compact-cut")
    module = bundle / "tools/pipeline_eval/variants/pilot_distill.py"
    shutil.copyfile(admission.__file__, module)
    whole_iq.checked(module, _sha(Path(admission.__file__)))
    narrow = narrow_sources()
    _, media, _, extensions, _ = one_lane_roster.inventory()
    cases = HELD + SUPPLEMENT
    plan = {}
    for i, ident in enumerate(cases):
        stage = stage_authority(work, recording(ident, narrow, media, extensions), model)
        schedule = METHODS[i % 4 :] + METHODS[: i % 4]
        plan[ident] = stage | {"cpu": CPUS[i % len(CPUS)], "order": schedule}
        print(ident, "prepared", flush=True)
    plan_path = report / "replay-plan.json"
    save_json(
        plan_path,
        dict(
            model=model,
            cases=plan,
            installed=whole_iq.receiver_identity(bundle),
            compiler=whole_iq.native_sources(bundle),
            memory=MEMORY,
            swap=0,
            limit_s=LIMIT,
            load=os.getloadavg(),
        ),
    )

    def lane(cpu):
        return [
            run_one(work, bundle, stage, arm, cpu)
            for stage in plan.values()
            if stage["cpu"] == cpu
            for arm in stage["order"]
        ]

    with ThreadPoolExecutor(len(CPUS)) as pool:
        attempts = [row for records in pool.map(lane, CPUS) for row in records]
    path = report / "positions.jsonl.gz"
    write(
        path,
        gzip.compress(
            b"".join(
                json.dumps(row, sort_keys=True, allow_nan=False).encode() + b"\n"
                for row in attempts
            ),
            mtime=0,
        ),
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=cases,
            files={p.name: _sha(p) for p in (path, plan_path, Path(model["path"]))},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "replay"))
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--work", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.report)
    elif args.work:
        replay(args.work, args.report)
    else:
        parser.error("replay needs a fresh local work directory and an unrun report")
