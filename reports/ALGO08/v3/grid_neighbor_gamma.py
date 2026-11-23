"""Probe a tighter neighbor-warm convergence rule in the checked posterior exporter."""

import ctypes as ct
from hashlib import sha256
from pathlib import Path
import subprocess
from time import process_time_ns

import numpy as np


TOLERANCE = {"warm": 1e-7, "tight": 1e-9}
GRID_LIMIT = 1e-5
MODES = ("stock", "warm", "tight")
MAX_GROUPS = 2048


def prepared_source(source):
    patches = (
        ("double *lower,int32_t *order,int *exported) {",
         "double *lower,int32_t *order,int *exported,const double *initial_rate,"
         "const double *initial_prior,double tolerance,double *final_prior) {"),
        ("    double change=INFINITY,logdet=0.;int performed=0;",
         "    if(initial_rate)memcpy(rate,initial_rate,k*sizeof(double));\n"
         "    if(initial_prior && t)memcpy(prate,initial_prior,t*sizeof(double));\n"
         "    double change=INFINITY,logdet=0.;int performed=0;"),
        ("(iteration>0 && change<1e-5)", "(iteration>0 && change<tolerance)"),
        ("    memcpy(returned_rates,rate,k*sizeof(double));", "    memcpy(returned_rates,rate,k*sizeof(double));\n"
         "    if(t)memcpy(final_prior,prate,t*sizeof(double));"),
    )
    for old, new in patches:
        if source.count(old) != 1:
            raise ValueError("The pinned posterior exporter changed")
        source = source.replace(old, new)
    return source


def build(root):
    from leo.analysis.localization_v4 import native_bound
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

    if sha256(Path(handoff.__file__).read_bytes()).hexdigest() != (
            "aa5d7ab17ce82e4bd64e463de0fddf710275634cf48675cf6076eeba6c184831"):
        raise ValueError("The pinned posterior export source changed")
    handoff.build(root / "stock-build.so")
    source = root / "neighbor.c"
    source.write_text(prepared_source((root / "stock-build.c").read_text()))
    binary = root / "neighbor.so"
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(source),
                    "-lm", "-o", str(binary)], check=True, timeout=30)
    return binary


def sweep_points(grid, endpoint):
    by_coordinate = {(row["east_km"], row["north_km"]): row for row in grid["points"]}
    east, north = endpoint
    sweeps = (
        ("local", [(east+shift, north+.5) for shift in (-1.5, -1., -.5, 0.)]),
        ("centre", [(x, 0.) for x in (0., 3.125, 6.25, 9.375)]),
        ("south_face", [(x, -12.5) for x in (-12.5, -9.375, -6.25, -3.125)]),
    )
    return {name: [by_coordinate[point] for point in points] for name, points in sweeps}


def clear_grid_cache(problem):
    closure = dict(zip(problem.calculate.__code__.co_freevars, problem.calculate.__closure__, strict=True))
    cached = closure["calculate"].cell_contents
    if (not hasattr(cached, "cache_clear") or not hasattr(cached, "__wrapped__")
            or cached.__wrapped__.__qualname__ != "cached.<locals>.calculate"):
        raise ValueError("Expected the released position cache")
    cached.cache_clear()


