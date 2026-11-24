"""Candidate-only variance replacement on the already selected sparse8 support."""

from collections import defaultdict
from contextlib import contextmanager
from math import sqrt
from statistics import median
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np


SIGMA_BOUNDS = 40., 600.
ARMS = ("c0", "fitted_c")


def target_scales(native, scale_hz2):
    from held_native_precision import relative_variance
    from signed_cfo_time_readout import opportunities

    return {
        ident: sqrt(scale_hz2 * relative_variance(row["factor"], 8)) if row["short"] else None
        for ident, row in opportunities(native).items() if row["factor"] is not None
    }


def replace_scales(before, ids, targets):
    before = np.asarray(before, dtype=np.float64)
    if before.shape != (len(ids),) or not np.isfinite(before).all():
        raise ValueError("The ordinary likelihood supplied invalid measurement scales")
    after = before.copy()
    for index, oid in enumerate(ids):
        sigma = targets[oid]
        if sigma is not None:
            after[index] = np.clip(sigma, *SIGMA_BOUNDS)
    return after


class FixedPrecision:
    def __init__(self, targets):
        self.targets = targets
        self.audit = dict(status="unavailable", attempts=0, variance_replacement=True)
        self.phase = None
        self.proposal = None
        self.rows = defaultdict(dict)

    @contextmanager
    def stage(self, phase):
        old = self.phase
        self.phase = phase
        try:
            yield
        finally:
            self.phase = old

    def record(self, p, role, ids, before, after):
        key = (self.phase, ARMS[int(p.fitted_c)], role)
        records = self.rows[key]
        for oid, old, new in zip(ids, before, after, strict=True):
            entry = (float(old), float(new))
            if records.setdefault(oid, entry) != entry:
                raise ValueError("One fixed likelihood row received different measurement precision")

    def summary(self):
        phases = {}
        for (when, arm, role), values in self.rows.items():
            entry = phases.setdefault(when, {}).setdefault(arm, {}).setdefault(role, {})
            for aperture in (8,20):
                rows = [(oid, before, after) for oid,(before,after) in values.items()
                        if (self.targets[oid] is None) == (aperture == 20)]
                if not rows:
                    continue
                before, after = [r[1] for r in rows], [r[2] for r in rows]
                proposed = [self.targets[r[0]] for r in rows] if aperture == 8 else []
                entry[str(aperture)] = dict(
                    samples=len(rows), changed=sum(a != b for a,b in zip(before,after,strict=True)),
                    floor_hits=sum(value <= SIGMA_BOUNDS[0] for value in proposed),
                    ceiling_hits=sum(value >= SIGMA_BOUNDS[1] for value in proposed),
                    before_hz=[min(before), median(before), max(before)],
                    after_hz=[min(after), median(after), max(after)])
        return dict(self.audit, scopes=phases)

    def repair(self, prepared, ordinary, observed):
        from leo.analysis.localization_v3 import event_position
        from leo.analysis.localization_v3.history_policy import pair_passes

        audit = {"decision": "rejected"}
        observed["local_future_repair"] = audit   # Original postfit follow-up uses this existing port.
        if self.audit["attempts"] or observed.get("signed", {}).get("status") != "accepted":
            audit["reason"] = "no eligible ordinary signed pair"
            return prepared, ordinary
        self.audit["attempts"] += 1
        scan = ordinary["scan"]
        values = (ordinary["scan"], ordinary["node"], ordinary["keep"])
        options = (ordinary["powers"], ordinary["means"], ordinary["model"], [], ordinary["entries"])
        self.audit["incumbent_noise"] = {
            k: scan.fixed_window_noise.get(k) for k in
            ("constant_radio_sigma_hz", "extra_parameter_BIC_gain", "heteroscedastic_selected", "noise_samples")
        }
        started = perf_counter_ns(), process_time_ns()
        try:
            with self.stage("fit"):
                arms = {arm: event_position.refit(*values, arm, *options) for arm in ARMS}
            if not pair_passes(arms, include_linear=True, half_width_km=scan.search_region.half_width_km):
                raise ValueError("original paired fit gate declined weighted result")
        except (AssertionError, KeyError, ValueError, np.linalg.LinAlgError) as error:
            self.audit["status"] = "fit_fallback"
            audit["reason"] = f"{type(error).__name__}: {error}"
            return prepared, ordinary
        finally:
            self.audit["fit_cpu_ns"] = process_time_ns()-started[1]
            self.audit["fit_wall_ns"] = perf_counter_ns()-started[0]
        self.proposal = dict(ordinary, arms=arms)
        self.audit.update(status="weighted_proposal", fit_arms={
            arm: dict(position=list(record["endpoint_latlon"]), rf_rms_hz=float(record["RMS_hz"]))
            for arm, record in arms.items()})
        audit["decision"] = "proposed"
        return prepared, self.proposal

    @contextmanager
    def install(self):
        from leo.analysis.localization_v3 import event_position, position, predictive_linear
        from short_margin_variance import observation_ids, set_normal_scales
        from tools import algo08_position
        import joint_publication

        constructor, linear, original_packet, route = (
            position.NormalPosition.__init__, predictive_linear.linear_geometry, algo08_position.selected_packet,
            joint_publication.full_catalogue_route,
        )
        if event_position.linear_geometry is not linear:
            self.audit["status"] = "unsupported_predictive_binding"
            yield
            return

        def normal(p, *args, **kwargs):
            constructor(p, *args, **kwargs)
            if self.phase is not None:
                ids = observation_ids(p.scan, p.members)
                original = p.point_noise
                sigma = replace_scales(original, ids, self.targets)
                kept = [oid for oid, live in zip(ids, p.keep, strict=True) if live]
                self.record(p, "curved", kept, original[p.keep], sigma[p.keep])
                set_normal_scales(p, sigma)

        def predictive(p, entries):
            view, values, sigma, groups, slices = linear(p, entries)
            if self.phase is not None:
                ids = observation_ids(p.scan, (entry["track_index"] for entry in entries))
                updated = replace_scales(sigma, ids, self.targets)
                self.record(p, "predictive", ids, sigma, updated)
                sigma = updated
            return view, values, sigma, groups, slices

        def prepare(prepared, chosen, fit):
            if self.proposal is not None and chosen is self.proposal:
                with self.stage("evidence"):
                    packet = original_packet(prepared, chosen, fit)
                if not packet["position_grid"]["complete"]:
                    raise ValueError("The weighted evidence cannot publish an incomplete grid")
                self.audit["weighted_evidence"] = True
                return packet
            return original_packet(prepared, chosen, fit)

        def view(installed, reader, attempts, *, optimized=False, postfit_repair=None):
            if postfit_repair is None:
                postfit_repair = self.repair
            else:
                self.audit["status"] = "postfit_port_unavailable"
            return route(installed, reader, attempts, optimized=optimized, postfit_repair=postfit_repair)

        with (patch.object(position.NormalPosition, "__init__", normal),
              patch.object(predictive_linear, "linear_geometry", predictive),
              patch.object(event_position, "linear_geometry", predictive),
              patch.object(algo08_position, "selected_packet", prepare),
              patch.object(joint_publication, "full_catalogue_route", view)):
            yield
