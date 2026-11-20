"""Seal and execute paired complete wide-IQ handoff measurements."""

import argparse
import gzip
import shutil
from hashlib import file_digest
from pathlib import Path
from time import time_ns

from .. import cavity_runtime, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import whole_band_trial, winner_stream_trial

REPORT = winner_stream_trial.SCREEN / "receiver-core/whole-winner"
SCHEDULE = {
    "DS29-0082": ("stock", "private"),
    "DS26-0122": ("private", "stock"),
}
CPUS = (3, 5)
LIMIT = 286


def lock(root):
    root.mkdir(exist_ok=False)
    donor = winner_stream_trial.WIDE
    previous = whole_iq.read(donor / "prediction-lock.json")
    source = whole_iq.read(
        whole_iq.checked(donor / "source-lock.json", previous["files"]["source-lock.json"])
    )
    arms = {}
    for ident, order in SCHEDULE.items():
        case, _ = whole_iq.binding(ident)
        old = source["cases"][ident]
        for key, expected in (
            ("capture_native_sha256", case["native"]["sha256"]),
            ("catalog_sha256", case["catalog"]["sha256"]),
            ("request_sha256", case["request"]["sha256"]),
        ):
            if old[key] != expected:
                raise ValueError("the full wide-IQ authority has changed")
        with gzip.open(
            whole_iq.checked(
                donor / f"native/{ident}.json.gz", previous["files"][f"native/{ident}.json.gz"]
            ),
            "rb",
        ) as raw:
            native = file_digest(raw, "sha256").hexdigest()
        arms[ident] = dict(
            order=order,
            tile=case["regions"][0],
            catalog_sha256=old["catalog_sha256"],
            capture_native_sha256=old["capture_native_sha256"],
            native_sha256=native,
            frozen_request_sha256=old["request_sha256"],
            recording=case["recording"],
        )
    detector_dir, digest = whole_band_trial.BINARIES["wide"]
    detector = whole_iq.checked(
        whole_band_trial.BUILD / detector_dir / "libleo-adaptive-detector.so", digest
    )
    # Keep the measured detector under the same local filesystem as the service scratch.
    local_detector = root / detector.name
    shutil.copyfile(detector, local_detector)
    whole_iq.checked(local_detector, digest)
    receiver = cavity_runtime.install(root / "stock", profile="phase-release")
    candidate = root / "private"
    winner_stream_trial.install(candidate, True)
    paths = (
        Path(__file__),
        Path(__file__).with_name("whole_winner.py"),
        Path(__file__).with_name("whole_winner_handoff.py"),
        Path(whole_iq.__file__),
        Path(cavity_runtime.__file__),
        Path(whole_iq.iq_service.__file__),
        Path(whole_iq.recording.__file__),
        Path(whole_iq.raw.__file__),
        REPORT / "PROTOCOL.md",
    )
    save_json(
        root / "study.json",
        dict(
            cases=arms,
            cpu_pins=CPUS,
            memory=whole_iq.MEMORY,
            swap=0,
            limit_s=LIMIT,
            nice=10,
            frozen_at_ns=time_ns(),
            whole_band_lock_sha256=whole_iq._sha(donor / "prediction-lock.json"),
            bindings={
                name: whole_iq.receiver_identity(path)
                for name, path in (("stock", receiver), ("private", candidate))
            },
            detector=local_detector.name,
            detector_sha256=digest,
            sources={str(p.relative_to(ROOT)): whole_iq._sha(p) for p in paths},
        ),
    )
    (root / "study.sha256").write_text(whole_iq._sha(root / "study.json") + "\n")


def attempt(root, ident, role):
    study = whole_iq.read(
        whole_iq.checked(root / "study.json", (root / "study.sha256").read_text().strip())
    )
    for path, digest in study["sources"].items():
        whole_iq.checked(ROOT / path, digest)
    receiver = root / role
    if whole_iq.receiver_identity(receiver) != study["bindings"][role]:
        raise ValueError("receiver differs from the frozen phase-release package")
    out = root / "attempts" / ident / role
    parameters = (
        ident,
        root / study["detector"],
        study["detector_sha256"],
        receiver,
        out,
        study["cpu_pins"],
        study["limit_s"],
    )
    try:
        if role == "stock":
            whole_iq.evaluate(*parameters)
        else:
            from . import whole_winner

            whole_winner.evaluate(
                *parameters, expected_native=study["cases"][ident]["native_sha256"]
            )
    except (OSError, ValueError, RuntimeError) as error:
        out.parent.mkdir(exist_ok=True, parents=True)
        save_json(out.with_name(role + "-failure.json"), {"error": str(error)})
        print(ident, role, str(error), flush=True)
    else:
        print(ident, role, "complete", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "run"))
    p.add_argument("work", type=local_output)
    p.add_argument("--case", choices=SCHEDULE)
    p.add_argument("--role", choices=("stock", "private"))
    args = p.parse_args()
    if args.action == "seal":
        lock(args.work)
    elif args.case and args.role:
        attempt(args.work, args.case, args.role)
    else:
        for ident, order in SCHEDULE.items():
            for role in order:
                attempt(args.work, ident, role)


if __name__ == "__main__":
    main()
