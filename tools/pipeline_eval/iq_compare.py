"""Pair complete saved-IQ detector runs, then publish matched position distributions."""

import argparse
import fcntl
import re
from pathlib import Path

from . import iq_service, whole_iq
from .__main__ import ROOT, local_output, save_json
from .qualification import capture_release
from .qualification.full_v5_check import _sha

BRANCHES = ("control", "candidate")


def validate(spec):
    cases = spec["cases"]
    if not re.fullmatch(r"[a-z][a-z0-9-]*", spec["id"]):
        raise ValueError("choose a short, lowercase study ID")
    if not cases or len({row["id"] for row in cases}) != len(cases):
        raise ValueError("the study needs distinct recording IDs")
    if not 1 <= spec["limit_s"] <= 600:
        raise ValueError("the whole-recording deadline must be 1 to 600 seconds")
    for branch in BRANCHES:
        if not re.fullmatch(r"[0-9a-f]{64}", spec[branch]["sha256"]) or not spec[branch]["label"]:
            raise ValueError("each detector needs a SHA-256 and a display name")
    for row in cases:
        if (
            not re.fullmatch(r"DS\d+-\d+", row["id"])
            or len(row["cpus"]) != 2
            or len(set(row["cpus"])) != 2
            or row["first"] not in BRANCHES
            or not row["cohort"]
        ):
            raise ValueError("each recording needs two distinct cores, a cohort and a branch order")
    panels = spec.get("additional_panels", [])
    ids = [p["id"] for p in panels]
    if len(set(ids)) != len(ids) or any(
        not re.fullmatch(r"[a-z][a-z0-9-]*", p["id"])
        or p["id"] == "all"
        or p["cohort"] not in {r["cohort"] for r in cases}
        for p in panels
    ):
        raise ValueError("each additional chart needs a unique ID and a populated cohort")


def prepare(spec_path, protocol, receiver, libraries, work):
    spec = whole_iq.read(spec_path)
    validate(spec)
    receiver = receiver.resolve()
    detectors = {}
    for branch in BRANCHES:
        library = whole_iq.checked(libraries[branch].resolve(), spec[branch]["sha256"])
        detectors[branch] = dict(spec[branch], path=str(library))
    cases = {}
    for row in spec["cases"]:
        ident = row["id"]
        case, request = whole_iq.binding(ident)
        capture = capture_release.read_capture(case)
        cases[ident] = dict(
            row,
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            tile=case["regions"][0],
            recording=case["recording"],
            clock_authority=capture["input_manifest_sha256"],
            orbit_snapshots=request["causal_snapshots"],
        )
    programs = [
        Path(__file__),
        Path(iq_service.__file__),
        Path(whole_iq.__file__),
        Path(whole_iq.recording.__file__),
        Path(whole_iq.raw.__file__),
        Path(capture_release.__file__),
    ]
    lock = dict(
        spec=spec,
        spec_sha256=_sha(spec_path),
        protocol_sha256=_sha(protocol),
        cases=cases,
        detectors=detectors,
        receiver=str(receiver),
        receiver_files=whole_iq.receiver_identity(receiver),
        native_sources=whole_iq.native_sources(receiver),
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=spec["limit_s"],
        programs={str(path.relative_to(ROOT)): _sha(path) for path in programs},
    )
    work.mkdir(parents=True, exist_ok=False)
    save_json(work / "source-lock.json", lock)
    (work / "source-lock.sha256").write_text(_sha(work / "source-lock.json") + "\n")


def run(work, ident):
    sealed = whole_iq.checked(
        work / "source-lock.json", (work / "source-lock.sha256").read_text().strip()
    )
    lock = whole_iq.read(sealed)
    if ident not in lock["cases"]:
        raise ValueError("recording is outside the frozen case roster")
    for name, digest in lock["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    receiver = Path(lock["receiver"])
    if (
        whole_iq.receiver_identity(receiver) != lock["receiver_files"]
        or whole_iq.native_sources(receiver) != lock["native_sources"]
    ):
        raise ValueError("installed receiver differs from the study")
    case, _ = whole_iq.binding(ident)
    planned = lock["cases"][ident]
    if (
        case["request"]["sha256"] != planned["request_sha256"]
        or case["recording"] != planned["recording"]
    ):
        raise ValueError("recording or position request changed since the study was frozen")
    folder = work / ident
    folder.mkdir(exist_ok=True)
    with (folder / ".run.lock").open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise iq_service.UnsettledService(f"another supervisor owns {ident}") from error
        run_branches(lock, ident, folder)


def run_branches(lock, ident, folder):
    planned = lock["cases"][ident]
    first = planned["first"]
    for branch in (first, next(b for b in BRANCHES if b != first)):
        attempt = folder / branch
        failure = folder / (branch + "-failure.json")
        terminal = attempt / "service.json"
        if failure.is_file():
            continue
        if attempt.exists():
            if terminal.is_file():
                previous = whole_iq.read(terminal)
            elif (attempt / "service.log").is_file():
                previous = iq_service.reconcile(attempt)
            else:
                raise iq_service.UnsettledService(f"no service log available for {attempt}")
            if not iq_service.succeeded(previous) or not (attempt / "end.json").is_file():
                save_json(failure, dict(error=f"saved-IQ service did not complete; see {terminal}"))
            continue
        detector = lock["detectors"][branch]
        try:
            whole_iq.evaluate(
                ident,
                Path(detector["path"]),
                detector["sha256"],
                Path(lock["receiver"]),
                attempt,
                planned["cpus"],
                lock["limit_s"],
            )
        except (FileExistsError, iq_service.UnsettledService):
            raise
        except (RuntimeError, ValueError, OSError) as error:
            if (attempt / "service.log").exists() and not terminal.exists():
                raise iq_service.UnsettledService(
                    f"terminal state unconfirmed for {attempt}"
                ) from error
            save_json(failure, dict(error=str(error)))
        print(ident, branch, "failed" if failure.is_file() else "completed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    bind = commands.add_parser("prepare", help="freeze waveform, receiver and detector identities")
    bind.add_argument("--spec", required=True, type=Path)
    bind.add_argument("--protocol", required=True, type=Path)
    bind.add_argument("--receiver", required=True, type=Path)
    for branch in BRANCHES:
        bind.add_argument("--" + branch, type=Path, required=True)
    execute = commands.add_parser("run", help="run both detectors on one recorded waveform")
    execute.add_argument("--case", required=True)
    for name in ("seal", "publish"):
        command = commands.add_parser(
            name,
            help=("freeze predictions" if name == "seal" else "score and render a sealed study"),
        )
        command.add_argument("--out", type=local_output, required=True)
        if name == "seal":
            command.add_argument("--keep-factors", action="store_true")
    for command in (bind, execute, commands.choices["seal"]):
        command.add_argument("--work", required=True, type=local_output)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(
            args.spec,
            args.protocol,
            args.receiver,
            {b: getattr(args, b) for b in BRANCHES},
            args.work,
        )
    elif args.action == "run":
        run(args.work, args.case)
    else:
        from . import iq_comparison_results

        if args.action == "seal":
            iq_comparison_results.seal(args.work, args.out, keep_factors=args.keep_factors)
        else:
            iq_comparison_results.publish(args.out)


if __name__ == "__main__":
    main()
