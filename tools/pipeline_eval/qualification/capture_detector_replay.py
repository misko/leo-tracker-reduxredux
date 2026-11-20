"""Project the original installed fast-scan detector's native science from CI16."""

from .full_v5_check import _from_production, _probe


def scan_capture_window(window, receiver_ids, policy):
    """Use the capture release already bound by the caller's worker process."""
    from leo.scanner.fast_scan_analysis import analyze_window

    result = analyze_window(window, receiver_ids, None, policy)
    probes = [
        _probe(window, item.receiver_id, map(_from_production, item.candidates))
        for item in result.receivers
    ]
    if result.status == "processed" and [p["receiver_id"] for p in probes] != list(receiver_ids):
        raise ValueError("capture detector reordered or omitted a physical receiver")
    if result.status != "processed" and probes:
        raise ValueError("capture exclusion has detector observations")
    return result, probes
