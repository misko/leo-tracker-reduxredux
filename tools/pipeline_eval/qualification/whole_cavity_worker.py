"""Fork the saved IQ entry at the audited process replacement boundary."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.qualification import whole_memory_chain_worker as raw

MEMORY, CPUS = raw.MEMORY, raw.CPUS
LIMIT = 300
METHOD = "whole_cavity"
BOUNDARY = "Complete saved IQ through ordinary GLRT and lifetime-bounded secant cavity"


def assemble(*args):
    from tools.pipeline_eval.qualification import cavity_lifetime_worker

    replace = os.execve
    target = str(Path(cavity_lifetime_worker.__file__))

    def route(exe, command, environment):
        if len(command) != 6 or command[3] != "position" or Path(command[2]) != Path(raw.__file__):
            raise ValueError("unrecognized capped-whole-chain process replacement")
        return replace(exe, [*command[:2], str(Path(__file__)), *command[3:5], target], environment)

    with patch.object(os, "execve", route):
        raw_assemble(*args)


raw_assemble = raw.assemble


def position(out, worker_path):
    from tools.pipeline_eval.qualification import cavity_lifetime_worker
    from tools.pipeline_eval.qualification import recording_to_v5 as previous

    if Path(cavity_lifetime_worker.__file__) != worker_path:
        raise ValueError("incorrect lifetime-bounded cavity worker")
    fit = out / "position"
    start = raw.mark("position enter")
    unit = Path(start["cgroup"]).name.removesuffix(".service")
    cavity_lifetime_worker.worker(
        unit,
        CPUS[0],
        str(fit / "request.json"),
        str(fit / "result.json"),
        str(fit / "orbit_projector.so"),
        "direct",
    )
    previous.save(
        out / "position-stages.json", dict(start=start, end=raw.mark("position complete"))
    )


if __name__ == "__main__":
    if sys.argv[1] == "position":
        position(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        with patch.object(raw, "LIMIT", LIMIT), patch.object(raw, "assemble", assemble):
            raw.main()
