"""Benchmark bounded regional probe blocks through the live terminal policy."""

import argparse
from pathlib import Path
from statistics import median
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve, write
from cold_track_row_transfer import GEOGRAPHIC
from dense_full_short_crossover import file_sha
from dense_geographic_trial import host
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection
from regional_probe_block import BLOCK_WIDTH, OrderedProbeScores, ProbeBlock
from regional_track_scores import TrackScores
from regional_track_trial import assignment


HERE = Path(__file__).resolve().parent
CASES = ("dense", "south-far")


def binding(case):
    archive, path, pin, offer, control = assignment(case)
    if archive_identity(Path(archive["root"])) != archive or file_sha(path) != pin.removeprefix("sha256:"):
        raise ValueError("Saved causal archive or detector changed")
    return dict(archive=archive, detection=str(path), native_pin=pin, offer=offer, control=control)


def authority(stock, block, specification):
    from dense_geographic_projection import checked_runtime
    from tools.pipeline_eval.variants.experimental import (
        regional_bound_guard,
        regional_exterior_veto,
        regional_veto_short_circuit,
    )

    kernel, reference = checked_runtime()
    if file_sha(stock) != TRACK_SCORES_SHA or file_sha(GEOGRAPHIC) != GEOGRAPHIC_SHA:
        raise ValueError("Unreviewed stock native library")
    files = (
        Path(__file__), HERE / "regional-probe-block-protocol.md",
        HERE / "regional_probe_block.py", HERE / "regional_probe_block.c",
        HERE / "regional_track_scores.py", HERE / "regional_track_scores.c",
        HERE / "dense_geographic_projection.py", HERE / "dense_geographic_projection.c",
        Path(kernel.__file__), Path(reference.__code__.co_filename),
        Path(regional_bound_guard.__file__), Path(regional_exterior_veto.__file__),
        Path(regional_veto_short_circuit.__file__),
        stock.resolve(), block.resolve(), GEOGRAPHIC.resolve(),
    )
    return dict(files={str(p): file_sha(p) for p in files}, specification=specification)


def freeze(directory, stock, block):
    host()
    _, specification = configuration()
    lock = dict(
        authority=authority(stock, block, specification),
        bindings={case: binding(case) for case in CASES},
        schedule={
            case: [pair for repeat in range(5)
                   for pair in (("stock", "block") if (repeat + ci) % 2 == 0 else ("block", "stock"))]
            for ci, case in enumerate(CASES)
        },
        block_width=BLOCK_WIDTH,
    )
    write(directory / "source-lock.json", lock)


def stage(kernel, tracks, reader, causal, region, stock, block, mode):
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    visited = []
    record = {}

    def evaluate(prepared, catalogue, offer):
        points, scalar, meta = kernel._prepare_probe_scores(prepared, catalogue, offer)
        start = process_time()
        packed = TrackScores(stock, scalar)
        if mode == "block":
            native = ProbeBlock(block, packed)
            score = OrderedProbeScores(points, offer.width_km, native, packed)
        else:
            score = lambda point: packed(dict(point))

        def visit(point):
            row = score(point)
            visited.append(row)
            return row["receiver_scores"]

        decision = evaluate_terminal(points, offer.width_km, visit)
        record["score_cpu_s"] = process_time() - start
        if mode == "block":
            if score.failed or packed.native or packed.fallbacks:
                raise ValueError("Native block fell back during qualification")
            evaluations, calls = native.computed, native.calls
            record["block_scratch_bytes"] = native.frame.nbytes + sum(a.nbytes for a in native.scratch)
        else:
            if packed.native != len(visited) or packed.fallbacks:
                raise ValueError("Native scalar scorer fell back during qualification")
            evaluations, calls = packed.native, packed.native
        cells = packed.geometry.geometry.position_norm_squared.size
        record.update(
            evaluated=evaluations, visited=len(visited), kernel_calls=calls,
            excess=evaluations - len(visited), cells=cells * evaluations,
            excess_cells=cells * (evaluations - len(visited)),
        )
        return dict(decision, **meta)

    with geographic_projection(GEOGRAPHIC) as projection, patch.object(kernel, "evaluate_veto", evaluate):
        cpu, wall = process_time(), perf_counter()
        result = regional_bound_guard.causal_probes(
            tracks, reader, region, catalogue=causal, terminal_only=True
        )
        record.update(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - wall)
    if projection.get("original_fallback") or projection.get("calls", 0) != (
            len(visited) if mode == "stock" else 0):
        raise ValueError("Unexpected scalar projector work")
    return dict(record, arm=mode, projection=dict(projection), result=result), visited