class Compare:
    def __init__(self, binary, archive):
        self.library = ct.CDLL(str(binary))
        self.variant = self.library.nb_run_posterior
        self.archive = archive
        self.context = None
        self.cell = None
        self.state = None
        self.rows = []

    def native(self, original):
        def export(capture, owner, operation, args):
            if self.cell is None or "kernel_cpu_ns" in self.cell:
                raise ValueError("Expected a single real posterior per audited point")
            mode = self.cell["mode"]
            seed = self.state if mode == "warm" else None
            prior = np.empty(args[11])
            if mode != "stock":
                self.variant.argtypes = operation.argtypes + [ct.c_void_p, ct.c_void_p, ct.c_double, ct.c_void_p]
                self.variant.restype = operation.restype

            def run(*arguments):
                if mode == "stock":
                    return operation(*arguments)
                cold = ct.c_void_p(), ct.c_void_p()
                noise, phases = cold if seed is None else tuple(ct.c_void_p(x.ctypes.data) for x in seed)
                return self.variant(*arguments, noise, phases, TOLERANCE[mode], ct.c_void_p(prior.ctypes.data))

            start = process_time_ns()
            status = original(capture, owner, run, args)
            self.cell.update(kernel_cpu_ns=process_time_ns()-start, status=status, seeded=seed is not None,
                             export=capture.exported.value, width=capture.width)
            if status == 0:
                self.cell.update(updates=ct.cast(args[25], ct.POINTER(ct.c_int))[0],
                                 final_change=ct.cast(args[24], ct.POINTER(ct.c_double))[1])
                if mode == "warm" and capture.exported.value == 1 and self.cell["final_change"] < TOLERANCE[mode]:
                    g = self.context["problems"][self.cell["arm"]][0]
                    count = len(np.unique(g.noise_groups[g.keep]))
                    if not 0 < count <= MAX_GROUPS:
                        raise ValueError("Unsupported saved noise-group layout")
                    self.state = (np.ctypeslib.as_array(ct.cast(args[26], ct.POINTER(ct.c_double)), shape=(count,)).copy(), prior)
            if mode == "warm" and (status != 0 or capture.exported.value != 1 or self.cell["final_change"] >= TOLERANCE[mode]):
                self.state = None
            return status

        return export

    def sample(self, score, endpoints, **_kwargs):
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff
        from unittest.mock import patch

        with patch.object(handoff.Capture, "run", self.native(handoff.Capture.run)):
            for arm, endpoint in endpoints.items():
                problem, _ = self.context["problems"][arm]
                if list(endpoint) != self.archive["endpoints"][arm]:
                    raise ValueError("The reconstructed endpoint changed")
                for sweep, rows in sweep_points(self.archive, endpoint).items():
                    self.state = None
                    for index, row in enumerate(rows):
                        point = row["east_km"], row["north_km"]
                        observations = {}
                        for mode in MODES[index % 3:] + MODES[:index % 3]:
                            clear_grid_cache(problem)
                            self.cell = dict(mode=mode, arm=arm)
                            value = score(arm, point)
                            observations[mode] = dict(self.cell, score=value)
                        self.rows.append(dict(arm=arm, sweep=sweep, index=index, point=point,
                                              archived_score=row["scores"][arm], observations=observations))
            self.cell = None
        return dict(points=[], complete=False, evaluated_points=24)


def score_rows(rows):
    if len(rows) != 24:
        raise ValueError("Expected the original three four-site sweeps in each calibration arm")
    report = {}
    for arm in ("c0", "fitted_c"):
        selected = [row for row in rows if row["arm"] == arm]
        if len(selected) != 12:
            raise ValueError("Expected all sites for both arms")
        got = [row["observations"] for row in selected]
        differences = {ref: [o["warm"]["score"]-o[ref]["score"] for o in got] for ref in ("stock", "tight")}
        report[arm] = dict(
            archived_stock_exact=all(x["stock"]["score"] == y["archived_score"] for x, y in zip(got, selected, strict=True)),
            all_checked=all(o[mode]["status"] == 0 and o[mode]["export"] == 1 for o in got for mode in MODES),
            converged=all(o[mode].get("final_change", np.inf) < threshold for o in got
                          for mode, threshold in dict(stock=1e-5, **TOLERANCE).items()),
            score_delta={ref: dict(min=min(d), max=max(d), over_limit=sum(abs(x) > GRID_LIMIT for x in d))
                         for ref, d in differences.items()},
            totals={mode: {key: sum(o[mode].get(key, 0) for o in got) for key in ("updates", "kernel_cpu_ns")}
                    for mode in MODES}, warm_seeds=sum(o["warm"]["seeded"] for o in got),
            sampled_minimum={mode: int(np.argmin([o[mode]["score"] for o in got])) for mode in MODES},
        )
    return report
