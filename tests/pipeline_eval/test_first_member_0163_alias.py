"""The additive alias diagnostic uses the actual original sign and period."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from first_member_0163_alias import PERIOD, affine_value, alias_at


def test_signed_nearest_alias_crosses_the_half_period():
    assert alias_at(PERIOD * .51, 0)["nearest_integer"] == -1
    assert alias_at(-PERIOD * .51, 0)["nearest_integer"] == 1
    assert alias_at(PERIOD * .51, 0)["nearest_alias_residual_hz"] == pytest.approx(-PERIOD * .49)


def test_peer_prediction_interpolates_around_native_target_epoch():
    assert affine_value([(-2, -30), (-1, -10), (+1, 30), (+2, 50)], 0) == pytest.approx(10)
