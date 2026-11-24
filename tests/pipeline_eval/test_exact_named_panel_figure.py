import json

import pytest
from PIL import Image

from reports.ALGO08.v3.exact_named_panel_figure import HERE, render


def test_common_error_curve_requires_identical_errors_in_each_arm(tmp_path):
    receipt = HERE / "measurements/exact-named-saved-panel-four.json"
    output = tmp_path / "panel.png"
    render(receipt, output)
    with Image.open(output) as figure:
        figure.verify()
    panel = json.loads(receipt.read_bytes())
    runs = panel["per_case"]["DS30-0316"]["geography"]["runs"]
    runs["candidate"]["horizontal_error_km"]["fitted_c"] += 0.001
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(panel))
    with pytest.raises(ValueError, match="DS30-0316 has different errors"):
        render(changed, output)
