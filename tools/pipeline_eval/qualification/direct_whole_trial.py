"""Bind a full prepared-fractional raw replay to the slim direct position entry."""

import argparse
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ..variants import v5_direct_whole as position
from . import direct_cavity_trial as direct
from . import recording_to_v5 as recording
from . import whole_cavity_worker as old_position
from . import whole_fractional as prior
from . import whole_fractional_worker as fractional
from . import whole_memory_chain as service
from . import whole_memory_chain_worker as raw
from .full_v5_check import _load_case

IDENT = "DS29-0082"
METHOD = "v5_direct_whole"
BOUNDARY = "Complete saved IQ through prepared fractional GLRT and standalone compact v5 cavity"
MODULE = "tools.pipeline_eval.qualification.direct_whole_trial"
PAIRED = Path("/srv/bulk/leo-dev/cavity-trim-hZWtOlK5/paired")
SLIM = PAIRED / "small"
REPORT = direct.common.SCREEN / "next/direct-whole"
TMP = Path("/srv/bulk/leo-dev/dw-tmp")
CHAIN = SimpleNamespace(__name__=MODULE, CPUS=(18, 19), MEMORY=512 * 1024**2, LIMIT=300)


def plan():
    published = prior.REPORT / "source-lock.json"
    earlier = prior.plan()
    if earlier != direct.common.read(published):
        raise ValueError("raw prepared replay inputs or source changed")
    archived = service.sealed(prior.REPORT, "positions.jsonl.gz")
    candidate = direct.read_predictions(archived)[IDENT]
    if candidate["result"]["status"] != "ok":
        raise ValueError("earlier prepared factor digest lacks a completed control")
    packaged_lock = PAIRED / "plan.json"
    packaged = direct.common.read(packaged_lock)
    slim = packaged["packages"]["small"]
    files = {
        **slim["files"],
        **slim["binaries"],
        "native/manifest.json": slim["native_manifest_sha256"],
    }
    if slim["count"] != 78 or any(direct.common.sha(SLIM / k) != v for k, v in files.items()):
        raise ValueError("slim release differs from the staged, paired source lock")
    key = "ordinary-" + IDENT
    _, _, binding = direct.input_case(key)
    direct.common.require_fields(packaged["bindings"][key], binding)
    paths = (
        Path(__file__).resolve(),
        Path(position.__file__).resolve(),
        REPORT / "PROTOCOL.md",
        published,
        prior.REPORT / "prediction-lock.json",
        packaged_lock,
    )
    return dict(
        case=IDENT,
        inputs={IDENT: earlier["inputs"][IDENT]},
        binding=binding,
        slim=slim,
        sources={str(p): direct.common.sha(p) for p in paths},
        prepared_native_sha256=candidate["native_sha256"],
        ordinary_native_sha256=candidate["origin_native_sha256"],
        cpus=list(CHAIN.CPUS),
        position_cpu=18,
        memory=CHAIN.MEMORY,
        swap=0,
        service_limit_s=CHAIN.LIMIT,
        nice=10,
        scratch=str(TMP),
    )


def position_flags(out, job, candidate_sha):
    record = job["native_input"]
    native = out / "native.json"
    if (
        job["evaluation_reference"] is not None
        or record["path"] != str(native)
        or record["sha256"].removeprefix("sha256:") != candidate_sha
        or direct.common.sha(native) != candidate_sha
    ):
        raise ValueError("fresh factors do not reproduce the exact declared prepared input")
    return position.explicit_arguments(
        native=native,
        native_sha256=candidate_sha,
        track_config=job["track_config"]["path"],
        config_sha256=job["track_config"]["sha256"],
        session=job["identity"]["session_id"],
        archive=job["tle_root"],
        native_backend=SLIM / "native/manifest.json",
        library=SLIM / "projector.so",
        tile=job["search_center"],
        screen_center=job["screen_center"],
    )


def assemble(out, ident, deadline, detector):
    saved_exec = os.execve
    experiment = direct.common.read(out.parent / "plan.json")

    def handoff(exe, command, _env):
        if (
            len(command) != 6
            or Path(command[2]) != Path(old_position.__file__)
            or command[3] != "position"
            or Path(command[4]) != out
        ):
            raise ValueError("unknown prepared replay handoff")
        dest = out / "position"
        job = direct.common.read(dest / "request.json")["job"]
        flags = position_flags(out, job, experiment["prepared_native_sha256"])
        cmd = [
            exe,
            "-B",
            str(Path(position.__file__)),
            str(SLIM),
            str(dest / "result.json"),
            str(out / "position-stages.json"),
            str(CHAIN.CPUS[0]),
            *flags,
        ]
        os.sched_setaffinity(0, {CHAIN.CPUS[0]})
        os.chdir(SLIM)
        env = dict(direct.command_env(SLIM), TMPDIR=str(TMP))
        saved_exec(exe, cmd, env)

    with patch.object(os, "execve", handoff):
        fractional.assemble(out, ident, deadline, detector)


def work_chain(out):
    os.environ["TMPDIR"] = str(TMP)
    recording.save(out.parent / f"{IDENT}-begin.json", dict(start=raw.mark("raw enter"), id=IDENT))
    with patch.object(recording, "MODULE", fractional.__name__):
        recording.run_recording(
            IDENT,
            out,
            CHAIN.CPUS,
            CHAIN.LIMIT,
            native_library=fractional.LIBRARY,
            finish=assemble,
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "run", "chain"))
    p.add_argument("path", type=Path)
    p.add_argument("worker_output", nargs="?", type=Path)
    args = p.parse_args()
    if args.action == "chain":
        if str(args.path) != IDENT:
            raise ValueError("only the sealed recording was scheduled")
        work_chain(args.worker_output)
    else:
        runs = direct.local_output(args.path)
        if args.action == "seal":
            if not TMP.is_dir():
                raise ValueError("dedicated disk scratch directory is required")
            # Read the manifest inventory and capture source before sealing the numerical run.
            recording.capture_release.read_capture(_load_case(IDENT))
            pins = plan()
            runs.mkdir(parents=True, exist_ok=False)
            direct.save_json(runs / "plan.json", pins)
        else:
            with patch.multiple(service, plan=plan, chain=CHAIN):
                service.run(IDENT, runs)


if __name__ == "__main__":
    main()
