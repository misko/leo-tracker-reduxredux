"""Compare the original and native track likelihood on the same saved proof geometry."""

import argparse
from hashlib import sha256
from math import isfinite
from pathlib import Path
from statistics import mean
from time import process_time
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve, write
from cold_track_row_transfer import DENSE, GEOGRAPHIC, SMALL, small_inputs
from cold_track_row_trial import REPLAY_PIN
from dense_full_short_crossover import file_sha
from dense_geographic_trial import difference, host
from full_short_run import geographic_projection
from regional_track_scores import TrackScores

HERE = Path(__file__).resolve().parent


def same_visits(left, right):
    if len(left) != len(right):
        raise ValueError("The regional proof visited different numbers of points")
    maximum = 0.
    for a, b in zip(left, right, strict=True):
        if any(a[key] != b[key] for key in ("xy_km", "latlon", "side", "owners")):
            raise ValueError("A probe or a track's assigned satellite changed")
        if not all(isfinite(v) for row in (a, b) for v in (row["score"], *row["receiver_scores"].values())):
            raise ValueError("Nonfinite score at a visited point")
        error = difference(a, b)
        if not error <= 1e-10:
            raise ValueError(f"Regional score changed by {error}")
        maximum = max(maximum, error)
    return maximum


def compare(kernel, tracks, catalogue, region, library):
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    start = process_time()
    points, original, meta = kernel._prepare_probe_scores(tracks, catalogue, region)
    setup = process_time() - start
    runs = []
    control_points = control_decision = None
    for arm in ("original", "native", "native", "original"):
        start = process_time()
        scorer = TrackScores(library, original) if arm == "native" else original
        visited = []

        def visit(point):
            row = scorer(dict(point))
            visited.append(row)
            return row["receiver_scores"]

        decision = evaluate_terminal(points, region.width_km, visit)
        duration = process_time() - start
        if control_points is None:
            control_points, control_decision = visited, decision
        drift = same_visits(control_points, visited)
        if difference(decision, control_decision) > 1e-10 or not visited:
            raise ValueError("Regional terminal comparison failed")
        if arm == "native" and (scorer.native != len(visited) or scorer.fallbacks):
            raise ValueError("A tested point fell back to the original")
        runs.append(dict(arm=arm, cpu_s=duration, max_score_drift=drift, points=len(visited)))
    means = {arm: mean(r["cpu_s"] for r in runs if r["arm"] == arm) for arm in ("native", "original")}
    return dict(runs=runs, mean_cpu_s=means, shared_geometry_cpu_s=setup, terminal=control_decision,
                visits_sha256=sha256(repr([(p["xy_km"], p["owners"]) for p in control_points]).encode()).hexdigest(),
                meta=meta, saved_cpu_s=means["original"] - means["native"])


def assignment(case):
    if case != "dense":
        (_, archive, _, path, pin, offer), control = small_inputs(case)
        return archive, path, pin, offer, control["early_regional"][0]["result"]
    if file_sha(DENSE) != REPLAY_PIN:
        raise ValueError("Unrecognized dense saved control")
    control = read(DENSE)
    path, = Path("/var/tmp/leo-full-short-dense-DS30-0008/publication/fast-scan-automatic-work").glob("*/detections.json")
    identity = control["raw"]["holder"]
    return identity["archive"], path, control["raw"]["raw_native_sha256"], identity["offer"], control["regional"][0]["result"]


def run(case, library, output):
    system = host()
    if case == "dense":
        small = [read(output.parent / f"{name}.json") for name in SMALL]
        if (any(row["case"] != name or row["library"] != file_sha(library) for name, row in zip(SMALL, small, strict=True))
                or sum(r["mean_cpu_s"]["native"] for r in small) > .8 * sum(r["mean_cpu_s"]["original"] for r in small)):
            raise ValueError("Small saved proof screen failed")
    publication, specification = configuration()
    from dense_geographic_projection import checked_runtime
    from leo.contracts.digests import canonical_digest
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    archive, path, pin, offer, control = assignment(case)
    if archive_identity(Path(archive["root"])) != archive or file_sha(path) != pin.removeprefix("sha256:"):
        raise ValueError("Saved causal archive or detector changed")
    document = read(path)
    if canonical_digest(document) != pin:
        raise ValueError("Saved detector canonical digest differs")
    kernel, _ = checked_runtime()
    normal = algo08_position.solve
    record = {}

    class ProofFinished(Exception):
        pass

    def intercept(native, reader, assets, region):
        if region.document() != offer:
            raise ValueError("Unexpected supplied region")
        with handoff(reader) as (live, _, _), geographic_projection(GEOGRAPHIC):
            def proof(prepared, view, *_args, **_kwargs):
                tracks = prepared["tracks"]
                causal = live.match(tracks, reader)
                if causal is None or list(view.center) != offer["center"] or view.width_km != offer["width_km"]:
                    raise ValueError("Missing original causal catalogue or offer")
                record.update(compare(kernel, tracks, causal.catalogue, view, library))
                raise ProofFinished()

            with patch.object(v5_core, "infer", proof):
                return normal(native, reader, assets, region)

    with patch.object(algo08_position, "solve", intercept):
        try:
            solve(publication, specification, document, Path(archive["root"]), offer)
        except ProofFinished:
            pass
    if any(record["terminal"].get(k) != control.get(k) for k in ("would_withhold", "stop", "probes_evaluated")):
        raise ValueError("Published regional decision failed to reproduce")
    write(output, dict(case=case, machine=system, graph="installed", archive=archive, offer=offer,
                       native_pin=pin, library=file_sha(library), **record))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=(*SMALL, "dense"))
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
