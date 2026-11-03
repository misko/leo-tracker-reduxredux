"""Use plug-in receiver probabilities only for physical-source association."""
import numpy as np
from whole_source_fast import WholeSourcePosition


class AssociationOnlyPosition(WholeSourcePosition):
    def __init__(self, doc, config, bound, calibration, arm, initial):
        super().__init__(doc, config, bound, calibration, arm)
        self.receiver_reference_x = np.array(initial, dtype=float, copy=True)
        self.fixed_rx = {tid: super(AssociationOnlyPosition, self).receiver_probabilities(track, tid, self.receiver_reference_x) for tid, track in self.tracks.items()}
        for values in self.fixed_rx.values():
            values.setflags(write=False)

    def receiver_probabilities(self, track, tid, x):
        return self.fixed_rx[tid]
