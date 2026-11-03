"""Assemble fixed satellite groups from the existing narrow track ports."""
import numpy as np

from leo.analysis.localization_shared_scale import SelectedResidualBlock, SharedScalePort


class FixedBackgroundPort:
    candidate_count = 0
    priors_piecewise_constant = True

    def __init__(self, base):
        self.base = base
        self.observation, self.observation_ids = base.observation, base.observation_ids

    def score_selected(self, state, index):
        if index != 0:
            raise ValueError('background-only port')
        return self.base.score_selected(state, self.base.candidate_count)

    def score_all(self, state):
        return np.array([self.score_selected(state, 0)])

    def predict_selected(self, state, index):
        raise ValueError('background has no signal prediction')


def make_groups(ports, state, assignments, grouping):
    if grouping not in ('satellite', 'singleton'):
        raise ValueError('invalid scale grouping')
    grouped, members, backgrounds = {}, {}, []
    for track_index, (port, assignment) in enumerate(zip(ports, assignments, strict=True)):
        if assignment == port.candidate_count:
            backgrounds.append(FixedBackgroundPort(port))
            continue
        key = assignment if grouping == 'satellite' else track_index
        prediction = port.predict_selected(state, assignment)
        if not prediction.eligible:
            raise ValueError('ineligible initial fixed assignment')
        block = SelectedResidualBlock(
            port.observation, port.observation_ids, prediction.covariance,
            lambda x, p=port, i=assignment: p.predict_selected(x, i),
            float(np.log(port.config.signal_prior/port.candidate_count)))
        grouped.setdefault(key, []).append(block)
        members.setdefault(key, []).append(track_index)
    result = [SharedScalePort(blocks) for blocks in grouped.values()]+backgrounds
    original = [i for p in ports for i in p.observation_ids]
    assembled = [i for p in result for i in p.observation_ids]
    assert len(set(assembled)) == len(assembled) and sorted(original) == sorted(assembled)
    return result, list(members.values())
