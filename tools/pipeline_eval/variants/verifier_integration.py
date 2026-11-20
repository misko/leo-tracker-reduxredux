"""Offer a reusable C verifier to one original scanner's post-coarse probe path."""

import ast
import ctypes as c
import inspect
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

RATE = 10_000_000
WINDOW = 200_000
EPOCHS = 13_333
CAPACITY = 8
FRAC_COMPLETE = 4
GUARD = 8 | 16 | 32 | 64


class Seed(c.Structure):
    _fields_ = [
        ("epoch", c.c_uint),
        ("bins", c.c_uint),
        ("absolute_hz", c.c_double),
        ("residual_hz", c.c_double),
    ]


class Result(c.Structure):
    _fields_ = [
        *(
            (name, c.c_uint)
            for name in (
                "seed_index",
                "fine_winner",
                "conditioned_winner",
                "conditioned_bins",
                "flags",
                "stage_frames",
            )
        ),
        *(
            (name, c.c_double)
            for name in (
                "fine_residual_hz",
                "acquired_hz",
                "acquired_residual_hz",
                "acquire",
                "verify",
                "verify_control",
                "conditioned",
                "integer_exact",
                "integer_control",
                "integer_residual_hz",
                "offset_samples",
                "curvature",
                "fractional_exact",
                "fractional_control",
                "fractional_residual_hz",
            )
        ),
        ("exact_grid", c.c_double * 5),
        ("control_grid", c.c_double * 5),
        ("conditioned_grid", c.c_double * 42),
        ("conditioned_scores", c.c_double * 42),
    ]


def coarse_prefix(acquisition):
    """Call the bound installed coarse source, preserving its live globals and selector."""
    source = inspect.getsource(acquisition.acquire_symbolwise)
    (function,) = ast.parse(source).body
    stop = next(
        i
        for i, row in enumerate(function.body)
        if isinstance(row, ast.AnnAssign)
        and isinstance(row.target, ast.Name)
        and row.target.id == "candidates"
    )
    loop = function.body[stop + 1]
    if (
        not isinstance(loop, ast.For)
        or ast.unparse(loop.target) != "(coarse_score, coarse_epoch, coarse_residual)"
        or ast.unparse(loop.iter) != "retained"
    ):
        raise ValueError("installed acquisition does not expose the qualified coarse boundary")
    function.body = [
        *function.body[:stop],
        ast.parse("return retained, score_maps, epoch_count, config").body[0],
    ]
    function.name = "bound_original_coarse_prefix"
    tree = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    local = {}
    exec(compile(tree, str(Path(acquisition.__file__)), "exec"), vars(acquisition), local)
    return local[function.name]


def grid_seeds(acquisition, prefix, calibration):
    retained, maps, epoch_count, cfg = prefix
    seeds = []
    for _, coarse_epoch, coarse_residual in retained:
        refined = acquisition._refine_epoch(maps[coarse_residual], coarse_epoch, epoch_count)
        residual = acquisition._bounded_grid(
            max(cfg.residual_cfo_min_hz, coarse_residual - cfg.fine_cfo_radius_hz),
            min(cfg.residual_cfo_max_hz, coarse_residual + cfg.fine_cfo_radius_hz),
            cfg.fine_cfo_step_hz,
        )
        absolute = tuple(calibration.absolute_cfo_hz(hz) for hz in residual)
        if (
            not 2 <= len(absolute) <= 321
            or acquisition._constant_grid_step(absolute) != 500
            or acquisition._constant_grid_step(residual) != 500
        ):
            return None
        seeds.append((int(refined), len(absolute), absolute[0], residual[0]))
    return seeds


