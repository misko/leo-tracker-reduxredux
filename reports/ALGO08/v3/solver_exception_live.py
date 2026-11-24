"""Measure in-flight orbit support on the pre-enrolled saved 0022 packet."""

import argparse
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import runpy
import shutil
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from solver_exception_0022 import GUARD, GUARD_PIN, OLD_GUARD, ROOT, digest, sources as previous_sources


PREVIOUS = Path("/dev/shm/leo-v3-solver-exception-0022-result01")
PREVIOUS_PIN = "d9e33461bbbf867d282002d4bf9b3139dec3e47f464b898aa1ff1bd6717ad4b8"


def read(path):
    return json.loads(path.read_bytes())


def sources():
    paths = (Path(__file__), HERE / "live_orbit_support.py")
    return previous_sources() | {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}


def worker(job, pin, output):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_publication import run
    from history_risk_weak_physical import deny_original
    from live_orbit_support import bind

    sys.addaudithook(deny_original)
    original = boot.load_runtime
    audit = dict(in_flight=[], original_restart=[])
    with ExitStack() as scope:
        def load():
            result = original()
            from tools import algo08_position, algo08_scan

            boot.checked(Path(algo08_position.corner_support.__wrapped__.__code__.co_filename), OLD_GUARD)
            boot.checked(GUARD, GUARD_PIN)
            repaired = runpy.run_path(str(GUARD))["corner_support"]

            @contextmanager
            def track_restart():
                with repaired() as entry:
                    audit["original_restart"].append(entry)
                    yield

            scope.enter_context(patch.object(algo08_position, "corner_support", track_restart))
            scope.enter_context(bind(algo08_position, algo08_scan, repaired, audit["in_flight"]))
            return result

        scope.enter_context(patch.object(boot, "load_runtime", load))
        try:
            run("routed", job, pin, output)
        finally:
            write(output / "live-corner.json", audit)


def launch(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    begin = boot.now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Require a fresh private tmpfs output")
    prior = json.loads(boot.checked(resident_path(PREVIOUS / "result.json"), PREVIOUS_PIN))
    job = resident_path(PREVIOUS / "job.json")
    job_pin = prior["admission"]["job_sha256"]
    if not prior["qualified_recovery"] or digest(job.read_bytes()) != job_pin:
        raise ValueError("Require the already verified historical recovery and its identical staged job")
    machine = host()
    if machine != prior["run"]["machine"] or previous_sources() != prior["admission"]["sources"]:
        raise ValueError("The historical scientific worker, configured machine or dependencies changed")
    binding = read(job)["binding"]
    _, refs = checked_catalogue(binding, read(Path(binding["request"])), TleArchiveReader, canonical_digest)
    causal = resident([ref.path for ref in refs])
    root.mkdir(mode=0o700)
    target = root / "routed"
    target.mkdir()
    (root / "tmp").mkdir()
    shutil.copytree(PREVIOUS / "fonts", root / "fonts")
    write(target / "binding.json", {"input": binding})
    cmd = ["/usr/bin/timeout", "--kill-after=2s", "100s", str(boot.RELEASE / "venv/bin/python"),
           "-IB", __file__, "worker", str(job), job_pin, str(target)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    write(root / "admission.json", dict(command=cmd, machine=machine, sources=sources(),
          previous_result_sha256=PREVIOUS_PIN, job_sha256=job_pin, resident=causal,
          planned_children=1, actual_setup=boot.clock(begin), no_waveform=True))
    write(root / "clock.json", measure(cmd, env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker"))
    cli.add_argument("path", type=Path)
    cli.add_argument("pin", nargs="?")
    cli.add_argument("output", type=Path, nargs="?")
    args = cli.parse_args()
    if args.mode == "worker":
        worker(args.path, args.pin, args.output)
    else:
        launch(args.path)
