"""Schedule complete short stereo visits inside the original mixed receiver."""

from hashlib import sha256
from pathlib import Path

from mixed_aperture_receiver import StereoSchedule


RULE = dict(anchor_period=8, short_period=3, keep_short=[0, 1], scope=["edge", "channel", "actual_rf_hz"],
            reset="new original recording; no gap reset", excludes="only original admitted opportunities advance",
            omitted_outputs="empty stereo probe pair at original hardware counters")
PLANNER_SHA = "eb8619f3c768510345663b8144a987a1c07ff890bc8351cbf9e18b992420e33a"
PROTOCOL_SHA = "a03d377e08e2f5b79641c5391c81f2df297e23d3398f2776be7669fed2707ba4"


class WholeStereoSchedule(StereoSchedule):
    def __init__(self):
        super().__init__(full_coverage=True)

    def visit(self, edge, target, capture):
        index, aperture = super().visit(edge, target, capture)
        short = index - 1 - index // 8
        return index, "skip" if aperture == "short_primary" and short % 3 == 2 else aperture


def bind(receiver, parent):
    from mixed_aperture_receiver import MixedApertureDetector

    if type(receiver) is not MixedApertureDetector:
        raise ValueError("Whole stereo scheduling requires the original unrefined mixed receiver")
    receiver.schedule = WholeStereoSchedule()
    return dict(kind="live whole-stereo short-opportunity schedule", parent=parent, rule=RULE,
                continuation="unfiltered original within-lane selection",
                planner_sha256=PLANNER_SHA, protocol_sha256=PROTOCOL_SHA,
                implementation_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
