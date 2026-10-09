"""Unfrozen research adapter. Importing performs no input access or fitting."""

import importlib.util
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_search import distinct_basins, hierarchical_search
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration

SOURCE = Path(__file__).parents[1] / "2026_10_09_position_error_iter114/fixed_bank.py"
SPEC = importlib.util.spec_from_file_location("fixed_bank114_for116", SOURCE)
FIXED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXED)


def rescore(
    objective, vector, full_bank, expected_native, *, batch_size=64, predictor=predict_orbits
):
    """Native coarse objective only; reject extra model/prior blocks implicitly lost."""
    if type(objective) is not Hard60Objective:
        raise ValueError("only the ordinary coarse Hard60Objective is supported")
    vector = np.asarray(vector, float)
    if vector.shape != (objective.size,) or not np.isfinite(vector).all():
        raise ValueError("invalid physical vector")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("positive integer batch size required")
    if not np.isfinite(expected_native):
        raise ValueError("finite native objective binding required")
    old = objective.bank
    mapping = {int(identifier): i for i, identifier in enumerate(full_bank.numbers)}
    if not set(old.numbers).issubset(mapping):
        raise ValueError("full bank is not a superset")
    indices = [mapping[int(identifier)] for identifier in old.numbers]
    for field in ("position_km", "velocity_km_s"):
        if not np.array_equal(getattr(old, field), getattr(full_bank, field)[indices]):
            raise ValueError("old orbital states changed")
    if not np.array_equal(old.nodes_s, full_bank.nodes_s):
        raise ValueError("ephemeris nodes changed")
    relative = objective.basis @ vector[8:]
    transport = FIXED.transport_timing(old.numbers, full_bank.numbers, vector[7], relative)
    observations = objective.observations
    shifts = transport["physical_shifts_s"]
    if (
        observations.times_s.min() + shifts.min() < full_bank.nodes_s[0]
        or observations.times_s.max() + shifts.max() > full_bank.nodes_s[-1]
    ):
        raise ValueError("transported shifts exceed ephemeris support")
    receiver = objective.design @ vector[2:7] + objective.baseline
    prediction, visible, _, _ = predictor(
        old, observations, objective.prior, vector[:2], vector[7] + relative, derivatives=False
    )
    prediction = prediction + receiver[:, None]
    penalty = float(
        0.5 * (vector[7] / objective.score.common_sigma_s) ** 2
        + 0.5 * np.sum((relative / objective.score.relative_sigma_s) ** 2)
    )
    options = dict(score=objective.score, penalty=penalty)
    native = FIXED.streamed_score(
        observations.measured_hz,
        [(prediction, visible)],
        candidate_count=len(old.numbers),
        **options,
    )
    if abs(native["objective"] - expected_native) > 1e-6:
        raise ValueError("native objective did not reproduce")
    normalization = FIXED.streamed_score(
        observations.measured_hz,
        [(prediction, visible)],
        candidate_count=len(full_bank.numbers),
        **options,
    )
    old_lookup = {int(identifier): i for i, identifier in enumerate(old.numbers)}

    def batches():
        for start in range(0, len(full_bank.numbers), batch_size):
            ix = list(range(start, min(len(full_bank.numbers), start + batch_size)))
            bank = full_bank.select(ix)
            p, v, _, _ = predictor(
                bank, observations, objective.prior, vector[:2], shifts[ix], derivatives=False
            )
            p = p + receiver[:, None]
            for j, identifier in enumerate(bank.numbers):
                if int(identifier) in old_lookup:
                    previous = old_lookup[int(identifier)]
                    if not np.allclose(
                        p[:, j], prediction[:, previous], rtol=0, atol=1e-9
                    ) or not np.array_equal(v[:, j], visible[:, previous]):
                        raise ValueError("old prediction or visibility changed in streamed bank")
            yield p, v

    common = FIXED.streamed_score(
        observations.measured_hz, batches(), candidate_count=len(full_bank.numbers), **options
    )
    if common["supplied_columns"] != len(full_bank.numbers):
        raise ValueError("incomplete whole-prior score")
    return {
        "native": native,
        "normalization_only": normalization,
        "fixed": common,
        "transport": transport,
    }


class PointEvaluator:
    """In-memory preparation only; an execution driver still needs durable receipts."""

    def __init__(
        self,
        observations,
        bank,
        prior,
        tracks,
        *,
        bootstrap=bootstrap_position,
        fitter=fit_position,
        scorer=rescore,
    ):
        self.observations, self.bank, self.prior, self.tracks = observations, bank, prior, tracks
        self.bootstrap, self.fitter, self.scorer = bootstrap, fitter, scorer
        self.seeds, self.rows = {}, {}

    def __call__(self, east, north, arm):
        if arm not in ("fitted-c", "zero-c"):
            raise ValueError("unknown RF arm")
        key, point = (float(east), float(north), arm), (float(east), float(north))
        if key in self.rows:
            return self.rows[key]
        # Ordinary production discovery seed is shared across c arms.
        if point not in self.seeds:
            self.seeds[point] = self.bootstrap(
                self.observations,
                self.bank,
                self.prior,
                point,
                self.tracks,
                maximum_seconds=5.0,
                orbit_predictor=predict_orbits,
            )
        seed = self.seeds[point]
        model = Hard60Objective(
            self.observations,
            self.bank.select(list(seed.satellite_indices)),
            self.prior,
            HARD60_SCORE,
        )
        fit = self.fitter(
            model,
            seed.vector.copy(),
            rf_arm=arm,
            fixed_position=True,
            maximum_seconds=5.0,
            maximum_iterations=200,
            slope_half_width_hz_s=60.0,
        )
        if arm == "zero-c" and fit.vector[6] != 0:
            raise ValueError("c=0 lock violated")
        if not np.array_equal(np.asarray(fit.vector[:2]), np.asarray(point)):
            raise ValueError("fixed-position fit moved")
        scores = self.scorer(model, fit.vector, self.bank, fit.objective)
        row = {"point": point, "arm": arm, "fit": fit, "scores": scores}
        self.rows[key] = row
        return row


def search_pair(evaluator, prior, arm, *, configuration=None):
    """Same hierarchy and retention, scalar queue score is the only intervention."""
    config = configuration or Hard60Configuration()
    results = {}
    for mode in ("native", "fixed"):
        search = hierarchical_search(
            lambda e, n, mode=mode: evaluator(e, n, arm)["scores"][mode]["objective"],
            radius_km=prior.radius_km,
            levels_km=config.levels_km,
            budget_points=config.point_budget,
            edge_priority=config.edge_priority,
        )
        regions = distinct_basins(
            search, count=config.basins, minimum_separation_km=config.basin_separation_km
        )
        results[mode] = {"search": search, "regions": regions}
    return results
