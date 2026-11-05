"""External full native-to-PNG check with concurrent initial-search arms only.

Reference output is opened only after inference and rendering finish. This is
not production execution, a publication test or an end-to-end speedup claim.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import check_algo07v3_engine as engine
import probe_algo07v3_parallel_initial as experiment


def run(args):
    from leo.analysis.localization_v3 import initial_search
    from leo.application import localization_v3

    affinity = os.sched_getaffinity(0)
    if len(set(args.cpus)) != 2 or not set(args.cpus) <= affinity:
        raise ValueError("Two distinct available CPUs required")
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output / "native"
    output.mkdir()
    experiment._CPUS = args.cpus
    candidate, arm, source, modified = experiment.transformed_function(
        initial_search, experiment.parallel_pair
    )
    experiment._ARM_FUNCTION = arm
    original = localization_v3.initial_search
    native = args.bundle / "native.json"
    config = SimpleNamespace(
        native_input=native,
        input_sha256="sha256:" + hashlib.sha256(native.read_bytes()).hexdigest(),
        track_config=args.bundle / "config.json",
        tle_root=args.bundle / "tle",
        search_center=(37.906, -122.545),
        screen_center=(37.5, -122.0),
        scan_identities=["fast-af5f79e905d946a6e38f9e3e8243460c"],
        output=output,
    )
    os.sched_setaffinity(0, {args.cpus[0]})
    localization_v3.initial_search = candidate
    began = time.perf_counter()
    try:
        engine.run(config)
    finally:
        localization_v3.initial_search = original
        os.sched_setaffinity(0, affinity)
    seconds = time.perf_counter() - began
    # The candidate has finished. Reference data never enters inference.
    expected_bytes = args.reference.read_bytes()
    actual_bytes = (output / "result.json").read_bytes()
    expected, actual = json.loads(expected_bytes), json.loads(actual_bytes)
    exact = actual == expected
    figure_checks = {}
    for path in sorted(output.glob("*.png")):
        figure_checks[path.name] = (
            path.read_bytes() == (args.reference.parent / path.name).read_bytes()
        )
    if len(figure_checks) != 8:
        raise ValueError("Eight actual PNG comparisons required")
    receipt = dict(
        complete=True,
        exact=exact and all(figure_checks.values()),
        scientific_snapshot_exact=exact,
        figure_checks=figure_checks,
        differing_fields=[
            k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k)
        ],
        observed_seconds=seconds,
        reference_sha256=hashlib.sha256(expected_bytes).hexdigest(),
        actual_sha256=hashlib.sha256(actual_bytes).hexdigest(),
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        experiment_sha256=hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        candidate_source_sha256=hashlib.sha256(modified.encode()).hexdigest(),
        pairs=experiment._PAIR_EVENTS,
        runtime_enabled=False,
        publication_qualified=False,
        qualified_pipeline_speedup=None,
    )
    with (args.output / "comparison.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps(receipt), flush=True)
    if not receipt["exact"]:
        raise SystemExit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--cpus", nargs=2, type=int, required=True)
    run(parser.parse_args())
