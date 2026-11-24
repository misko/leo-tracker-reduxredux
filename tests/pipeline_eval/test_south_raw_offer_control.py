from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from south_raw_offer_control import offer_only


def test_only_offer_and_destination_may_change():
    before = ["entry", "--region", "inside", "--output", "old", "--receiver", "continued"]
    after = ["entry", "--region", "outside", "--output", "new", "--receiver", "continued"]
    offer_only(before, after, "inside", "outside")
    for index, value in [(2, "inside"), (4, "old"), (6, "stock")]:
        modified = after.copy()
        modified[index] = value
        with pytest.raises(ValueError):
            offer_only(before, modified, "inside", "outside")
