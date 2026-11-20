"""Refit the sealed oracle owners with one saturated phase bound released."""

import argparse
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS, distance_km
from . import conditional_support as diagnostic
from . import owner_factor as owner
from . import owner_factor_models as models

LIMIT = 22.5


def expanded_fit(rows, count, half, arm, affected):
    lean = models.lean
    original_solver = lean.lsq_linear
    active = np.array(sorted({r.orbit for r in rows}))

    def solve(matrix, right, *, bounds, **options):
        lower, upper = (b.copy() for b in bounds)
        if not np.array_equal(upper[-len(active) :], np.full(len(active), lean.PHASE_BOUND_S)):
            raise ValueError("phase columns changed in the original model")
        target = np.flatnonzero(np.isin(active, tuple(affected))) + len(upper) - len(active)
        lower[target], upper[target] = -LIMIT, LIMIT
        return original_solver(matrix, right, bounds=(lower, upper), **options)

    with patch.object(lean, "lsq_linear", solve):
        return lean.fit(rows, count, half, arm)


def refit(case, prior_root):
    reference, groups, _ = diagnostic.factors(case)
    locked = owner._blind(prior_root)[case]
    expected = owner._read(prior_root / "input-lock.json")
    privileged = prior_root / "privileged-inputs.jsonl.gz"
    if owner._sha(privileged) != expected["privileged_sha256"]:
        raise ValueError("original privileged owner mask differs from sealed source")
    identified = next(r for r in owner._load(privileged) if r["case"] == case)
    packet = locked["packet"]
    masks, _ = models.join(identified["factors"], locked["rows"])
    original = models.lean.fit
    original_knots = models.exact.grid._knots

    def padded(d, s):
        nominal = original_knots(d, s)
        if s != 5:
            return nominal
        extra = 5 * np.arange(1, 5)
        return np.r_[nominal[0] - extra[::-1], nominal, nominal[-1] + extra]

    with patch.object(models.exact.grid, "_knots", padded):
        tile, region, lookup = models.bank(packet)
    rows = [r for r in masks["full"] if r["v5_owner"] in lookup]
    fragments = models.fragments(rows, "v5", "v5", lookup)
    results = {}
    truth = next(r for r in owner.corpus.references("ds26-common127") if r["id"] == case)["truth"]
    for arm in ARMS:
        affected = {
            point["norad"]
            for group in groups[arm].values()
            for point in group
            if abs(point["phase_s"]) == models.lean.PHASE_BOUND_S
        }
        if not affected:
            raise ValueError("these extra components have no phase lever to test")
        affected_indices = {lookup[n] for n in affected}
        extra_ids = {r["id"] for g in groups[arm].values() for r in g}

        def fit(rows, n, h, a, affected=affected_indices):
            # Bind the exact original entrypoint while constrained phases get a wider box.
            with patch.object(models.lean, "fit", original):
                return expanded_fit(rows, n, h, a, affected)

        half = float(packet["offer"].get("width_km", 25.0)) / 2
        result = {}
        for mode, fn in (("fixed", original), ("release_saturation", fit)):
            with patch.object(models.lean, "fit", fn):
                xy, phases, radios, objective, receipt = models._least_fit(
                    fragments, tile, region, half, arm
                )
            site, latlon = region.site(xy)
            residuals = {}
            for g, p, radio in zip(fragments, phases, radios, strict=True):
                estimate = models.exact.project(tile, g.orbit, g.t, site, p, g.rf)[0] + radio
                residuals.update((r["id"], e) for r, e in zip(g.rows, g.y - estimate, strict=True))
            result[mode] = dict(
                latlon=None,
                forced_latlon=latlon,
                forced_error_km=distance_km(latlon, truth),
                phases_s={
                    str(g.norad): p
                    for g, p in zip(fragments, phases, strict=True)
                    if g.norad in affected
                },
                common_rms_hz=diagnostic.rms(
                    np.array([v for k, v in residuals.items() if k not in extra_ids])
                ),
                added_rms_hz=diagnostic.rms(
                    np.array([v for k, v in residuals.items() if k in extra_ids])
                ),
                total_rms_hz=diagnostic.rms(np.array(list(residuals.values()))),
                objective=objective,
                exact_steps=receipt["accepted_steps"],
            )
        earlier = reference["estimates"]["v5_full_lean"]["arms"][arm]
        result["earlier_fixed"] = dict(
            forced_latlon=earlier["forced_latlon"],
            forced_error_km=distance_km(earlier["forced_latlon"], truth),
            total_rms_hz=earlier["rf_rms_hz"],
        )
        results[arm] = result
    return dict(
        id=case,
        status="forced_only",
        arms=results,
        input_sha256=expected["privileged_sha256"],
        source_position_sha256=expected["blind_lock_sha256"],
        bound_s=LIMIT,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=diagnostic.CASES)
    parser.add_argument("--prior", type=Path, required=True)
    args = parser.parse_args()
    save_json(diagnostic.OUTPUT / f"{args.case}-oracle-refit.json", refit(args.case, args.prior))
