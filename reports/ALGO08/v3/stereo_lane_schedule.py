"""Deterministic thinning of one independently measured antenna per short visit."""

from collections import Counter
from hashlib import sha256
from pathlib import Path

from mixed_aperture_receiver import FULL_RULE


RESIDUES = {"quarter": (1, 3, 5, 7), "target": (1, 2, 3, 5, 6, 7)}


def recipe(mode, parent_receiver):
    """Bind the chosen schedule to the unchanged original receiver recipe digest."""
    if not parent_receiver.startswith("sha256:") or len(parent_receiver) != 71:
        raise ValueError("Expected the original canonical receiver recipe digest")
    return dict(mode=mode, parent_receiver=parent_receiver, omitted_short_residues=list(RESIDUES[mode]),
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), stereo_anchors=True,
                streams=["edge", "channel", "actual_rf_hz"], parity="(j + j // 4) % 2")


class StereoSchedule:
    def __init__(self, mode):
        self.omit_at = RESIDUES[mode]
        self.counts = Counter()

    def next(self, stream):
        """Advance once per admitted stereo visit in a fixed RF, channel and edge stream."""
        n = self.counts[stream]
        self.counts[stream] += 1
        aperture = FULL_RULE[n % len(FULL_RULE)]
        if aperture == "full":
            return aperture, None
        j = n - 1 - n // len(FULL_RULE)
        return aperture, (j + j // 4) % 2 if j % 8 in self.omit_at else None
