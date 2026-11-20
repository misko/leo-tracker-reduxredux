"""Try stored FFTW measured plans on the two viable development lengths."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import geometric_mean, median
from time import process_time_ns

from ..__main__ import encoded, save_json, write
from ..variants import fft_length_plan, original_kernel
from . import fft_length_sweep as sweep
from .coarse_basis_audit import FALLBACK
from .coarse_basis_eval import captures
from .full_v5_check import _sha
from .retry_reuse_eval import window_from_lock

LENGTHS = (256, 512)


def read(path):
    return json.loads(path.read_bytes())


def prepare(work):
    original = work / "selection-lock.json"
    chosen = read(original)
    inputs = read(work / "input-lock.json")
    sizes = sorted(chosen["paired_native_ratio"], key=chosen["paired_native_ratio"].get)[:2]
    if set(map(int, sizes)) != set(LENGTHS):
        raise ValueError("the stored-plan follow-up is bound to the two observed fastest lengths")
    write(work / "estimate-selection-lock.json", original.read_bytes())
    variants = {}
    for size in LENGTHS:
        start = process_time_ns()
        wisdom = fft_length_plan.measure(size)
        planning_ns = process_time_ns() - start
        directory = work / f"planned-{size}"
        previous = Path(inputs["variants"][str(size)]["path"]).parent
        binary, command = fft_length_plan.build(directory, previous, wisdom)
        write(directory / "fftw.wisdom", wisdom.encode("ascii"))
        variants[str(size)] = dict(
            path=str(binary),
            sha256=_sha(binary),
            command=command,
            planning_cpu_ns=planning_ns,
            generated={p.name: _sha(p) for p in directory.iterdir() if p != binary},
        )
    save_json(
        work / "planning-lock.json",
        dict(
            initial_selection_sha256=_sha(work / "estimate-selection-lock.json"),
            qualification_source_sha256=_sha(Path(__file__)),
            variant_source_sha256=_sha(Path(fft_length_plan.__file__)),
            rule="Compare measured plans at the two fastest lengths with the released bank.",
            variants=variants,
        ),
    )


def bench(work, ident):
    from leo.analysis.starlink import acquisition

    inputs, case, policy, _producer = sweep.checked(work, ident)
    plan = read(work / "planning-lock.json")
    if (
        _sha(Path(__file__)) != plan["qualification_source_sha256"]
        or _sha(Path(fft_length_plan.__file__)) != plan["variant_source_sha256"]
    ):
        raise ValueError("plan experiment differs from the fixed source")
    ready = inputs["variants"]["512"]["path"]
    grids = {"estimate": original_kernel.PersistentGrid(ready)}
    for length, info in plan["variants"].items():
        if _sha(Path(info["path"])) != info["sha256"]:
            raise ValueError("measured plan library changed")
        grids[length] = original_kernel.PersistentGrid(info["path"])

    def timed(args, layout):
        inspected = {}
        for name in layout:
            grid = grids[name]
            begin = process_time_ns()
            grid.score_grid(acquisition, original, *args)
            receipt = grid.calls[-1]
            if not receipt["applied"] or receipt["fft_length"] != int(
                "512" if name == "estimate" else name
            ):
                raise ValueError("prepared stored-plan ABI declined the measured shape")
            inspected[name] = dict(cpu_ns=process_time_ns() - begin, **receipt)
        return inspected

    rows = []
    try:
        for declared in (r for r in case["rows"] if r["split"] == "development"):
            window = window_from_lock(work, ident, declared)
            original, _, inputs = captures(window, policy)
            for receiver, (args, _rank) in enumerate(inputs):
                for anchors in (args[4], FALLBACK):
                    working = *args[:4], anchors, args[-1]
                    layout = tuple(grids)
                    first = timed(working, layout)
                    series = []
                    for repeat in range(sweep.REPEATS):
                        shift = (repeat + len(rows)) % len(layout)
                        order = layout[shift:] + layout[:shift]
                        series.append(dict(order=order, calls=timed(working, order)))
                    rows.append(
                        dict(receiver=receiver, anchors=len(anchors), first=first, paired=series)
                    )
                    print(
                        ident,
                        receiver,
                        len(anchors),
                        {
                            size: round(
                                median(r["calls"][size]["native_cpu_ns"] for r in series) / 1e6, 2
                            )
                            for size in layout
                        },
                        flush=True,
                    )
    finally:
        for grid in grids.values():
            grid.clear_cache()
    write(
        work / f"{ident}-planned.json.gz",
        gzip.compress(
            encoded(
                dict(
                    case=ident,
                    rows=rows,
                    planning_lock_sha256=_sha(work / "planning-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


def select(work):
    plan = read(work / "planning-lock.json")
    estimate = read(work / "estimate-selection-lock.json")
    names = [f"{ident}-planned.json.gz" for ident in sweep.DEV]
    indexed = [json.loads(gzip.decompress((work / p).read_bytes())) for p in names]
    if any(
        item["planning_lock_sha256"] != _sha(work / "planning-lock.json") or len(item["rows"]) != 4
        for item in indexed
    ):
        raise ValueError("incomplete stored-plan sweep")
    rows = [r for item in indexed for r in item["rows"]]
    ratios = {
        k: geometric_mean(
            [
                median(
                    pair["calls"][k]["native_cpu_ns"] / pair["calls"]["estimate"]["native_cpu_ns"]
                    for pair in row["paired"]
                )
                for row in rows
            ]
        )
        for k in plan["variants"]
    }
    length = str(estimate["selected"])
    winner = min(ratios, key=ratios.get)
    selectable = ratios[winner] < estimate["paired_native_ratio"][length]
    chosen = dict(
        estimate,
        selected=int(winner if selectable else length),
        measured_ratios=ratios,
        planner="stored-measure" if selectable else "estimate",
        development=estimate["development"] | {p: _sha(work / p) for p in names},
        planning_sha256=_sha(work / "planning-lock.json"),
    )
    if selectable:
        chosen["selected_build"] = plan["variants"][winner]
    save_json(work / "selection-lock.json", chosen)
    print(chosen, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "bench", "select"))
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(sweep.DEV), nargs="?")
    args = parser.parse_args()
    if args.action == "bench":
        bench(args.work, args.case)
    else:
        {"prepare": prepare, "select": select}[args.action](args.work)
