import json
from pathlib import Path

from PIL import Image

from reports.ALGO08.v3 import blind_joint_figure


def test_plot_with_withheld_offers_and_archived_dense_control(tmp_path):
    data = Path(blind_joint_figure.__file__).parent / "measurements/blind-joint-summary.json"
    cases = json.loads(data.read_bytes())["cases"]
    assert cases["DS30-0008"]["timing"]["stock"] is None
    assert cases["south-far"]["returned"]["arms"]["c0"]["error_km"] is None
    figure = tmp_path / "result.png"
    blind_joint_figure.figure(cases, figure, "Joint fit")
    with Image.open(figure) as image:
        image.verify()
