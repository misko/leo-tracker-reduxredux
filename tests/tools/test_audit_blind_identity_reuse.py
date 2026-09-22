import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "reuse", Path(__file__).parents[2] / "tools/research/audit_blind_identity_reuse.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_distinguishes_track_receiver_and_scan_repetition():
    tracks = [
        {"session_id": s, "episode_id": e, "candidates": [{"norad": n, "weight": w}]}
        for s, e, n, w in [("s1", "a", 1, .8), ("s1", "b", 1, .7), ("s2", "c", 1, .2)]
    ]
    receivers = {("s1", "a"): 0, ("s1", "b"): 1, ("s2", "c"): 0}
    strong = module.summarize(tracks, receivers, .5)
    assert strong["repeated_across_receivers"] == 1
    assert strong["repeated_across_scans"] == 0
    assert strong["supported_track_count"] == 2
    assert module.summarize(tracks, receivers, .1)["repeated_across_scans"] == 1
    with pytest.raises(ValueError, match="duplicate track"):
        module.summarize(tracks + tracks[:1], receivers, .5)
