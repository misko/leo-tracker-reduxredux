"""Freeze two held FFTW acquisitions and launch only their two complete services."""

import argparse
import shutil
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import differential_runtime as numpy_runtime
from . import frontier_whole_replay as prior
from . import whole_fftw_raw, whole_fftw_runtime
from .full_v5_check import _sha

REPORT = prior.REPORT.with_name("whole-fftw")
QUALIFIED = prior.REPORT.with_name("differential-runtime")
WORK = Path("/var/tmp/leo-frontier-fftw-20261119")
CASES = {"DS26-0168": [0, 1], "DS29-0604": [8, 9]}
METHOD = "frontier_whole_fftw"


def qualified():
    seal = whole_iq.read(QUALIFIED / "prediction-lock.json")
    for name in ("plan.json", "summary.json", "paired.json.gz"):
        whole_iq.checked(QUALIFIED / name, seal["files"][name])
    for name, digest in seal["sources"].items():
        whole_iq.checked(ROOT / name, digest)
    grades = whole_iq.read(QUALIFIED / "summary.json")["cohorts"]
    if any(
        grades[name]["windows"] != count
        or grades[name]["canonical_native_payloads"] != count
        or grades[name]["complete_rank_lanes"] != 2 * count
        for name, count in (("primary", 24), ("confirmation", 8), ("synthetic", 14))
    ):
        raise ValueError("FFTW scorer did not reproduce the prespecified held and plant payloads")
    lib = whole_iq.read(QUALIFIED / "plan.json")["libraries"]
    for name, pinned in (
        ("fftw", whole_fftw_raw.SCOUT_SHA256),
        ("hinted", numpy_runtime.HINTED_SHA256),
    ):
        if lib[name]["sha256"] != pinned:
            raise ValueError("qualified scout or hinted library identity differs")
        whole_iq.checked(Path(lib[name]["path"]), pinned)
    return lib


def freeze(work):
    source_path = prior.REPORT / "prospective-lock.json"
    source = whole_iq.read(source_path)
    activation_path = prior.REPORT / "experiment.json"
    active = whole_iq.read(activation_path)
    if (
        set(source["cases"]) != set(CASES)
        or active["activation"]["policy"] != "unprivileged-differential"
        or active["activation"]["prospective_lock_sha256"] != _sha(source_path)
        or active["candidate"]["sha256"] != numpy_runtime.HINTED_SHA256
        or source["memory_max"] != whole_iq.MEMORY
        or (source["limit_s"], source["swap_max"]) != (450, 0)
    ):
        raise ValueError("FFTW requires the independently frozen NumPy/stock recording pair")
    selection = prior.REPORT / "selection.json"
    whole_iq.checked(selection, source["spec"]["selection_sha256"])
    assets = qualified()
    if work.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("use writable local scratch")
    work.mkdir(parents=True, exist_ok=False)
    target = work / "runtime"
    target.mkdir()
    libraries = dict(
        hinted=str(target / "libleo-adaptive-detector.so"),
        fftw=str(target / whole_fftw_raw.SCOUT_NAME),
    )
    for name, path in libraries.items():
        shutil.copyfile(assets[name]["path"], path)
        whole_iq.checked(Path(path), assets[name]["sha256"])
    cases = {
        ident: dict(source["cases"][ident], cpus=cpus, first="candidate")
        for ident, cpus in CASES.items()
    }
    programs = whole_fftw_runtime.source_identity() | {
        str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__)),
    }
    pins = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (
            source_path,
            activation_path,
            selection,
            REPORT / "PROTOCOL.md",
            QUALIFIED / "prediction-lock.json",
        )
    }
    lock = dict(
        cases=cases,
        programs=programs,
        inputs=pins,
        receiver=source["receiver"],
        receiver_files=source["receiver_files"],
        native_sources=source["native_sources"],
        limit_s=source["limit_s"],
        memory_max=source["memory_max"],
        swap_max=0,
        detectors={
            "candidate": dict(path=libraries["hinted"], sha256=numpy_runtime.HINTED_SHA256),
            "scout": dict(path=libraries["fftw"], sha256=whole_fftw_raw.SCOUT_SHA256),
        },
    )
    save_json(work / "source-lock.json", lock)
    save_json(REPORT / "source-lock.json", lock)


def binding(work):
    lock = whole_iq.read(
        whole_iq.checked(work / "source-lock.json", _sha(REPORT / "source-lock.json"))
    )
    for name, digest in (lock["inputs"] | lock["programs"]).items():
        whole_iq.checked(ROOT / name, digest)
    for asset in lock["detectors"].values():
        whole_iq.checked(Path(asset["path"]), asset["sha256"])
    return lock


def run(work, ident):
    lock = binding(work)
    plan = lock["cases"][ident]
    current, _ = whole_iq.binding(ident)
    receiver = Path(lock["receiver"])
    if (
        current["recording"] != plan["recording"]
        or current["request"]["sha256"] != plan["request_sha256"]
        or whole_iq.receiver_identity(receiver) != lock["receiver_files"]
        or whole_iq.native_sources(receiver) != lock["native_sources"]
    ):
        raise ValueError("installed reader or scientific source differs from the frozen controls")
    folder = work / ident
    folder.mkdir(exist_ok=False)
    attempt = folder / "candidate"
    detector = lock["detectors"]["candidate"]
    try:
        whole_fftw_runtime.evaluate(
            ident,
            Path(detector["path"]),
            detector["sha256"],
            receiver,
            attempt,
            plan["cpus"],
            lock["limit_s"],
        )
    except (FileExistsError, iq_service.UnsettledService):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        if (attempt / "service.log").exists() and not (attempt / "service.json").exists():
            raise iq_service.UnsettledService(
                f"terminal state unconfirmed for {attempt}"
            ) from error
        save_json(folder / "candidate-failure.json", dict(error=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", *CASES))
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.work)
    else:
        run(args.work, args.command)


if __name__ == "__main__":
    main()