class Port:
    def __init__(self, library, acquisition, detector, scores, edge):
        if c.sizeof(Seed) != 24 or c.sizeof(Result) != 896:
            raise ValueError("portable verifier ABI changed")
        self.acquisition, self.detector, self.scores = acquisition, detector, scores
        self.fractional_source = import_module(f"{scores.__package__}.fast_scan_fractional")
        self.edge = acquisition.StarlinkEdge(edge)
        self.coarse = coarse_prefix(acquisition)
        self.native = c.CDLL(str(library))
        create = self.native.portable_verifier_create
        create.restype = c.c_void_p
        create.argtypes = (c.c_void_p, c.c_void_p)
        self.native.portable_verifier_free.argtypes = (c.c_void_p,)
        self.native.portable_verifier_free.restype = None
        workspace = self.native.portable_verifier_workspace_bytes
        workspace.argtypes = ()
        workspace.restype = c.c_size_t
        self.workspace_bytes = workspace()
        self.batch = self.native.verifier_integration_batch
        self.batch.argtypes = (
            c.c_void_p,
            c.c_void_p,
            c.c_uint,
            c.POINTER(Seed),
            c.c_uint,
            c.c_double,
            c.c_double,
            c.c_double,
            c.POINTER(Result),
        )
        self.batch.restype = c.c_int
        self.templates = tuple(
            np.ascontiguousarray(
                acquisition.qin_edge_pilot_frame(RATE, edge, symbol_roll=roll), dtype=np.complex128
            )
            for roll in (0, acquisition.CONTROL_SYMBOL_ROLL)
        )
        if any(t.shape != (EPOCHS,) for t in self.templates):
            raise ValueError("portable templates require the qualified 10 MS/s geometry")
        self.context = create(*(t.ctypes.data for t in self.templates))
        if not self.context:
            raise MemoryError("portable verifier context initialization failed")
        self.results = (Result * CAPACITY)()
        self.seeds = (Seed * CAPACITY)()
        self.window = self.loaded = None
        self.calls = []

    def close(self):
        if self.context:
            self.native.portable_verifier_free(self.context)
            self.context = None

    @contextmanager
    def bind(self, window):
        if self.window is not None or not self.context:
            raise RuntimeError("portable verifier requires a live context and one resident visit")
        self.window = window
        self.loaded = None
        self.calls.clear()
        try:
            yield
        finally:
            self.window = self.loaded = None

    def supported(self, probe, config, cfg, edge, lane):
        return (
            self.window is not None
            and lane in (0, 1)
            and edge == self.edge
            and config.sample_rate_hz == self.window.sample_rate_hz == RATE
            and config.scheduled_probe_count == 1
            and config.probe_samples == WINDOW
            and config.dwell_samples == WINDOW
            and config.glrt64_margin_gate == 0.025
            and cfg.retained_candidate_count == config.maximum_acquisition_candidates <= CAPACITY
            and cfg.minimum_frame_support == 2
            and cfg.fine_cfo_step_hz == 500
            and cfg.conditioned_cfo_step_hz == 100
            and cfg.conditioned_cfo_radius_hz == 2_000
            and cfg.acquire_symbols == self.acquisition.DEFAULT_ACQUIRE_SYMBOLS
            and cfg.verify_symbols == self.acquisition.DEFAULT_VERIFY_SYMBOLS
            and probe.shape == (WINDOW,)
            and probe.dtype == np.complex128
            and probe.flags.c_contiguous
            and self.window.samples.dtype.str == "<i2"
            and self.window.samples.shape == (WINDOW, 2, 2)
            and self.window.samples.flags.c_contiguous
        )

    def fractional(self, row, seed):
        s = self.fractional_source
        complete = bool(row.flags & FRAC_COMPLETE)
        return s.FractionalEpochRefinement(
            integer_epoch_sample=seed.epoch,
            frame_period_samples=RATE / 750,
            wrapped_epoch_samples=s.circular_epoch_grid(seed.epoch, RATE),
            exact_score_grid=tuple(row.exact_grid),
            control_score_grid=tuple(row.control_grid),
            status=s.FractionalEpochStatus("complete" if complete else "unbracketed"),
            fractional_epoch_offset_samples=row.offset_samples if complete else None,
            log_curvature=row.curvature if complete else None,
            fractional_exact_score=row.fractional_exact if complete else None,
            fractional_control_score=row.fractional_control if complete else None,
            fractional_residual_cfo_hz=row.fractional_residual_hz if complete else None,
            fractional_tracking_cfo_hz=(row.acquired_hz + row.fractional_residual_hz)
            if complete
            else None,
            fractional_margin=(row.fractional_exact - row.fractional_control) if complete else None,
        )

    def evaluate(
        self,
        original,
        probe,
        configuration,
        calibration,
        *,
        edge,
        acquisition_config,
        receiver_id,
        probe_index,
    ):
        cfg = acquisition_config
        detail = dict(
            receiver=receiver_id,
            anchors=cfg.anchor_symbols,
            candidates=0,
            route="unsupported_geometry",
            converted=False,
            native_cpu_ns=0,
            native_wall_ns=0,
            coarse_cpu_ns=0,
            seeds=[],
            flags=[],
        )
        self.calls.append(detail)

        def run():
            return original(
                probe,
                configuration,
                calibration,
                edge=edge,
                acquisition_config=cfg,
                receiver_id=receiver_id,
                probe_index=probe_index,
            )

        if probe_index != 0 or not self.supported(probe, configuration, cfg, edge, receiver_id):
            return run()
        raw = self.window.samples
        if not (
            np.array_equal(probe.real, raw[:, receiver_id, 0])
            and np.array_equal(probe.imag, raw[:, receiver_id, 1])
        ):
            raise ValueError("coarse input and the bound physical CI16 lane disagree")
        start = process_time_ns()
        prefix = self.coarse(probe, RATE, calibration, edge=edge, config=cfg)
        if isinstance(prefix, self.acquisition.SymbolwiseAcquisitionResult):
            detail.update(route="empty", coarse_cpu_ns=process_time_ns() - start)
            return self.detector._ProbeEvaluation((), ())
        seeds = grid_seeds(self.acquisition, prefix, calibration)
        detail["coarse_cpu_ns"] = process_time_ns() - start
        if seeds is None:
            detail["route"] = "unsupported_fine_grid"
            return run()
        for i, seed in enumerate(seeds):
            self.seeds[i] = Seed(*seed)
        converted = self.loaded != receiver_id
        cpu, wall = process_time_ns(), perf_counter_ns()
        status = self.batch(
            self.context,
            raw.ctypes.data if converted else None,
            receiver_id,
            self.seeds,
            len(seeds),
            calibration.center_hz,
            cfg.residual_cfo_min_hz,
            cfg.residual_cfo_max_hz,
            self.results,
        )
        detail.update(
            converted=converted,
            native_cpu_ns=process_time_ns() - cpu,
            native_wall_ns=perf_counter_ns() - wall,
            seeds=seeds,
            candidates=len(seeds),
        )
        self.loaded = receiver_id
        if status:
            detail["route"] = "unsupported_native"
            return run()
        rows = self.results[: len(seeds)]
        detail["flags"] = [r.flags for r in rows]
        if any(row.flags & GUARD for row in rows):
            detail["route"] = "numeric_guard"
            return run()
        records = [self.seeds[row.seed_index] for row in rows]
        candidates = tuple(
            SimpleNamespace(
                rank=rank, refined_epoch_sample=seed.epoch, absolute_cfo_hz=row.acquired_hz
            )
            for rank, (row, seed) in enumerate(zip(rows, records, strict=True))
        )
        integer = tuple(
            self.scores._score(
                self.scores.PilotMethod.GLRT64,
                row.integer_exact,
                row.integer_control,
                row.integer_residual_hz,
                row.acquired_hz,
            )
            for row in rows
        )
        fractional = tuple(
            self.fractional(row, seed) for row, seed in zip(rows, records, strict=True)
        )
        detail["route"] = "portable"
        with patch.multiple(
            self.detector,
            acquire_symbolwise=lambda *a, **k: SimpleNamespace(candidates=candidates),
            conditioned_glrt64_scores=lambda *a, **k: integer,
            refine_glrt64_epochs=lambda *a, **k: fractional,
        ):
            return run()

    @contextmanager
    def route(self):
        original = self.detector._evaluate_probe

        def wrapped(*args, **kwargs):
            return self.evaluate(original, *args, **kwargs)

        with patch.object(self.detector, "_evaluate_probe", wrapped):
            yield
