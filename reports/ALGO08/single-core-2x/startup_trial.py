"""Profile fresh ALGO08 imports, a sealed prefix, and saved completed science."""

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

TRACKED = (
    "numpy", "scipy.linalg", "scipy.optimize", "scipy.stats",
    "matplotlib.figure", "matplotlib.backends.backend_agg", "sgp4",
    "sqlalchemy", "leo.catalog", "leo.operations.retention", "leo.operations.service",
    "leo.operations.tle_archive", "leo.operations.localization_v3_inputs",
    "leo.analysis.research.analyzers", "leo.analysis.standard.analyzers",
    "leo.storage.persistent_hop", "leo.scanner.persistent_hop",
)


def modules():
    return {name: name in sys.modules for name in TRACKED}


def prepare_inputs(pair_path):
    pair = json.loads(pair_path.read_bytes())
    session = pair["runs"]["candidate"]["receipt"]["session_id"]
    root = pair_path.parent / "candidate"
    inventory = json.loads((root / "fast-scan-inputs" / f"{session}.json").read_bytes())
    detections = tuple((root / "fast-scan-automatic-work").glob("*/detections.json"))
    if len(detections) != 1:
        raise ValueError("expected one saved candidate detection artifact")
    native = json.loads(detections[0].read_bytes())
    if native["source"]["session_id"] != session:
        raise ValueError("saved inventory and candidate detections differ")
    return (session, Path(pair["recording"]), Path(pair["region"]), inventory, native)


def replay(startup, pair, specification_path, archive_path):
    started, wall_start = process_time_ns(), perf_counter_ns()
    if startup == "lazy":
        from tools.pipeline_eval.variants.experimental.lean_startup import install

        install()
    from leo.contracts.digests import canonical_digest
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import experimental_publication

    session, recording, region, inventory, native = prepare_inputs(pair)
    specification = json.loads(specification_path.read_bytes())
    limit = 40
    if inventory["segments"][0]["windows"] < limit:
        raise ValueError("the acquisition prefix must fit in the first sealed segment")
    prefix = dict(inventory, window_count=limit, segments=inventory["segments"][:1])
    stock_segment = algo08_scan.FastSegmentSource
    results = {}
    stages = {}
    loaded_after = {}

    def checkpoint(name, cpu, wall):
        stages[name] = dict(cpu_s=(process_time_ns() - cpu) / 1e9,
                            elapsed_s=(perf_counter_ns() - wall) / 1e9)
        loaded_after[name] = modules()

    class PrefixSegment(stock_segment):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=limit)

    def analyze(recording_path, root, assets, archive, offer):
        checkpoint("import_and_setup", started, wall_start)
        start, wall = process_time_ns(), perf_counter_ns()
        with patch.object(algo08_scan, "FastSegmentSource", PrefixSegment):
            acquisition = algo08_scan.acquire(session, canonical_digest(prefix), prefix, assets)
        checkpoint("prefix_acquisition", start, wall)

        start, wall = process_time_ns(), perf_counter_ns()
        prediction, packet, policy = algo08_scan.solve(
            native, algo08_scan.TleArchiveReader(archive), assets, offer,
        )
        if prediction["status"] != "ok" or packet is None:
            raise ValueError("saved positive candidate must exercise solver and renderer")
        checkpoint("saved_factor_solve", start, wall)

        start, wall = process_time_ns(), perf_counter_ns()
        figures = algo08_scan.render(packet, title=recording_path.name)
        if len(figures) != 8:
            raise ValueError("expected the eight completed publication figures")
        checkpoint("saved_factor_render", start, wall)
        # Use the same scientific grid normalization as the publication comparer.
        grid = {key: value for key, value in packet["position_grid"].items()
                if key not in ("binding", "elapsed_seconds")}
        results.update(
            prefix_raw_authority=acquisition["source"]["raw_recording_authority_digest"],
            prefix_ordered_probes=canonical_digest(acquisition["source"]["probes"]),
            native_raw_authority=native["source"]["raw_recording_authority_digest"],
            native_detection=canonical_digest(native),
            decision=prediction["status"],
            policy=policy,
            arms=prediction["arms"],
            position_grid=canonical_digest(grid),
            position_path=canonical_digest(packet["position_path"]),
            figures={name: sha256(data).hexdigest() for name, data in figures.items()},
        )
        return {}

    with TemporaryDirectory(prefix="algo08-startup-trial-") as scratch:
        args = SimpleNamespace(recording=recording, bulk_root=Path(scratch), archive=archive_path,
                               region=region)
        with patch.object(algo08_scan, "analyze", analyze):
            experimental_publication.run(args, specification)
    return dict(startup=startup, checks=results, modules=loaded_after, stages=stages,
                cpu_s=(process_time_ns() - started) / 1e9,
                elapsed_s=(perf_counter_ns() - wall_start) / 1e9)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("startup", choices=("stock", "lazy"))
    parser.add_argument("pair", type=Path)
    parser.add_argument("specification", type=Path)
    parser.add_argument("--archive", type=Path, default=Path("/var/lib/leo/tle"))
    arguments = parser.parse_args()
    print(json.dumps(replay(arguments.startup, arguments.pair, arguments.specification,
                            arguments.archive), indent=2, allow_nan=False))
