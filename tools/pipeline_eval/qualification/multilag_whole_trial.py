"""Run two matched whole saved-IQ services with only the fifth-center scout changed."""

import argparse
import shutil
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import differential_runtime as runtime
from . import fifth_completion, multilag_search_eval, multilag_whole_raw, whole_center_union
from .full_v5_check import _sha

REPORT = multilag_search_eval.REPORT.with_name("multilag-whole")
WORK = Path("/var/tmp/leo-multilag-whole-20261119")
CORES = {"DS26-0197": [4, 5], "DS29-0519": [5, 4]}
METHOD = "multilag_whole"
MODULE = "tools.pipeline_eval.qualification.multilag_whole_trial"
LIMIT = 540


def prior(ident):
    if ident == "DS26-0197":
        return dict(
            four=(whole_center_union.REPORT, whole_center_union.BASELINE, "control"),
            five=(whole_center_union.REPORT, whole_center_union.METHOD, "candidate"),
        )
    folder = fifth_completion.SCREEN / "receiver-core/full-stride"
    return dict(
        four=(folder, "wide-cfo-stride_control", "control"),
        five=(fifth_completion.REPORT, fifth_completion.METHOD, ident),
    )


def historical(ident):
    controls = {}
    for role, (folder, method, branch) in prior(ident).items():
        receipt = folder / "prediction-lock.json"
        lock = whole_iq.read(receipt)
        files = {
            f: lock["files"][f]
            for f in ("source-lock.json", "positions.jsonl.gz", "resources.json")
        }
        for name, digest in files.items():
            whole_iq.checked(folder / name, digest)
        controls[role] = dict(
            folder=str(folder.relative_to(ROOT)),
            method=method,
            branch=branch,
            prediction_lock_sha256=_sha(receipt),
            files=files,
        )
    return controls


def freeze(work):
    target = REPORT / "source-lock.json"
    if target.exists():
        raise FileExistsError("complete replay is already frozen")
    stage = multilag_search_eval.REPORT / "source-lock.json"
    source = whole_iq.read(stage)
    waveform = multilag_search_eval.REPORT / "waveform.json.gz"
    # The waveform lock had been created before running the common raw detector panel.
    import gzip
    import json

    witness = json.loads(gzip.decompress(waveform.read_bytes()))
    if witness["lock_sha256"] != _sha(stage) or not any(
        row.get("matches", {}).get("multilag", [{}])[0].get("category") == "physical_gated"
        for row in witness["rows"]
        if row["cohort"] == "held" and row["kind"] == "miss"
    ):
        raise ValueError("the locked three-lag scorer has no held raw admission witness")
    parents = [
        whole_center_union.REPORT / "source-lock.json",
        fifth_completion.REPORT / "source-lock.json",
    ]
    first, second = map(whole_iq.read, parents)
    if any(first[k] != second[k] for k in ("receiver", "receiver_files", "native_sources")):
        raise ValueError("the two historical branches use different installed compact receivers")
    cases, controls = {}, {}
    for ident, cpus in CORES.items():
        common = (first if ident == "DS26-0197" else second)["cases"][ident]
        case, request = whole_iq.binding(ident)
        if (
            case["native"]["sha256"],
            case["recording"],
            case["request"]["sha256"],
            case["catalog"]["sha256"],
            case["regions"][0],
            request["causal_snapshots"],
        ) != (
            common["capture_native_sha256"],
            common["recording"],
            common["request_sha256"],
            common["catalog_sha256"],
            common["tile"],
            common["orbit_snapshots"],
        ):
            raise ValueError("whole replay does not match its original physical/request authority")
        controls[ident] = historical(ident)
        cases[ident] = dict(
            common,
            cpus=cpus,
            cohort="known hard" if ident == "DS26-0197" else "prespecified control",
        )
    work.mkdir(parents=True, exist_ok=False)
    release = work / "release"
    release.mkdir()
    detectors = {}
    for name, spec, fname in (
        ("candidate", source["detectors"]["candidate"], "libleo-adaptive-detector.so"),
        ("scout", source["multilag"], "libmultilag-scout.so"),
    ):
        path = release / fname
        shutil.copyfile(whole_iq.checked(Path(spec["path"]), spec["sha256"]), path)
        detectors[name] = dict(
            path=str(whole_iq.checked(path, spec["sha256"])), sha256=spec["sha256"]
        )
    raw_release = release / "raw-release.json"
    save_json(raw_release, detectors)
    raw_release.chmod(0o644)
    programs = runtime.source_identity() | {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (
            Path(__file__),
            Path(multilag_whole_raw.__file__),
            Path(multilag_search_eval.multilag_search.__file__),
            Path(multilag_search_eval.center_union.__file__),
        )
    }
    roots = (REPORT / "PROTOCOL.md", stage, waveform, *parents)
    lock = dict(
        cases=cases,
        historical=controls,
        programs=programs,
        detectors=detectors,
        **{k: first[k] for k in ("receiver", "receiver_files", "native_sources")},
        limit_s=LIMIT,
        swap_max=0,
        memory_max=whole_iq.MEMORY,
        files={str(path.relative_to(ROOT)): _sha(path) for path in roots},
        raw_release_sha256=_sha(raw_release),
    )
    save_json(work / target.name, lock)
    save_json(target, lock)


def bound(work):
    local = whole_iq.checked(work / "source-lock.json", _sha(REPORT / "source-lock.json"))
    lock = whole_iq.read(local)
    for name, digest in (lock["files"] | lock["programs"]).items():
        whole_iq.checked(ROOT / name, digest)
    for spec in lock["detectors"].values():
        whole_iq.checked(Path(spec["path"]), spec["sha256"])
    whole_iq.checked(work / "release/raw-release.json", lock["raw_release_sha256"])
    return lock


def context(lock):
    return patch.multiple(
        runtime,
        MODULE=MODULE,
        HINTED_SHA256=lock["detectors"]["candidate"]["sha256"],
        differential_runtime_raw=multilag_whole_raw,
        source_identity=lambda: lock["programs"],
    )


def run(work):
    lock = bound(work)
    with context(lock):
        for ident in CORES:
            dest = work / ident
            if (dest / "candidate/service.json").is_file() or (
                dest / "candidate-failure.json"
            ).is_file():
                continue
            whole_center_union.service(work, ident, "candidate", lock, evaluator=runtime.evaluate)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("freeze", "run", "worker", "position"))
    p.add_argument("attempt", type=local_output, nargs="?")
    p.add_argument("--work", type=local_output, default=WORK)
    args = p.parse_args()
    if args.stage == "freeze":
        freeze(args.work)
    elif args.stage == "run":
        run(args.work)
    elif args.stage == "worker":
        with context(bound(args.attempt.parents[1])):
            runtime.worker(args.attempt)
    else:
        whole_iq.position(args.attempt)
