"""Position inference through explicit native CFO branches and latent histories.

Waveform evidence labels native acquisition candidates, not satellites. The
physical CFO domain is the metadata sampling circle; nearby OFDM branches stay
distinct while exact sampling aliases remain observationally identical.
"""

from dataclasses import dataclass, replace

import numpy as np
from scipy.special import logsumexp

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.joint_association_graph import continuity_families, sparse_forward_backward
from leo.analysis.regional_position_score import PositionObjective, WindowLikelihood


@dataclass(frozen=True)
class NativeBranchEvidence:
    """Exact aligned native candidate IDs, CFOs and optional measured log evidence.

    Empty IDs denote unavailable native candidates. No synthetic CFO branch may
    be called measured. Missing waveform evidence contributes exactly zero.
    Slots must identify the same physical CFO ambiguity branch within a family.
    """

    candidate_ids: tuple[tuple[str, ...], ...]
    cfo_hz: np.ndarray
    waveform_log_evidence: np.ndarray
    waveform_measured: np.ndarray
    receive_time_s: np.ndarray | None = None

    def __post_init__(self):
        cfo = np.asarray(self.cfo_hz, float)
        waveform = np.asarray(self.waveform_log_evidence, float)
        measured = np.asarray(self.waveform_measured)
        available = np.asarray([[bool(x) for x in row] for row in self.candidate_ids])
        if (
            cfo.ndim != 2
            or cfo.shape[1] < 1
            or waveform.shape != cfo.shape
            or measured.shape != cfo.shape
            or measured.dtype != bool
            or available.shape != cfo.shape
            or not available.any(axis=1).all()
            or not np.isfinite(cfo).all()
            or not np.isfinite(waveform).all()
            or np.any(measured & ~available)
            or np.any(waveform[~measured] != 0)
        ):
            raise ValueError("native branches and explicit optional waveform evidence required")
        for row in self.candidate_ids:
            ids = [x for x in row if x]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate native candidate branch")
        for name, value in (
            ("cfo_hz", cfo),
            ("waveform_log_evidence", waveform),
            ("waveform_measured", measured),
        ):
            value = np.array(value, copy=True)
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        if self.receive_time_s is not None:
            times = np.asarray(self.receive_time_s, float)
            if times.shape != cfo.shape or not np.isfinite(times).all():
                raise ValueError("aligned native receive times required")
            times = times.copy()
            times.setflags(write=False)
            object.__setattr__(self, "receive_time_s", times)

    @property
    def available(self):
        return np.asarray([[bool(x) for x in row] for row in self.candidate_ids])


