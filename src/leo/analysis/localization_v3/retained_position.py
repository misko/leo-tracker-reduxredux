"""Phase-refreshed retained-point fitting with explicit causal prior evidence."""

import numpy as np

from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.orbit_modes import previous_bank
from leo.analysis.localization_v3.phase_prior import causal_phase_sigma
from leo.analysis.localization_v3.position import NormalPosition, fit


def phase_widths(scan, labels):
    if scan.previous_sources is None:
        raise ValueError("Explicit previous-epoch provenance required")
    _, _, alignments = previous_bank(scan, labels)
    old = scan.previous_sources
    result, receipt = [], []
    for j in labels:
        norad = str(int(scan.norads[j]))
        epoch = scan.elements[norad]["provenance"]["element_epoch_utc_ns"]
        age = (scan.origin_utc_ns - epoch) / 1e9
        gap = (epoch - old[norad]["epoch_utc_ns"]) / 1e9 if norad in old else None
        alignment = alignments.get(int(norad))
        width = causal_phase_sigma(alignment, age, gap) if alignment is not None else 1.0
        result.append(width)
        receipt.append(
            dict(
                norad=int(norad),
                age_s=age,
                previous_epoch_gap_s=gap,
                old_new_alignment_s=alignment,
                sigma_s=width,
            )
        )
    return np.array(result), receipt


class PositionNormal(NormalPosition):
    """Original integrated position model, optionally with shared satellite scales."""

    def __init__(self, *args, scale_labels=(), scale_reference=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scale_labels = [j for j in scale_labels if j in self.labels]
        self.scale_reference = (
            np.zeros(len(self.scale_labels))
            if scale_reference is None
            else np.asarray(scale_reference)
        )

    def calculate(self, x):
        if not self.scale_labels:
            return super().calculate(x)
        result = JointMarginal.calculate(self, x)
        features = result["features"].copy()
        intercept = result["intercept"].copy()
        scales = np.zeros((len(self.values), len(self.scale_labels)))
        start = self.hardware.shape[1] + self.smooth.shape[1]
        for k, j in enumerate(self.scale_labels):
            local = self.labels.index(j)
            use = self.flat_labels == local
            ref = float(self.scale_reference[k])
            scales[use, k] = self.q[use] * result["frequency"][use] * 0.005
            features[use, start + local] *= 1 + ref
            intercept[use] -= ref * result["derivative"][use] * self.reference[local]
        stop = features.shape[1] - len(self.members)
        features = np.column_stack((features[:, :stop], scales, features[:, stop:]))
        raw = self.values - self.q * intercept
        bound = hierarchical_bound(
            raw[self.keep],
            features[self.keep],
            self.point_noise[self.keep],
            self.noise_groups[self.keep],
        )
        present = np.unique(self.noise_groups[self.keep])
        weights = np.zeros(len(self.members))
        weights[present] = bound["noise_precision"]
        bound["noise_precision"] = weights
        bound["conditional_residual_hz"] = raw - features @ bound["coefficient"]
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.noise_volume)]
        result.update(bound, features=features, intercept=intercept)
        return result

    def scale_state(self, x):
        if not self.scale_labels:
            return np.zeros(0)
        a = self.calculate(x)["coefficient"]
        end = len(a) - len(self.members)
        return a[end - len(self.scale_labels) : end] * 0.005


def fit_position(
    scan, node, keep, scale_labels, arm, model, start=(0.0, 0.0), rounds=5, iterations=48
):
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    widths, width_receipt = phase_widths(scan, labels)
    phase = np.zeros(len(labels))
    active_scale = [j for j in scale_labels if j in labels] if model == "shared_scale" else []
    reference_scale = np.zeros(len(active_scale))
    anchor = np.asarray(start, float)
    history = []
    for epoch in range(rounds):
        p = PositionNormal(
            scan,
            node,
            scan.radio_sigma_hz,
            arm == "fitted_c",
            reference=phase,
            keep=keep,
            scale_labels=active_scale,
            scale_reference=reference_scale,
        )
        p.phase_sigma = widths
        result = fit(p, anchor, iterations=iterations)
        anchor = np.asarray(result["parameters"])
        posterior_phase = p.state(anchor)["phases"][p.labels]
        posterior_scale = p.scale_state(anchor)
        history.append(
            dict(
                epoch=epoch,
                fit=result,
                phase_reference=phase,
                scale_reference=reference_scale,
                max_phase_change_s=float(max(abs(posterior_phase - phase))),
                max_scale_change=float(max(abs(posterior_scale - reference_scale), default=0)),
            )
        )
        phase = np.clip(posterior_phase, -15, 15)
        reference_scale = posterior_scale
    c = p.calculate(anchor)
    rows = []
    for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
        r = c["conditional_residual_hz"][sl]
        rows.append(
            dict(
                component=row["component"],
                norad=row["candidate_norad"],
                candidate_index=row["candidate_index"],
                points=int(p.keep[sl].sum()),
                residual_rms_hz=float(np.sqrt(np.mean(r * r))),
                noise_precision=float(c["noise_precision"][p.noise_groups[sl.start]]),
                observation_ids=scan.tracks[i]["observation_ids"],
            )
        )
    state = p.state(anchor)
    state["satellite_scales"] = {
        int(j): float(v) for j, v in zip(p.scale_labels, p.scale_state(anchor), strict=True)
    }
    record = dict(
        fit=result,
        history=history,
        endpoint_east_north_km=anchor,
        endpoint_latlon=scan.search_region.latlon(anchor),
        state=state,
        phase_reference=p.reference,
        scale_reference=p.scale_reference,
        phase_widths_s=widths,
        phase_width_receipt=width_receipt,
        scales={
            str(int(scan.norads[j])): float(v)
            for j, v in zip(p.scale_labels, p.scale_state(anchor), strict=True)
        },
        active_points=int(keep.sum()),
        tracks=rows,
        rows=p.rows,
        aliases=p.alias,
        frequency_rms_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep] ** 2))),
        score=float(p.residual(anchor) @ p.residual(anchor)),
        noise_precision=c["noise_precision"],
        phase_rounds=rounds,
        scale_sigma=0.005 if active_scale else None,
        scale_gaussian_not_hard_truncated=True,
        max_last_phase_change_s=history[-1]["max_phase_change_s"],
        max_last_scale_change=history[-1]["max_scale_change"],
    )
    return p, record


def repaired_fit(scan, node, arm, kind, keep, *, rounds=5, iterations=48):
    if kind not in ("unit", "phase3", "causal"):
        raise ValueError("Unsupported repair prior")
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    widths, receipt = phase_widths(scan, labels)
    reference, anchor, history = np.zeros(len(labels)), np.zeros(2), []
    for _ in range(rounds):
        cls = NormalPosition
        p = cls(scan, node, scan.radio_sigma_hz, arm == "fitted_c", reference=reference, keep=keep)
        if kind in ("phase3", "causal"):
            p.phase_sigma = np.full(len(labels), 3.0) if kind == "phase3" else widths
        fitted = fit(p, anchor, iterations=iterations)
        anchor = np.array(fitted["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(float(np.max(abs(phase - reference))))
        reference = np.clip(phase, -15, 15)
    return p, fitted, history, receipt
