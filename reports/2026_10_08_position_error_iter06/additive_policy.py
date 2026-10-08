"""Retain the original finalist unless an additional finalist scores better."""


def select(original, additional):
    if additional is None or not additional["converged"]:
        return original, "baseline"
    if original is None or additional["selection_score"] < original["selection_score"]:
        return additional, "additional"
    return original, "baseline"
