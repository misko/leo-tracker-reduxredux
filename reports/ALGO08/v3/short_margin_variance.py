"""Apply one frozen short-verifier information factor on fixed signed support."""

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from unittest.mock import patch

import numpy as np


MIN_INFORMATION = 0.5
MAX_SIGMA_HZ = 600.


def variance_factors(native):
    from discovery_margin import factor_weights

    information, census = factor_weights(native, unit=False)
    return {oid: 1. / max(MIN_INFORMATION, value) for oid, (value, _) in information.items()}, census


def scales(base, rows, factors, *, weighted):
    sigma = np.asarray(base, dtype=np.float64)
    if (sigma.shape != (len(rows),) or not np.isfinite(sigma).all()
            or np.any((sigma < 40.) | (sigma > MAX_SIGMA_HZ))):
        raise ValueError("Expected aligned original finite measurement scales between 40 and 600 Hz")
    variance = np.array([factors[oid] for oid in rows], dtype=np.float64)
    if not weighted:
        return sigma
    short = variance > 1.
    output = sigma.copy()
    output[short] = np.minimum(MAX_SIGMA_HZ, sigma[short] * np.sqrt(variance[short]))
    return output


def observation_ids(scan, members):
    return [oid for i in members for oid in scan.tracks[i]["observation_ids"]]


def set_normal_scales(model, sigma):
    model.point_noise = sigma
    model.diagonal_logvolume = float(2 * np.sum(model.point_power * np.log(sigma / 40)))
    model.noise_volume = float(2 * np.log(sigma[model.keep] / 40).sum())


class Trial:
    def __init__(self, factors, *, weighted):
        self.factors = factors
        self.weighted = weighted
        self.stage = ContextVar("signed_measurement_variance", default=None)
        self.chosen = None
        self.supports = {}
        self.tallies = defaultdict(dict)
        self.calls = defaultdict(int)

    @contextmanager
    def active(self, stage):
        token = self.stage.set(stage)
        try:
            yield
        finally:
            self.stage.reset(token)

    def record(self, arm, role, ids, before, after):
        key = (self.stage.get(), "fitted_c" if arm else "c0", role)
        self.calls[key] += 1
        for oid, original, candidate in zip(ids, before, after, strict=True):
            used = (float(original), float(candidate))
            if self.tallies[key].setdefault(oid, used) != used:
                raise ValueError("A fixed observation's radio sigma changed on re-evaluation")

    def support(self, name, candidate):
        from tools.pipeline_eval.variants.track_preparation import fingerprint

        scan = candidate["scan"]
        self.supports[name] = fingerprint(dict(
            catalogue=scan.norads, node=candidate["node"], keep=candidate["keep"],
            entries=candidate["entries"], powers=candidate["powers"], model=candidate["model"],
        ))

    @contextmanager
    def install(self):
        from leo.analysis.localization_v3 import event_position, position, predictive_linear
        from tools import algo08_position
        import lighter_joint_estimator

        constructor = position.NormalPosition.__init__
        linear_geometry = predictive_linear.linear_geometry
        update = lighter_joint_estimator.update
        packet = algo08_position.selected_packet
        if event_position.linear_geometry is not linear_geometry:
            raise ValueError("Expected the shared original predictive measurement port")

        def normal(model, *args, **kwargs):
            constructor(model, *args, **kwargs)
            if self.stage.get() is None:
                return
            ids = observation_ids(model.scan, model.members)
            original = model.point_noise
            sigma = scales(original, ids, self.factors, weighted=self.weighted)
            kept_ids = [oid for oid, keep in zip(ids, model.keep, strict=True) if keep]
            self.record(model.fitted_c, "curved", kept_ids, original[model.keep], sigma[model.keep])
            if self.weighted:
                set_normal_scales(model, sigma)

        def predictive(model, entries):
            view, values, sigma, groups, slices = linear_geometry(model, entries)
            if self.stage.get() is None:
                return view, values, sigma, groups, slices
            ids = observation_ids(model.scan, (entry["track_index"] for entry in entries))
            scaled = scales(sigma, ids, self.factors, weighted=self.weighted)
            self.record(model.fitted_c, "predictive", ids, sigma, scaled)
            return view, values, scaled, groups, slices

        def signed(prepared, ordinary, measured):
            self.support("ordinary", ordinary)
            with self.active("signed"):
                chosen = update(prepared, ordinary, measured)
            self.support("after_signed", chosen)
            if measured["signed"]["status"] == "accepted":
                self.chosen = chosen
            return chosen

        def selected(prepared, chosen, fit):
            if chosen is self.chosen:
                with self.active("evidence"):
                    return packet(prepared, chosen, fit)
            return packet(prepared, chosen, fit)

        # The checked grid compiler snapshots the event module's globals
        # before the solve starts. Install both aliases before that snapshot.
        with (patch.object(position.NormalPosition, "__init__", normal),
              patch.object(predictive_linear, "linear_geometry", predictive),
              patch.object(event_position, "linear_geometry", predictive),
              patch.object(lighter_joint_estimator, "update", signed),
              patch.object(algo08_position, "selected_packet", selected)):
            yield

    def summary(self):
        rows = {}
        for (stage, arm, role), values in sorted(self.tallies.items()):
            key = stage, arm, role
            ratios = [(candidate / original)**2 for original, candidate in values.values()]
            rows.setdefault(stage, {}).setdefault(arm, {})[role] = dict(
                calls=self.calls[key], rows=len(values), changed=sum(value > 1. for value in ratios),
                short_rows=sum(self.factors[oid] > 1. for oid in values),
                variance_ratio_range=[min(ratios), max(ratios)],
            )
        return dict(accepted=self.chosen is not None, selected_support=self.supports, scopes=rows)