class JointAssociationObjective(PositionObjective):
    """Lean receiver offset/drift/RF terms plus orbital timing and position.

    No satellite-specific frequency slopes, receiver splines, frame ranging or
    satellite identity is inferred from the pilot itself. Group constants can
    be added through the existing narrow GroupCalibrationObjective wrapper.
    """

    def __init__(
        self,
        observations,
        bank,
        prior,
        score,
        *,
        sample_rate_hz,
        branch_evidence,
        family_keys,
        maximum_gap_s=0.025,
        signal_stay=0.95,
        clutter_stay=0.5,
        receiver_baseline_hz=None,
    ):
        super().__init__(
            observations, bank, prior, score, receiver_baseline_hz=receiver_baseline_hz
        )
        if (
            not np.isfinite(sample_rate_hz)
            or sample_rate_hz <= 10 * score.sigma_hz
            or branch_evidence.cfo_hz.shape[0] != len(observations.times_s)
        ):
            raise ValueError("metadata sampling domain and aligned native branches required")
        self.sample_rate_hz = float(sample_rate_hz)
        self.branches = branch_evidence
        self.families = continuity_families(
            observations.times_s, family_keys, maximum_gap_s=maximum_gap_s
        )
        self.signal_stay = signal_stay
        self.clutter_stay = clutter_stay
        k, b = len(bank.numbers), branch_evidence.cfo_hz.shape[1]
        # This is a normalized conditional detector-observation model, distinct
        # from the legacy independent Poisson top-one mixture.
        clutter_mass = score.clutter_rate / (score.clutter_rate + score.detection_budget)
        self.initial = np.r_[clutter_mass, np.full(k * b, (1 - clutter_mass) / (k * b))]
        self.branch_observations = tuple(
            observations
            if branch_evidence.receive_time_s is None
            else replace(observations, times_s=branch_evidence.receive_time_s[:, j])
            for j in range(b)
        )
        self.branch_design = np.repeat(self.design[:, :, None], b, axis=2)
        for j, obs in enumerate(self.branch_observations):
            centered = obs.times_s - observations.time_center_s
            self.branch_design[:, 1, j] = (obs.receiver == 0) * centered
            self.branch_design[:, 3, j] = (obs.receiver == 1) * centered

    def likelihood(self, prediction, visible):
        native = self.branches
        n, k = prediction.shape[:2]
        b = native.cfo_hz.shape[1]
        if prediction.ndim == 2:
            prediction = np.repeat(prediction[:, :, None], b, axis=2)
            visible = np.repeat(visible[:, :, None], b, axis=2)
        residual = native.cfo_hz[:, None, :] - prediction
        residual = (residual + self.sample_rate_hz / 2) % self.sample_rate_hz
        residual -= self.sample_rate_hz / 2
        log_phi = -0.5 * (residual / self.score.sigma_hz) ** 2
        log_phi -= np.log(self.score.sigma_hz * np.sqrt(2 * np.pi))
        available = native.available
        # A uniform branch observation has total mass one even when only one
        # native proposal is available. Measured waveform likelihood is shared
        # across satellites and never supplies a satellite identity label.
        log_phi += np.log(b / available.sum(axis=1))[:, None, None]
        log_waveform = np.where(available, native.waveform_log_evidence, -np.inf)
        log_waveform -= logsumexp(log_waveform, axis=1)[:, None]
        log_waveform += np.log(available.sum(axis=1))[:, None]
        log_phi += log_waveform[:, None, :]
        log_phi = np.where(visible & available[:, None, :], log_phi, -np.inf)
        emissions = np.column_stack(
            [np.full(n, -np.log(self.sample_rate_hz)), log_phi.reshape(n, k * b)]
        )
        histories = sparse_forward_backward(
            emissions,
            self.families,
            self.initial,
            signal_stay=self.signal_stay,
            clutter_stay=self.clutter_stay,
        )
        branches = histories.posterior[:, 1:].reshape(n, k, b)
        responsibilities = branches.sum(axis=2)
        gradient = -np.sum(branches * residual, axis=2) / self.score.sigma_hz**2
        mean = np.sum(branches * residual, axis=2)
        mean = np.divide(
            mean, responsibilities, out=np.zeros_like(mean), where=responsibilities > 0
        )
        terms = WindowLikelihood(
            histories.nll, responsibilities, histories.posterior[:, 0], gradient, mean
        )
        return terms, -branches * residual / self.score.sigma_hz**2

    def evaluate(self, vector):
        vector = np.asarray(vector, float)
        if vector.shape != (self.size,) or not np.isfinite(vector).all():
            raise ValueError("invalid joint position vector")
        relative = self.basis @ vector[8:]
        predictions = [
            predict_orbits(self.bank, obs, self.prior, vector[:2], vector[7] + relative)
            for obs in self.branch_observations
        ]
        prediction = np.stack([p[0] for p in predictions], axis=2)
        visible = np.stack([p[1] for p in predictions], axis=2)
        spatial = np.stack([p[2] for p in predictions], axis=2)
        timing = np.stack([p[3] for p in predictions], axis=2)
        correction = np.einsum("npb,p->nb", self.branch_design, vector[2:7])
        prediction += (correction + self.baseline[:, None])[:, None, :]
        terms, weight = self.likelihood(prediction, visible)
        shift_gradient = np.sum(weight * timing, axis=(0, 2))
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nkb,nkbi->i", weight, spatial)
        gradient[2:7] = np.einsum("npb,nb->p", self.branch_design, weight.sum(axis=1))
        gradient[7] = shift_gradient.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift_gradient + relative / self.score.relative_sigma_s**2)
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        return terms.nll + float(penalty), gradient, terms
