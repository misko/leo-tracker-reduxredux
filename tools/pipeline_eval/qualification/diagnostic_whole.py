"""Freeze and run the two qualified FFTW whole-recording development diagnostics."""

import argparse
import shutil
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import capture_release, whole_fftw_raw, whole_fftw_runtime, whole_fftw_trial
from .full_v5_check import _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "acquisition-frontier/diagnostic-whole"
STOCK = SCREEN / "receiver-core/full-stride"
STOCK_PIN = "42136b7b48d910bf416772d7c7eb9e127dafb0ee5f54089c58d94820a05a9872"
QUALIFICATION_PIN = "b2f5f110e8ede61429c80eeddf44d304fd700288414679f51785e3c3be6bf202"
LIMIT_S = 450
CASES = {"DS26-0237": [16, 17], "DS29-0082": [18, 19]}
METHOD = "diagnostic_whole_fftw"
BASELINE = "diagnostic_whole_stock"


def stock_sources():
    seal = whole_iq.read(whole_iq.checked(STOCK / "prediction-lock.json", STOCK_PIN))
    frozen = whole_iq.checked(STOCK / "source-lock.json", seal["files"]["source-lock.json"])
    return seal, whole_iq.read(frozen)


def freeze(work):
    lock_file = REPORT / "source-lock.json"
    if lock_file.exists():
        raise FileExistsError(lock_file)
    seal, reference = stock_sources()
    qualification = whole_iq.checked(
        whole_fftw_trial.QUALIFIED / "prediction-lock.json", QUALIFICATION_PIN
    )
    qualified = whole_fftw_trial.qualified()
    work.mkdir(parents=True, exist_ok=False)
    runtime = work / "runtime"
    runtime.mkdir()
    assets = {}
    for role, source, name in (
        ("candidate", "hinted", "libleo-adaptive-detector.so"),
        ("scout", "fftw", whole_fftw_raw.SCOUT_NAME),
    ):
        path = runtime / name
        shutil.copyfile(qualified[source]["path"], path)
        digest = qualified[source]["sha256"]
        whole_iq.checked(path, digest)
        assets[role] = dict(path=str(path), sha256=digest)
    receiver = Path(reference["receiver"])
    if (
        whole_iq.receiver_identity(receiver) != reference["receiver_files"]
        or whole_iq.native_sources(receiver) != reference["native_sources"]
    ):
        raise ValueError("the installed candidate receiver differs from stock phase release")
    cases = {}
    for ident, cpus in CASES.items():
        frozen = reference["cases"][ident]
        actual, _ = whole_iq.binding(ident)
        capture = capture_release.read_capture(actual)
        if (
            actual["recording"] != frozen["recording"]
            or actual["request"]["sha256"] != frozen["request_sha256"]
            or capture["input_manifest_sha256"] != frozen["clock_authority"]
        ):
            raise ValueError(f"saved capture, request or clock authority changed for {ident}")
        native = f"native/control/{ident}.json.gz"
        whole_iq.checked(STOCK / native, seal["files"][native])
        cases[ident] = dict(frozen, cpus=cpus, cohort="development diagnostic")
    files = (
        qualification,
        STOCK / "prediction-lock.json",
        STOCK / "source-lock.json",
        REPORT / "PROTOCOL.md",
    )
    lock = dict(
        cases=cases,
        detectors=assets | {"control": reference["detectors"]["control"]},
        inputs={str(path.relative_to(ROOT)): _sha(path) for path in files},
        receiver=str(receiver),
        receiver_files=reference["receiver_files"],
        native_sources=reference["native_sources"],
        limit_s=LIMIT_S,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        stock_limit_s=reference["limit_s"],
        programs=whole_fftw_runtime.source_identity()
        | {str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
    )
    save_json(work / "source-lock.json", lock)
    save_json(lock_file, lock)
    print(_sha(lock_file), flush=True)


def source(work):
    fixed = REPORT / "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(work / fixed.name, _sha(fixed)))
    for name, digest in (plan["inputs"] | plan["programs"]).items():
        whole_iq.checked(ROOT / name, digest)
    return plan


def run(work, ident):
    spec = source(work)
    planned = spec["cases"][ident]
    receiver = Path(spec["receiver"])
    if (
        whole_iq.receiver_identity(receiver) != spec["receiver_files"]
        or whole_iq.native_sources(receiver) != spec["native_sources"]
    ):
        raise ValueError("phase-release installed package changed after freeze")
    for role in ("candidate", "scout"):
        artifact = spec["detectors"][role]
        whole_iq.checked(Path(artifact["path"]), artifact["sha256"])
    folder = work / ident
    folder.mkdir()
    attempt = folder / "candidate"
    detector = spec["detectors"]["candidate"]
    try:
        whole_fftw_runtime.evaluate(
            ident,
            Path(detector["path"]),
            detector["sha256"],
            receiver,
            attempt,
            planned["cpus"],
            spec["limit_s"],
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", *CASES))
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        run(args.work, args.action)
