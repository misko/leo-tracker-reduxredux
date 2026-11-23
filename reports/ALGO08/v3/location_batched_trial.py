"""Compare a four-location row prepass on the saved publication likelihood."""

import argparse
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from aperture_trial import archive_identity, configuration, read, solve, write
from cold_track_row_transfer import small_inputs
from dense_full_short_crossover import OWNER_KEYS, file_sha
from dense_geographic_trial import host
from grid_neighbor_gamma import clear_grid_cache, sweep_points
from grid_neighbor_gamma_trial import reconstruct
from location_batched_gram import ARMS, REPEATS, BatchGram, build

HERE = Path(__file__).resolve().parent
SWEEPS = ("local", "south_face")
WEAK_CONTROL = Path("/var/tmp/leo-short-graph-20261123-physical")


def array(pointer, length, dtype=ct.c_double):
    return np.ctypeslib.as_array(ct.cast(pointer, ct.POINTER(dtype)), shape=(length,))


class Compare:
    def __init__(self, binary, archive):
        self.gram = BatchGram(binary)
        self.archive = archive
        self.context = self.point = None
        self.rows, self.clocks = [], []

    def operation(self, original):
        def run(capture, owner, stock, args):
            state = self.point
            if state is None or "result" in state:
                raise ValueError("Expected one fresh native factor at each point")
            problem, _ = self.context["problems"][state["arm"]]
            n, p = int(np.count_nonzero(problem.keep)), capture.width
            layout = args[0]
            y = array(args[5], n)
            design = array(args[6], n*p).reshape(n, p)
            sigma, groups = array(args[7], n), array(args[8], n, ct.c_int64)
            if state["mode"] == "collect":
                state["inputs"] = (layout, y.copy(), design.copy(), sigma.copy(), groups.copy())
            elif not all(np.array_equal(a, b) for a, b in zip(
                    (y, design, sigma, groups), state["inputs"][1:], strict=True)):
                raise ValueError("A sampled position changed its numeric operands")
            if layout != state["inputs"][0]:
                raise ValueError("Native symbolic layout changed")
            if state["mode"] == "batch":
                self.gram.fit.argtypes = [*stock.argtypes, ct.c_void_p]
                op = lambda *values: self.gram.fit(*values, state["stats"].ctypes.data)
            else:
                op = stock

            start = process_time_ns()
            status = original(capture, owner, op, args)
            native_ns = process_time_ns()-start
            if status != 0 or capture.exported.value != 1:
                raise ValueError("The checked native grid posterior was unavailable")
            k, t = int(groups.max())+1, args[11]
            contents = [array(args[index], length).tobytes() for index, length in (
                (19, p), (20, n), (21, k), (22, p), (23, t), (24, 2), (26, k),
            )]
            contents.extend((capture.lower.tobytes(), capture.order.tobytes()))
            state["result"] = dict(
                native_ns=native_ns, sha256=sha256(b"".join(contents)).hexdigest(),
                updates=ct.cast(args[25], ct.POINTER(ct.c_int))[0],
                final_change=float(array(args[24], 2)[1]), width=p, rows=n, noise_groups=k,
                status=status, export=capture.exported.value,
            )
            return status
        return run

    def score(self, score, arm, point, mode, *, inputs=None, stats=None):
        problem, _ = self.context["problems"][arm]
        clear_grid_cache(problem)
        self.point = dict(arm=arm, mode=mode, inputs=inputs, stats=stats)
        value = score(arm, point)
        record = self.point["result"] | dict(score=value)
        data = self.point["inputs"]
        self.point = None
        return record, data

    def compare_strip(self, score, arm, sweep, sites):
        points = [(r["east_km"], r["north_km"]) for r in sites]
        control, inputs = zip(*(self.score(score, arm, p, "collect") for p in points), strict=True)
        if any(a["score"] != b["scores"][arm] for a, b in zip(control, sites, strict=True)):
            raise ValueError(f"Released scores changed on the {arm} {sweep} strip")
        layout, _, _, sigma, groups = inputs[0]
        if any(row[0] != layout or not np.array_equal(row[3], sigma)
               or not np.array_equal(row[4], groups) for row in inputs):
            raise ValueError("Observed grid sites require separate batch layouts")
        originals = [{k: v for k, v in c.items() if k != "native_ns"} for c in control]
        output = {mode: [] for mode in ("stock", "batch")}
        setup_times = []
        for repeat in range(REPEATS):
            order = ("stock", "batch") if (repeat + len(self.clocks)) % 2 == 0 else ("batch", "stock")
            for mode in order:
                prepared = (None,)*4
                if mode == "batch":
                    start = process_time_ns()
                    prepared = self.gram.batch(layout, [u[1:3] for u in inputs], sigma, groups)
                    setup_times.append(process_time_ns()-start)
                rows = []
                for p, u, stats in zip(points, inputs, prepared, strict=True):
                    record, _ = self.score(score, arm, p, mode, inputs=u, stats=stats)
                    rows.append(record)
                if [{k: v for k, v in c.items() if k != "native_ns"} for c in rows] != originals:
                    raise ValueError(f"Batch altered {arm}/{sweep} posterior, convergence or score")
                output[mode].append([r["native_ns"] for r in rows])
        self.rows.extend(dict(arm=arm, sweep=sweep, point=p, **c)
                         for p, c in zip(points, originals, strict=True))
        self.clocks.append(dict(arm=arm, sweep=sweep, compile_shape_width=self.gram.width(layout),
                                prepass_ns=setup_times, **output))
        return [dict(east_km=p[0], north_km=p[1], score=c["score"])
                for p, c in zip(points, originals, strict=True)]

    def sample(self, score, endpoints, **_kwargs):
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

        with patch.object(handoff.Capture, "run", self.operation(handoff.Capture.run)):
            for arm in ARMS:
                if list(endpoints[arm]) != self.archive["endpoints"][arm]:
                    raise ValueError("Reconstructed endpoint changed")
                sweeps = sweep_points(self.archive, endpoints[arm])
                for sweep in SWEEPS:
                    self.compare_strip(score, arm, sweep, sweeps[sweep])
        return dict(points=[], complete=False, evaluated_points=len(self.rows))

    def result(self):
        arms = {arm: [row for row in self.rows if row["arm"] == arm] for arm in ARMS}
        totals = {mode: [sum(sum(c[mode][i]) for c in self.clocks)
                         for i in range(REPEATS)] for mode in ("stock", "batch")}
        prep = [sum(c["prepass_ns"][i] for c in self.clocks) for i in range(REPEATS)]
        clocks = [a-b-c for a, b, c in zip(totals["stock"], totals["batch"], prep, strict=True)]
        return dict(
            rows=self.rows, clock=self.clocks, native_ns=totals, prepass_ns=prep, saving_ns=clocks,
            paired_median_saving_ns=median(clocks),
            paired_median_saving_ratio=median(value/base for value, base in zip(clocks, totals["stock"], strict=True)),
            winners={arm: min(rows, key=lambda r: r["score"])["point"] for arm, rows in arms.items()},
        )


