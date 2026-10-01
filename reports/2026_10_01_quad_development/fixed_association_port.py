"""Preserve selected physical branch while disabling reassignment."""
import numpy as np


class FixedAssociationPort:
    def __init__(self, port, index):
        if not 0 <= index <= port.candidate_count: raise ValueError('invalid branch')
        self.port = port
        self.index = index

    def __getattr__(self, name): return getattr(self.port, name)

    def score_all(self, state):
        values = np.full(self.candidate_count+1, -np.inf)
        values[self.index] = self.port.score_selected(state, self.index)
        return values

    def score_selected(self, state, index):
        if index != self.index: raise ValueError('fixed branch mismatch')
        return self.port.score_selected(state, index)

    def predict_selected(self, state, index):
        if index != self.index: raise ValueError('fixed branch mismatch')
        return self.port.predict_selected(state, index)
