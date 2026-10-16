"""Private singleton candidate mixtures with fixed mass per native OFDM cell."""

from dataclasses import dataclass

import numpy as np

from leo.analysis.joint_association_graph import sparse_forward_backward
from leo.analysis.joint_association_sparse import SparseNativeJointObjective
from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood


def native_candidate_cell_prior(evidence, sample_rate_hz):
    """Split 1/B available-cell mass equally among its actual native proposals.

    Priors depend only on the fixed input inventory, before visibility masking.
    They are separate from measured waveform evidence and never create another
    observation for an alternative candidate.
    """
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("positive finite native sampling domain required")
    available = evidence.available
    canonical = (evidence.cfo_hz + sample_rate_hz / 2) % sample_rate_hz
    canonical -= sample_rate_hz / 2
    labels = np.floor(canonical / ALIAS_HZ + 0.5).astype(int)
    prior = np.zeros_like(evidence.cfo_hz)
    for row, valid in enumerate(available):
        cells, inverse, counts = np.unique(labels[row, valid], return_inverse=True,
                                          return_counts=True)
        prior[row, valid] = 1 / (len(cells) * counts[inverse])
    labels.setflags(write=False)
    prior.setflags(write=False)
    return labels, prior


@dataclass(frozen=True)
class NativeCandidateWindowLikelihood(WindowLikelihood):
    candidate_responsibilities: np.ndarray
    posterior_native_residual_rms_hz: float | None


class NativeCandidateSingletonObjective(SparseNativeJointObjective):
    """Same physical parameters/priors, with every native candidate retained.

    Packed slots are meaningful only within their original measurement window.
    Reject temporal histories rather than asserting a persistent candidate ID.
    This separate research objective leaves the default native model unchanged.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if any(len(family) != 1 for family in self.families):
            raise ValueError("all-candidate slots require singleton temporal families")
        if (self.branches.waveform_measured.any()
                or np.any(self.branches.waveform_log_evidence != 0)):
            raise ValueError("this candidate control requires explicit neutral waveform evidence")
        self.candidate_cell_labels, self.metadata_candidate_prior = native_candidate_cell_prior(
            self.branches, self.sample_rate_hz
        )
        denominator = np.ones_like(self.metadata_candidate_prior)
        for row, available in enumerate(self.branches.available):
            cells, inverse, counts = np.unique(self.candidate_cell_labels[row, available],
                                               return_inverse=True, return_counts=True)
            denominator[row, available] = len(cells) * counts[inverse]
        self.metadata_log_emission_prior = np.log(self.branches.cfo_hz.shape[1] / denominator)
        self.metadata_log_emission_prior.setflags(write=False)

    def likelihood(self, prediction, visible):
        native = self.branches
        n, k = prediction.shape[:2]
        b = native.cfo_hz.shape[1]
        if prediction.ndim == 2:
            prediction = np.repeat(prediction[:, :, None], b, axis=2)
            visible = np.repeat(visible[:, :, None], b, axis=2)
        if prediction.shape != (n, k, b) or visible.shape != prediction.shape:
            raise ValueError("aligned per-candidate native predictions and visibility required")
        residual = native.cfo_hz[:, None, :] - prediction
        residual = (residual + self.sample_rate_hz / 2) % self.sample_rate_hz
        residual -= self.sample_rate_hz / 2
        phi = -0.5 * (residual / self.score.sigma_hz)**2
        phi -= np.log(self.score.sigma_hz * np.sqrt(2 * np.pi))
        # Match the source-default scale/multiply normalization, including its
        # conditional residual diagnostics at subnormal posterior mass. The
        # uniform padded-slot initial prior is corrected by b/(B_i*n_ih).
        phi += self.metadata_log_emission_prior[:, None, :]
        phi = np.where(visible & native.available[:, None, :], phi, -np.inf)
        emissions = np.column_stack([
            np.full(n, -np.log(self.sample_rate_hz)), phi.reshape(n, k * b),
        ])
        histories = sparse_forward_backward(emissions, self.families, self.initial,
                                            signal_stay=self.signal_stay,
                                            clutter_stay=self.clutter_stay)
        posterior = histories.posterior[:, 1:].reshape(n, k, b)
        responsibilities = posterior.sum(axis=2)
        weight = -posterior * residual / self.score.sigma_hz**2
        mean = (posterior * residual).sum(axis=2)
        mean = np.divide(mean, responsibilities, out=np.zeros_like(mean),
                         where=responsibilities > 0)
        mass = float(posterior.sum())
        native_rms = float(np.sqrt(np.sum(posterior * residual**2) / mass)) if mass else None
        return NativeCandidateWindowLikelihood(
            histories.nll, responsibilities, histories.posterior[:, 0],
            weight.sum(axis=2), mean, posterior.sum(axis=1), native_rms,
        ), weight
