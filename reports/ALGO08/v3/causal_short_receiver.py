"""Apply the released continuation decision after the mixed receiver's single-lane selection."""

import json
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from mixed_aperture_receiver import MixedApertureDetector

from tools.pipeline_eval.variants import carrier_continuation

FILTER_SHA = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"


def identity(original):
    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != FILTER_SHA:
        raise ValueError("The frozen carrier history filter changed")
    recipe = [
        "causal selective on maximum-margin short factors v1",
        "sha256:" + original,
        FILTER_SHA,
    ]
    return recipe, sha256(json.dumps(recipe, separators=(",", ":")).encode()).hexdigest()


def select(history, row):
    _, keep, _ = history.select(row)
    return dict(row, candidates=[] if keep is None else [row["candidates"][keep]])


class CausalShortReceiver(MixedApertureDetector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = carrier_continuation.Continuation()

    @contextmanager
    def detector(self, *args, **kwargs):
        with super().detector(*args, **kwargs) as receive:

            def visit(window):
                return [select(self.history, row) for row in receive(window)]

            yield visit
