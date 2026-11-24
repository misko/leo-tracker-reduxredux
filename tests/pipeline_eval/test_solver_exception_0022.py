from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3.solver_exception_0022 import HOUR_NS, selected_refs


def snapshot(name, time):
    return SimpleNamespace(path=Path(name + ".tle"), collected_utc_ns=time, sha256=name)


def test_original_catalogue_can_be_verified_across_existing_donors():
    capture, cutoff = 80 * HOUR_NS, 80 * HOUR_NS - 1
    old, new = snapshot("old", 8 * HOUR_NS), snapshot("new", cutoff - 1)
    future = snapshot("future", cutoff)
    expired = snapshot("expired", old.collected_utc_ns - 1)
    donors = (("first", (expired, old, future)), ("second", (old, new)))
    pin = canonical_digest({"old.tle": "old", "new.tle": "new"})
    assert selected_refs(donors, capture, cutoff, pin) == (new, old)
    with pytest.raises(ValueError, match="lacks the exact"):
        selected_refs(donors[:1], capture, cutoff, pin)
