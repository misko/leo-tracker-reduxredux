"""Publish the reviewed ordinary Gamma kernel on the fixed saved short offers."""

import argparse
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter

from aperture_trial import archive_identity, read, write
from cold_track_row_transfer import GEOGRAPHIC, dense_inputs
from dense_geographic_trial import host
from proof_rank_short_transfer import saved, saved_far
from profiled_gamma_live import digest


HERE = Path(__file__).resolve().parent
LIBRARY = Path("/var/tmp/leo-structural-gamma-v2.so")
SMALL = ("physical", "south-far", "south-inside")


def verified_inputs(case):
    from full_short_graph_transfer import inputs as graph_inputs
    from leo.contracts.algo08_region import Algo08Region

    if case == "dense":
        row, _ = dense_inputs(GEOGRAPHIC)
    else:
        if case == "south-far":
            saved_far()
        else:
            saved(case)
        row = graph_inputs(case)
    _, archive, region, native, native_pin, offer = row
    if (digest(native) != native_pin.removeprefix("sha256:") or Algo08Region.parse(read(region)).document() != offer
            or archive_identity(Path(archive["root"])) != archive):
        raise ValueError("The original saved detector, offer or causal archive changed")
    return row


def usage():
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return children.ru_utime + children.ru_stime


def invoke(case, root, mode, chosen, library):
    recording, archive, region, packet, pin, offer = chosen
    names = dict(recording=recording, archive=archive["root"], region=region, output=root / mode, saved=packet,
                 saved_digest=pin, geographic_library=GEOGRAPHIC, track_graph="installed")
    values = [item for name, value in names.items() for item in ("--"+name.replace("_", "-"), str(value))]
    if mode == "profiled":
        values.extend(("--profiled-gamma-library", str(library)))
    env = dict(os.environ)
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    start, before = perf_counter(), usage()
    command = [sys.executable, "-BPs", str(HERE / "full_short_run.py"), *values]
    try:
        child = subprocess.run(command, env=env, capture_output=True, text=True, timeout=85)
    except subprocess.TimeoutExpired:
        status, error = "timeout", "85 second publication limit expired"
    else:
        status, error = child.returncode, child.stderr[-6000:]
    write(root / f"{mode}-process.json", dict(cpu_s=usage()-before, elapsed_s=perf_counter()-start, status=status,
              error=error, command=command, case=case, native_sha256=pin, archive=archive, offer=offer))


def run(case, output, library, screen):
    current = host()
    if case == "dense":
        if screen is None or not all(read(screen / f"{case}-gate.json")["passed"] for case in SMALL):
            raise ValueError("All three small paired publications must pass before the single dense launch")
    chosen = verified_inputs(case)
    output.mkdir(exist_ok=False)
    order = ("profiled",) if case == "dense" else (("profiled", "control") if case == "south-far" else ("control", "profiled"))
    write(output / "binding.json", dict(case=case, order=list(order), host=current, one_solve_per_mode=True,
          library_sha256=digest(library), protocol_sha256=digest(HERE / "profiled-gamma-live-protocol.md")))
    for mode in order:
        invoke(case, output, mode, chosen, library)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=(*SMALL, "dense"))
    cli.add_argument("output", type=Path)
    cli.add_argument("--library", type=Path, default=LIBRARY)
    cli.add_argument("--screen", type=Path)
    run(**vars(cli.parse_args()))
