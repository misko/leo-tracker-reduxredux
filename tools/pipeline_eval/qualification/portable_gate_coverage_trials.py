"""Run a new blind site and the historical controls with a held-support gate."""

from pathlib import Path
from unittest.mock import patch

from ..variants import portable_gate_coverage
from . import portable_gate_halo_trials as trials

REPORT = trials.primary.REPORT / "coverage"
WORKER = Path(__file__).with_name("portable_gate_coverage_worker.py")


def source():
    files = (Path(__file__), WORKER, Path(portable_gate_coverage.__file__), Path(trials.__file__))
    return dict(
        trial=trials.primary.lock(), coverage={p.name: trials.primary.checksum(p) for p in files}
    )


if __name__ == "__main__":
    with (
        patch.object(trials, "WORKER", WORKER),
        patch.object(trials, "REPORT", REPORT),
        patch.object(trials, "portable_gate_halo", portable_gate_coverage),
        patch.object(trials, "source", source),
    ):
        trials.main()
