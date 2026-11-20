"""Freeze and independently draw the development-calibrated transfer cohort."""

from pathlib import Path
from unittest.mock import patch

from ..variants import tile_region_empirical, tile_region_support
from . import tile_region_support_trials as trials

OUT = trials.OUT / "development-noise"
WORKER = Path(__file__).with_name("tile_region_empirical_worker.py")


def source():
    paths = (
        Path(__file__),
        WORKER,
        Path(trials.__file__),
        Path(tile_region_support.__file__),
        Path(tile_region_empirical.__file__),
        Path(trials.portable_gate_coverage.__file__),
    )
    return dict(prior=trials.prior.lock(), files={p.name: trials.prior.checksum(p) for p in paths})


if __name__ == "__main__":
    command = trials.prior.worker_command

    def with_reference(cpu, items, library, worker, modules):
        return command(cpu, items, library, worker, (*modules, tile_region_support))

    with (
        patch.object(trials, "OUT", OUT),
        patch.object(trials, "WORKER", WORKER),
        patch.object(trials, "METHOD", tile_region_empirical.METHOD),
        patch.object(trials, "tile_region_support", tile_region_empirical),
        patch.object(trials, "source", source),
        patch.object(trials.prior, "worker_command", with_reference),
    ):
        trials.main()
