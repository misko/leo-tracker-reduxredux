"""Count-frozen retained-numerator approximation, not a normalized density."""

import math


class FrozenDenominator:
    def __init__(self, base, counts):
        self.base = base
        self.documents = base.documents
        self.models = base.models
        self.counts = counts
        self.original_background = dict(base.background)

    def evaluate(self, x, gradient=True, held=False):
        penalty = 0.0
        shifts = []
        for di, (doc, engine) in enumerate(zip(self.documents, self.models, strict=True)):
            for ti, track in enumerate(doc["tracks"]):
                _, visible = engine.prediction(track, [x[0], x[1], x[di + 2]])
                retained = int(visible.sum())
                full = self.counts[di, ti]
                assert 0 < retained <= full
                shift = math.log(full / retained)
                # Shift background inside original mixture, then undo common
                # factor outside it. Locally constant visible sets preserve
                # the original responsibility-weighted analytic gradient.
                self.base.background[di, ti] = tuple(
                    value + shift for value in self.original_background[di, ti]
                )
                penalty += shift
                shifts.append(shift)
        try:
            result = self.base.evaluate(x, gradient=gradient, held=held)
            result["score"] -= penalty
            if held:
                for row, shift in zip(result["rows"], shifts, strict=True):
                    row["training_log_score"] -= shift
                    row["signal_training_log_density"] -= shift
                    row["background_training_log_density"] -= shift
            return result
        finally:
            self.base.background = dict(self.original_background)
