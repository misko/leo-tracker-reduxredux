"""The stock-only calibration must use the original released argv and receipts."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
import stock_raw_repeat as repeat


@pytest.mark.parametrize("case", repeat.ORDER)
def test_only_stock_output_path_is_replaced(case, tmp_path):
    admission = repeat.sealed_control(case)["admission"]
    old = admission["commands"]["stock"]
    assert repeat.stock_command(admission, tmp_path) == [*old[:-1], str(tmp_path / "stock")]
    admission["commands"]["stock"][0] = "/tmp/development-run"
    with pytest.raises(ValueError, match="installed ALGO08v3 command"):
        repeat.stock_command(admission, tmp_path)
