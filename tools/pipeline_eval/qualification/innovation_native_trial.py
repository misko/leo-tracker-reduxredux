"""Measure the compiled scalar filter on paired, complete GLRT receiver jobs."""

import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ..variants import innovation_native
from . import innovation_noise_trial as pair

REPORT = pair.REPORT.with_name("compiled-noise")
METHOD = "native_compiled_innovation"
WORKER = Path(__file__).with_name("innovation_native_worker.py")
PARENT_WORKER = pair.WORKER
MODULE = Path(innovation_native.__file__)
C_FILE = MODULE.with_name("innovation_filter.c")
first_roster = pair.choose


def build(path):
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-ffp-contract=off",
            "-fPIC",
            "-shared",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(C_FILE),
            "-o",
            str(path),
        ],
        check=True,
    )


def choose(jobs):
    selected = first_roster(jobs)
    used = {q["id"] for q, _ in selected}
    remaining = sorted(
        (entry for entry in jobs if entry[0]["cohort"] == "roof" and entry[0]["id"] not in used),
        key=lambda entry: pair.phase.corpus._sha(
            ("compiled-innovation-20261119/" + entry[0]["id"]).encode()
        ),
    )
    for ds, n in (("DS26", 4), ("DS29", 2)):
        selected.extend([entry for entry in remaining if entry[0]["id"].startswith(ds + "-")][:n])
    if len(selected) != 21:
        raise ValueError("expected 15 prior and six new requests")
    return selected


def run(work, output, bundle):
    with TemporaryDirectory(prefix="leo-filter-library-") as tmp:
        library = Path(tmp) / "innovation.so"
        build(library)
        bindings = (
            (PARENT_WORKER, "/worker/innovation_parent.py"),
            (
                Path(pair.innovation_noise.__file__),
                "/worker/tools/pipeline_eval/variants/innovation_noise.py",
            ),
            (MODULE, "/worker/tools/pipeline_eval/variants/innovation_native.py"),
            (library, "/worker/innovation.so"),
        )

        def command(cpu, paths, bundle):
            argv = pair.stock_command(cpu, paths, bundle)
            argv[argv.index(str(pair.base.WORKER))] = str(WORKER)
            for path, target in bindings:
                argv[-3:-3] = ["--ro-bind", str(path), target]
            return argv

        def sources(bundle):
            return dict(
                native=pair.base.sources(bundle),
                numerical={target: pair.phase.digest(path) for path, target in bindings},
                kernel=pair.phase.digest(C_FILE),
                worker=pair.phase.digest(WORKER),
                runner=pair.phase.digest(Path(__file__)),
                paired_supervisor=pair.phase.digest(Path(pair.__file__)),
                protocol=pair.phase.digest(REPORT / "PROTOCOL.md"),
                reference=pair.phase.digest(pair.panel.REPORT / "prediction-lock.json"),
            )

        with patch.multiple(
            pair,
            CPU=4,
            METHOD=METHOD,
            REPORT=REPORT,
            choose=choose,
            command=command,
            source=sources,
        ):
            pair.run(work, output, bundle)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--output", type=Path, default=REPORT)
    cli.add_argument("--bundle", type=Path, default=pair.base.BUNDLE)
    args = cli.parse_args()
    run(args.work, args.output, args.bundle)
