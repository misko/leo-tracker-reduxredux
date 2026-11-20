"""Expose the already-qualified complete row-major recovery worker to the benchmark."""

from pathlib import Path

from ..__main__ import local_output


def run(case, work_dir):
    from ..variants import orbit_projector, v5_lean

    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    script = Path(__file__).with_name("recovery_reads_worker.py")
    return v5_lean.run_bound_worker(case, directory, script, worker_args=(str(library),))
