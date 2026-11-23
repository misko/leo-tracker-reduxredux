"""Build and measure the fixed 8 ms primary against the full-coverage 12 ms rule."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import resource
from time import perf_counter_ns

from . import mixed_aperture_trial, short_signed_trial
from .scout_readout_trial import check_machine


SHAPES = {"12ms": (120_000, 8), "8ms": (80_000, 5)}
HERE = Path(__file__).resolve().parent


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def checked_shape(samples, frames):
    geometry = short_signed_trial.geometry(samples, frames)
    if samples % 4 or frames < 4 or any(v > samples for key, v in geometry.items() if key.startswith("first_unused")):
        raise ValueError("The aperture lacks complete native refinement and confirmation support")
    return geometry


def build(archive, output, installed, assets):
    host = check_machine()
    geometries = {arm: checked_shape(*shape) for arm, shape in SHAPES.items()}
    output.mkdir(exist_ok=False)
    started = perf_counter_ns()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    scout = short_signed_trial.build(archive, output / "scouts", installed, assets, apertures=SHAPES)
    primary = {}
    for arm, source in scout["arms"].items():
        path = output / arm
        mixed_aperture_trial.build(archive, path, short=source)
        primary[arm] = json.loads((path / "build-receipt.json").read_bytes())
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    scope = dict(elapsed_ns=perf_counter_ns()-started, child_user_cpu_s=after.ru_utime-before.ru_utime,
                 child_system_cpu_s=after.ru_stime-before.ru_stime)
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "eight-ms-primary-protocol.md", "short_signed_trial.py", "mixed_aperture_trial.py", "short_primary_entry.inc")}
    write(output / "build.json", dict(machine=host, geometry=geometries, clocks=scope, scout=scout,
                                     primary=primary, source_sha256=pins))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "output", "installed", "assets"):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
