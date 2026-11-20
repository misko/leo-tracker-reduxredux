"""Measure rank-20 AVX-VNNI reconstruction with actual sparse native revisits."""

import argparse
import gzip
import importlib.util
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import encoded, write
from ..variants import coarse_basis, coarse_basis_integer, original_kernel
from .coarse_basis_audit import FALLBACK
from .coarse_basis_eval import CASES, REPEATS, captures, compare_map, read_lock
from .full_v5_check import _sha

SPARSE = Path(
    "/opt/leo-native-glrt-runtime/a1b999aad5bdc924fd90d35e055878bc23bd4c06/"
    "src/leo/analysis/starlink/_sparse_native"
)


def sparse_library():
    (library,) = SPARSE.glob("_native_acquisition*.so")
    spec = importlib.util.spec_from_file_location("_native_acquisition", library)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.folded_anchor_score_grid_backend() != "avx2_fma":
        raise ValueError("revisit requires the screened release's AVX2 exact column scorer")
    return module, library


def revisit(grid, retain, ranking, native, args, starts, frames, prefix):
    raw, template, rate, bins, _, epochs = args
    residuals, count, epoch_sep, cfo_sep, _ = ranking
    proposed = retain(residuals, tuple(grid), 32, epoch_sep, cfo_sep, epochs)
    span = np.arange(-6, 7)
    by_lane = [[] for _ in range(len(bins))]
    for score, epoch, residual in proposed:
        if score > 0:
            by_lane[residuals.index(residual)].append((epoch + span) % epochs)
    sparse = np.full_like(grid, np.nan)
    evaluated = 0
    for start in range(0, len(bins), 12):
        chunk = bins[start : start + 12]
        guessed = [a for group in by_lane[start : start + len(chunk)] for a in group]
        if not guessed:
            continue
        requested = np.unique(np.concatenate(guessed)).astype(np.intp)
        lanes = (*chunk, *((chunk[-1],) * (12 - len(chunk))))
        evaluated += len(requested) * len(lanes)
        coarse = native.folded_anchor_score_columns(
            np.asarray(raw, np.complex128),
            template,
            np.asarray(lanes),
            starts,
            starts + 44,
            frames,
            prefix,
            rate,
            epochs,
            requested,
        )
        for lane, nominal in enumerate(by_lane[start : start + len(chunk)]):
            if nominal:
                epochs_to_restore = np.unique(np.concatenate(nominal))
                sparse[start + lane, epochs_to_restore] = coarse[
                    lane, np.searchsorted(requested, epochs_to_restore)
                ]
    selected = retain(residuals, tuple(sparse), count, epoch_sep, cfo_sep, epochs)
    return sparse, selected, evaluated


def verify(window, policy, work):
    from leo.analysis.starlink import acquisition as acq

    orig, retain, inputs = captures(window, policy)
    native, sparse = sparse_library()
    library = work / "integer-basis.so"
    command = coarse_basis_integer.build(library)
    grid = original_kernel.PersistentGrid(work / "prepared/original_kernel.so")
    rows = []
    try:
        for lane, (args, ranking) in enumerate(inputs):
            for anchors in (args[4], FALLBACK):
                samples, template, rate, bins, _, epochs = args
                working = samples, template, rate, bins, anchors, epochs
                starts = np.array([round(s * rate * acq.OFDM_SYMBOL_DURATION_S) for s in anchors])
                frames = np.rint(np.arange(15) * rate / acq.FRAME_RATE_HZ).astype(np.intp)
                prefix = acq._power_prefix(samples)
                bank = coarse_basis.filters(template, starts, 44, bins, rate)
                fp32 = coarse_basis.Projection(
                    work / "projection.so",
                    bank,
                    20,
                    starts,
                    frames,
                    epochs,
                )
                quantized = coarse_basis_integer.QuantizedReconstruction(library, fp32)

                def prepared(ready):
                    return grid.score_grid(acq, orig, *ready)

                def proposed(
                    receiver, geometry=(working, starts, frames, prefix, ranking), model=quantized
                ):
                    work_args, s, f, p, ordering = geometry
                    votes, cost = model.score(receiver, p)
                    revisit_start = process_time_ns()
                    exact, keys, calculated = revisit(
                        votes,
                        retain,
                        ordering,
                        native,
                        work_args,
                        s,
                        f,
                        p,
                    )
                    return (
                        votes,
                        exact,
                        keys,
                        dict(
                            cost,
                            revisit_ns=process_time_ns() - revisit_start,
                            evaluated_cells=calculated,
                        ),
                    )

                prepared(working)
                proposed(samples)
                timings = []
                for iteration in range(REPEATS):
                    order = ("prepared", "int8") if iteration % 2 == 0 else ("int8", "prepared")
                    pair = {}
                    for mode in order:
                        cpu, wall = process_time_ns(), perf_counter_ns()
                        if mode == "prepared":
                            prepared(working)
                            cost = grid.calls[-1]
                        else:
                            votes, exact, keys, cost = proposed(samples)
                        pair[mode] = dict(
                            cpu_ns=process_time_ns() - cpu,
                            wall_ns=perf_counter_ns() - wall,
                            stage=cost,
                        )
                    timings.append(dict(order=order, pair=pair))
                direct = np.asarray(orig(*working))
                mask = np.isfinite(exact)
                observed = exact[mask] - direct[mask]
                exact_keys = retain(ranking[0], tuple(direct), *ranking[1:])
                match_key = [(epoch, cfo) for _, epoch, cfo in keys]
                direct_key = [(epoch, cfo) for _, epoch, cfo in exact_keys]
                precision = compare_map(direct, votes, retain, ranking)
                rows.append(
                    dict(
                        lane=lane,
                        anchors=len(anchors),
                        precision=precision,
                        timings=timings,
                        restored_cells=int(mask.sum()),
                        max_revisit_score_delta=float(abs(observed).max(initial=0)),
                        reproduced_cells=int(np.count_nonzero(observed == 0)),
                        ordered_recall=match_key == direct_key,
                        missed_keys=sorted(set(direct_key) - set(match_key)),
                        unmatched_keys=sorted(set(match_key) - set(direct_key)),
                        selected=keys,
                    )
                )
    finally:
        grid.clear_cache()
    return dict(rows=rows, sparse_library=str(sparse), sparse_sha256=_sha(sparse), compiler=command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(CASES))
    cli = parser.parse_args()
    policy, provenance, ((window, witness),) = read_lock(cli.work, cli.case, "development")
    result = verify(window, policy, cli.work)
    result.update(witness=witness, provenance=provenance)
    write(cli.work / f"{cli.case}-int8.json.gz", gzip.compress(encoded(result), mtime=0))
