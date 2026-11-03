"""Sparse GLRT refinement with a shared latent identity for each long track."""

import numpy as np
from staged_fit import (
    candidate_ladder,
    fit_receiver_lines,
    frozen_row_weights,
    refine_bank,
    select_trials,
)
from track_seed import fit_rough


def anchor_partition(data, *, min_groups=15, min_span_s=15.0, max_anchors=12):
    eligible = []
    for index, track in enumerate(data.tracks):
        rows = np.asarray(track["rows"], dtype=int)
        groups = np.unique(data.group[rows])
        span = float(np.ptp(data.times[rows])) if len(rows) else 0.0
        if len(groups) >= min_groups and span >= min_span_s:
            eligible.append((index, groups, span))
    eligible.sort(key=lambda item: (-len(item[1]), -item[2], item[0]))
    owned = set()
    anchors = []
    for index, groups, span in eligible:
        retained = np.asarray([group for group in groups if int(group) not in owned], dtype=int)
        retained_rows = np.asarray(data.tracks[index]["rows"], dtype=int)
        retained_rows = retained_rows[np.isin(data.group[retained_rows], retained)]
        retained_span = float(np.ptp(data.times[retained_rows])) if len(retained_rows) else 0.0
        if len(retained) < min_groups or retained_span < min_span_s:
            continue
        owned.update(retained.tolist())
        anchors.append(
            {
                "track_index": index,
                "groups": retained,
                "span_s": retained_span,
                "original_span_s": span,
                "overlap_groups_removed": len(groups) - len(retained),
                "candidate_indices": np.unique(data.tracks[index]["candidate_indices"]),
            }
        )
        if len(anchors) >= max_anchors:
            break
    return anchors


def frozen_identity_masses(anchors, full_bank, selected):
    full_bank = np.asarray(full_bank, dtype=int)
    selected = np.asarray(selected, dtype=int)
    if len(np.unique(full_bank)) != len(full_bank) or not np.all(np.isin(selected, full_bank)):
        raise ValueError("Selected identities must belong to a unique frozen bank")
    raw_mass = np.full(len(selected), 0.8 / len(full_bank))
    anchor_mass = np.zeros((len(anchors), len(selected)))
    for index, anchor in enumerate(anchors):
        allowed = np.intersect1d(full_bank, anchor["candidate_indices"])
        if len(allowed):
            anchor_mass[index] = np.isin(selected, allowed) * (0.8 / len(allowed))
    return {
        "raw_satellite_mass": raw_mass,
        "raw_background_mass": 1 - float(raw_mass.sum()),
        "anchor_satellite_mass": anchor_mass,
        "anchor_unknown_mass": 1 - anchor_mass.sum(axis=1),
    }


class FixedBankLikelihood:
    def __init__(self, prepared, masses):
        self.prepared = prepared
        self.masses = masses
        self.last_result = None

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        satellite_weights,
        background_mass,
        return_gradient=False,
        return_precision=False,
    ):
        self.last_result = self.prepared.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            **self.masses,
            track_contamination=0.2,
            return_gradient=return_gradient,
            return_precision=return_precision,
        )
        return self.last_result


def fit_coherent(data, rough=None, *, keep_track_identity=True):
    from track_likelihood import prepare_track_grouped_likelihood

    rough = fit_rough(data) if rough is None else rough
    initial = fit_receiver_lines(data, rough)
    capture_count = len(getattr(data, "child_sessions", [data.session_id]))
    anchors = anchor_partition(data, max_anchors=12 * capture_count)
    if not keep_track_identity:
        anchors = []
    ladder = candidate_ladder(
        rough["assignments"], sizes=tuple(size * capture_count for size in (4, 8, 12))
    )
    full_bank = ladder[-1][0]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in anchors],
    )
    trials = []
    for satellites, support in ladder:
        masses = frozen_identity_masses(anchors, full_bank, satellites)
        likelihood = FixedBankLikelihood(prepared, masses)
        trial = refine_bank(data, initial, satellites, support, likelihood)
        trial.pop("satellite_weights")
        trial["identity_masses"] = masses
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    return {
        "rough": rough,
        "rx_initial": initial,
        "anchors": anchors,
        "full_bank": full_bank,
        "keep_track_identity": keep_track_identity,
        "trials": trials,
        **select_trials(trials),
        "scope": "Whole-track latent identity with per-group clutter; remaining groups use raw "
        "mixture. Groups counted once. Uniform identity masses frozen against largest proposed "
        "bank; omitted mass becomes unknown. Candidate proposals and track partition are "
        "data-dependent, so likelihood remains a conditional proxy, not calibrated evidence.",
    }
