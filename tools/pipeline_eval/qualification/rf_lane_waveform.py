"""Replay the whole recorded clock with exactly one detector assigned per valid visit."""

import argparse
from pathlib import Path

from .. import original_receiver
from ..__main__ import local_output, write
from ..variants import prepared_hotpath_peaks, rf_routing
from . import arrival_queue, paced_controlled_source
from . import parallel_acquisition as replay
from . import parallel_acquisition_source as staging
from .full_v5_check import _sha

PREFIX = "leo-rfw-261119"
WORK = Path("/var/tmp") / PREFIX
STAGE = Path("/dev/shm") / PREFIX
REPORT = staging.SCREEN / "pilot-search-and-region/rf-lane-waveform"
CPUS = {"DS26-0237": (4, 5, 20), "DS29-0082": (6, 7, 21)}
SELECTED_RF_HZ = {"DS26-0237": 12_209_687_500, "DS29-0082": 12_690_312_500}
PROGRAMS = (
    Path(__file__),
    *(
        Path(module.__file__)
        for module in (
            replay,
            staging,
            paced_controlled_source,
            original_receiver,
            prepared_hotpath_peaks,
            rf_routing,
            arrival_queue,
        )
    ),
)


def snapshot_sources(work):
    folder = work / "measured-sources"
    folder.mkdir(mode=0o755, parents=True, exist_ok=True)
    for path in PROGRAMS:
        snapshot = folder / path.name
        if not snapshot.exists():
            write(snapshot, path.read_bytes())
        if path.read_bytes() != snapshot.read_bytes():
            raise ValueError(f"program source changed across paired launches: {path.name}")


def stage(case, stage_root):
    stage_root.mkdir(mode=0o755, parents=True, exist_ok=True)
    staging.stage(
        case,
        stage_root / case,
        cpu=CPUS[case][2],
        unit=f"{PREFIX}-{case.lower()}-stage.service",
    )


def routing_evidence(spec, events):
    seed = spec["capture"]["input_manifest_sha256"]
    centers = sorted({event["center_hz"] for event in events if event["status"] == "processed"})
    selected_rf_hz = SELECTED_RF_HZ[spec["case"]]
    if rf_routing.choose_rf(seed, centers) != selected_rf_hz:
        raise ValueError("authenticated scan does not reproduce the prospective RF assignment")
    return dict(
        policy="whole-rf-v1",
        selected_rf_hz=selected_rf_hz,
        rf_centers_hz=centers,
        experiment_seed=seed,
        selector_source_sha256=_sha(Path(rf_routing.__file__)),
    )


def launch(case, work, stage_root):
    folder = stage_root / case
    spec, _, events, _ = replay.source_input(folder)
    snapshot_sources(work)
    replay.launch(
        case,
        work / case,
        folder,
        cpus=CPUS[case],
        prefix=PREFIX,
        routing=routing_evidence(spec, events),
        selector=original_receiver.selector_evidence("row-wise", Path(spec["producer"])),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "launch"))
    parser.add_argument("case", choices=CPUS)
    parser.add_argument("--stage-root", type=local_output, default=STAGE)
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.case, args.stage_root)
    else:
        launch(args.case, args.work, args.stage_root)