def run(case, directory, stock, block):
    current = host()
    publication, specification = configuration()
    source = directory / "source-lock.json"
    lock = read(source)
    given = binding(case)
    if authority(stock, block, specification) != lock["authority"] or given != lock["bindings"][case]:
        raise ValueError("Benchmark authority changed after freeze")
    from dense_geographic_projection import checked_runtime
    from leo.contracts.digests import canonical_digest
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    original = read(Path(given["detection"]))
    if canonical_digest(original) != given["native_pin"]:
        raise ValueError("Saved detector canonical digest differs")
    kernel, _ = checked_runtime()
    normal = algo08_position.solve
    offer = given["offer"]
    runs = []
    expected = None

    class ProofFinished(Exception):
        pass

    def intercept(native, reader, assets, region):
        nonlocal expected
        if region.document() != offer:
            raise ValueError("Unexpected supplied region")
        with handoff(reader) as (live, _, _):
            def proof(prepared, view, *_args, **_kwargs):
                nonlocal expected
                tracks = prepared["tracks"]
                causal = live.match(tracks, reader)
                if causal is None or list(view.center) != offer["center"] or view.width_km != offer["width_km"]:
                    raise ValueError("Missing original prepared catalogue or offer")
                for mode in lock["schedule"][case]:
                    row, rows = stage(kernel, tracks, reader, causal, view, stock, block, mode)
                    if expected is None:
                        expected = row["result"], rows
                    if (row["result"], rows) != expected:
                        raise ValueError("A probe score, owner, order or terminal result changed")
                    if any(row["result"].get(k) != given["control"].get(k) for k in (
                        "would_withhold", "stop", "probes_evaluated", "complete"
                    )):
                        raise ValueError("Historical terminal policy did not reproduce")
                    runs.append(dict(row, rows_sha256=canonical_digest(rows)))
                    print(case, mode, row["cpu_s"], row["score_cpu_s"], row["excess"], flush=True)
                raise ProofFinished()

            with patch.object(v5_core, "infer", proof):
                return normal(native, reader, assets, region)

    with patch.object(algo08_position, "solve", intercept):
        try:
            solve(publication, specification, original, Path(given["archive"]["root"]), offer)
        except ProofFinished:
            pass
    if len(runs) != len(lock["schedule"][case]):
        raise ValueError("Missing regional proof attempts")
    ratios = []
    for a, b in zip(runs[::2], runs[1::2], strict=True):
        control, candidate = (a, b) if a["arm"] == "stock" else (b, a)
        ratios.append({k: candidate[k] / control[k] for k in ("cpu_s", "elapsed_s", "score_cpu_s")})
    write(
        directory / f"{case}.json",
        dict(case=case, machine=current, source_sha256=file_sha(source), runs=runs, rows=expected[1],
             paired_ratios=ratios, median_ratios={k: median(r[k] for r in ratios) for k in ratios[0]}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", *CASES))
    parser.add_argument("directory", type=Path)
    parser.add_argument("stock", type=Path)
    parser.add_argument("block", type=Path)
    args = parser.parse_args()
    names = args.directory, args.stock, args.block
    if args.action == "freeze":
        freeze(*names)
    else:
        run(args.action, *names)
