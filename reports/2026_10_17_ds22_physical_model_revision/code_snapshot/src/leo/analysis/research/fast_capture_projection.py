"""Project a later GLRT export onto explicitly sealed original raw windows."""

from copy import deepcopy


def project_fast_capture(document, windows):
    if not windows:
        raise ValueError("explicit sealed window support required")
    support = {}
    for window in windows:
        visit = window["visit"]
        if visit in support or window["sample_end"] <= window["sample_start"]:
            raise ValueError("duplicate or invalid sealed window")
        support[visit] = window
    selected = []
    for probe in document["source"]["probes"]:
        window = support.get(probe["visit_index"])
        if window is None:
            continue
        if probe["valid_start_counter"] != window["sample_start"]:
            raise ValueError("processed probe counter differs from sealed raw window")
        duration = round(
            document["source"]["sample_rate_hz"] * document["source"]["probe_ms"] / 1000
        )
        if probe["valid_start_counter"] + duration > window["sample_end"]:
            raise ValueError("processed probe extends beyond sealed window support")
        selected.append(probe)
    result = deepcopy(document)
    result["source"]["probes"] = deepcopy(selected)
    result["last_sample_counter"] = max(w["sample_end"] for w in windows)
    return result
