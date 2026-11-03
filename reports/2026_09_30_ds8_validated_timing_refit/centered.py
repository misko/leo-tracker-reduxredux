"""Subtract a fixed objective constant while preserving all derivatives."""


class Centered:
    def __init__(self, model, initial):
        self.model = model
        self.offset = model.evaluate(initial, gradient=False)['score']

    def evaluate(self, x, **kwargs):
        out = dict(self.model.evaluate(x, **kwargs))
        out['score'] -= self.offset
        return out
