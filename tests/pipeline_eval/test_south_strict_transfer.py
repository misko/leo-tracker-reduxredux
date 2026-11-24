from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.south_strict_transfer import price, selected_causal, strict_match


def test_causal_selection_keeps_recent_aliases_and_one_older_stamp():
    hour = 3_600_000_000_000
    cutoff = 80 * hour
    refs = [SimpleNamespace(collected_utc_ns=stamp * hour, sha256=body, path=Path(str(stamp)))
            for stamp, body in ((0, "old"), (8, "a"), (12, "a"), (32, "b"), (40, "b"), (81, "future"))]

    class Ref:
        def __init__(self, row):
            self.__dict__.update(vars(row))

        def __lt__(self, other):
            return self.collected_utc_ns < other.collected_utc_ns

    assert selected_causal([Ref(row) for row in reversed(refs)], cutoff) == {Path("8"), Path("32"), Path("40")}


def test_strict_matching_rejects_unchecked_suffix_or_fallback():
    row = {"state": "strict-packed-eight", "encoded_blocks": 2, "original_decoded_sha256": "sha256:one",
           "seek_sha256": "sha256:map", "checks": {"payload_bytes": 56}, "loads": {"0": "short"}}
    usage = {"strict_packed_eight": True, "fallback": None, "original_windows": 0, "members": [row]}
    verified = {"sections": [{"original": {"window_count": 1, "uncompressed_sha256": "sha256:one"},
                              "checked_derivative": {"payload_bytes": 56}, "binding": {"seek_sha256": "sha256:map"}}]}
    assert strict_match(usage, verified) == {"short": 1}
    stale = deepcopy(usage)
    stale["members"][0]["checks"]["payload_bytes"] -= 1
    with pytest.raises(ValueError, match="independently verified"):
        strict_match(stale, verified)
    with pytest.raises(ValueError, match="independently verified"):
        strict_match(dict(usage, fallback="ordinary"), verified)


def test_full_conversion_and_both_historical_denominators_are_separate():
    result = price(10, 17, 15, 8)
    assert result["clears_fresh_1_6x"] and not result["clears_archived_1_6x"]
    assert result["first_use_s"] == 18
    assert result["first_use_vs_fresh"] < 1
