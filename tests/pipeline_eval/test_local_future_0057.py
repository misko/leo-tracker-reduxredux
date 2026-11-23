import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from local_future_0057 import changes


def test_owner_audit_counts_displaced_rows_and_rejects_ambiguous_labels():
    old = [["one", 1, "conditional"], ["two", 2, "predictive"]]
    new = [["one", 1, "predictive"], ["three", 2, "conditional"]]
    assert changes(old, new) == dict(before=2, after=2, lost=1, added=1, changed=1)
    with pytest.raises(ValueError):
        changes(old, new + [new[0]])
