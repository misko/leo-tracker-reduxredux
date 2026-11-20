"""Run counterbalanced full-IQ comparisons of two native short-window frequency spans."""

import argparse
from pathlib import Path
from time import time

from .. import cavity_runtime, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import raw_robust
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/whole-band"
BUILD = Path("/srv/bulk/leo-dev/20261119-wide-regional")
BINARIES = {
    "narrow": ("control", "e545c28554c9db50fe5aece28e7c8ce6ab2b2504db13ab946fbff0f0a190fe0d"),
    "wide": ("wide", "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"),
}
SCHEDULE = {
    "DS26-0036": ([0, 1], ["narrow", "wide"], "development"),
    "DS29-0082": ([18, 19], ["wide", "narrow"], "development"),
    "DS26-0237": ([20, 21], ["wide", "narrow"], "previous confirmation"),
    "DS29-0174": ([22, 23], ["narrow", "wide"], "previous confirmation"),
    "DS26-0122": ([18, 19], ["narrow", "wide"], "additional reserve"),
    "DS29-0247": ([0, 1], ["wide", "narrow"], "additional reserve"),
}


def lock(work, build):
    receipts = whole_iq.read(raw_robust.ORDINARY_RECEIPT)["recordings"]
    if set(receipts) != set(SCHEDULE):
        raise ValueError("the roster must include the six existing complete ordinary controls")
    detectors = {}
    for name, (folder, digest) in BINARIES.items():
        library = whole_iq.checked(build / folder / "libleo-adaptive-detector.so", digest)
        detectors[name] = dict(path=str(library), sha256=digest)
    cases = {}
    for ident, (cpus, order, cohort) in SCHEDULE.items():
        case, request = whole_iq.binding(ident)
        strict = raw_robust.prior_directory(ident) / "native.json"
        expected = receipts[ident]
        whole_iq.checked(strict, expected["native_sha256"])
        cases[ident] = dict(
            cpus=cpus,
            order=order,
            cohort=cohort,
            ordinary_sha256=expected["native_sha256"],
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            tile=case["regions"][0],
            catalog_sha256=case["catalog"]["sha256"],
            clock_authority=expected["input_manifest_sha256"],
            history=request["causal_snapshots"],
            recording=case["recording"],
        )
    pin = [
        Path(__file__),
        Path(whole_iq.__file__),
        Path(cavity_runtime.__file__),
        Path(cavity_runtime.__file__).with_name("cavity_entry.py"),
        REPORT / "PROTOCOL.md",
        Path(whole_iq.recording.__file__),
        Path(whole_iq.raw.__file__),
        cavity_runtime.RELEASE / "prediction-lock.json",
        raw_robust.ORDINARY_RECEIPT,
    ]
    release = cavity_runtime.install(work / "receiver")
    return dict(
        cases=cases,
        detectors=detectors,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=360,
        receiver_files=whole_iq.receiver_identity(release),
        sources={str(p.relative_to(ROOT)): _sha(p) for p in pin},
    )


def run(work, ident):
    whole_iq.checked(work / "study.json", (work / "study.sha256").read_text().strip())
    pins = whole_iq.read(work / "study.json")
    case = pins["cases"][ident]
    for name, digest in pins["sources"].items():
        whole_iq.checked(ROOT / name, digest)
    receiver = work / "receiver"
    if whole_iq.receiver_identity(receiver) != pins["receiver_files"]:
        raise ValueError("standalone receiver differs from the study release")
    (work / ident).mkdir(exist_ok=False)
    for arm in case["order"]:
        detector = pins["detectors"][arm]
        attempt = work / ident / arm
        try:
            whole_iq.evaluate(
                ident,
                Path(detector["path"]),
                detector["sha256"],
                receiver,
                attempt,
                case["cpus"],
                pins["limit_s"],
            )
        except (OSError, RuntimeError, ValueError) as error:
            save_json(
                work / ident / f"{arm}-failure.json", dict(error=str(error), time_unix_s=time())
            )
            print(ident, arm, "failed", error, flush=True)
        else:
            print(ident, arm, "complete", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "run"))
    p.add_argument("work", type=local_output)
    p.add_argument("--build", type=Path, default=BUILD)
    p.add_argument("--case", choices=SCHEDULE)
    args = p.parse_args()
    if args.action == "seal":
        pins = lock(args.work, args.build.resolve())
        save_json(args.work / "study.json", pins)
        (args.work / "study.sha256").write_text(_sha(args.work / "study.json") + "\n")
    elif args.case:
        run(args.work, args.case)
    else:
        p.error("run requires --case")