def weak(observer):
    from early_region import before_fit
    from joint_publication import full_catalogue_route
    from leo.contracts.digests import canonical_digest
    from leo.presentation import localization_v3 as presentation
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    publication, specification = configuration()
    picked, control = small_inputs("physical")
    _, archive, _, packet, pin, offer = picked
    archive_path = Path(archive["root"])
    native = read(packet)
    if file_sha(packet) != pin.removeprefix("sha256:") or archive_identity(archive_path) != archive:
        raise ValueError("The archived weak input is no longer authentic")
    expected = control["receipt"]
    store = FastStandardAnalysisStore(WEAK_CONTROL)
    grid = store.position_grid(expected["run_id"])
    terminal = read(WEAK_CONTROL / "fast-scan-automatic-work" / expected["run_id"] / "terminal.json")
    if terminal["native_sha256"] != pin or canonical_digest(terminal) != expected["terminal_sha256"]:
        raise ValueError("The weak selected grid is bound to another native packet")
    measured = observer(grid)
    original, prepare = algo08_position.solve, algo08_position.prepare_packet
    attempt, proofs, owners = [], [], {}

    def remember(context, *args, **kwargs):
        measured.context = context
        packet = prepare(context, *args, **kwargs)
        owners.update({arm: [[row[key] for key in OWNER_KEYS] for row in rows]
                       for arm, rows in packet["rows"].items()})
        return packet

    def observed(document, reader, assets, region):
        if document is not native or reader.root != archive_path or region.document() != offer:
            raise ValueError("The weak grid changed its saved bindings")
        with ExitStack() as stack:
            live, _, _ = stack.enter_context(handoff(reader))
            stack.enter_context(reduced_grid())
            route = full_catalogue_route(v5_core.infer, reader, attempt, optimized=True)
            guarded = before_fit(route, reader, regional_bound_guard.causal_probes, proofs, live.match)
            stack.enter_context(patch.object(v5_core, "infer", guarded))
            stack.enter_context(patch.object(algo08_position, "prepare_packet", remember))
            return original(document, reader, assets, region)

    with (patch.object(algo08_position, "solve", observed),
          patch.object(presentation, "sample_position_grid", measured.sample)):
        result = solve(publication, specification, native, archive_path, offer)
    checks = dict(arms=result["arms"] == terminal["arms"], owners=owners == control["selected_rows"],
                  objective_replay=result["objective_replay"] == control["solve"]["objective_replay"])
    return dict(checks=checks, input_sha256=pin), attempt


def run(case, out):
    machine = host()
    out.mkdir()
    measured = binary = command = None

    def observer(archive):
        nonlocal measured, binary, command
        binary, command = build(out / "build")
        measured = Compare(binary, archive)
        return measured

    reconstruction, _ = (reconstruct if case == "dense" else weak)(observer)
    write(
        out / "receipt.json",
        dict(case=case, **reconstruction, **measured.result(), machine=machine,
             command=command, seals={p.name: file_sha(p) for p in (
                 binary, HERE / "location_batched_gram.py", HERE / "location_batched_gram.inc",
                 HERE / "location-batched-protocol.md", Path(__file__),
             )}),
    )
    if not all(reconstruction["checks"].values()):
        raise ValueError(f"The original selected context changed: {reconstruction['checks']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("dense", "weak"))
    parser.add_argument("out", type=Path)
    run(**vars(parser.parse_args()))
