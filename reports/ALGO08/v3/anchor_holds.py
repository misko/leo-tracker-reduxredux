"""Project held-anchor training rows without importing solver or archive code."""

from anchor_exposure import enroll


def erased_rows(document):
    probes = document["source"]["probes"]
    held = [index for index, opportunity in enumerate(enroll(document)) if opportunity[4] == "anchor"]
    masked = list(probes)
    for index in held:
        masked[index] = dict(probes[index], candidates=[])
    return masked, held


def history_rows(probes):
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    history, rows = Continuation(), []
    for row in probes:
        _, keep, _ = history.select(row)
        rows.append(dict(row, candidates=[] if keep is None else [row["candidates"][keep]]))
    return rows
