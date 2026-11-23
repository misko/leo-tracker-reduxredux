from importlib import import_module
from io import BytesIO
from pathlib import Path

import pytest


@pytest.fixture
def census(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(directory))
    return import_module("calibration_png_layers")


def test_native_stream_names_follow_bytes_and_original_figure_reuse(census):
    names = [f"web-png-{i}" for i in range(8)]
    products = {name: name.encode() for name in reversed(names)}
    figure_ids = (1, 1, 2, 2, 3, 4, 5, 6)
    streams = [
        dict(figure_number=figure, stream=BytesIO(products[name]))
        for name, figure in zip(names, figure_ids, strict=True)
    ]
    interpreted = census.name_outputs(streams, products)
    assert list(interpreted) == names
    assert tuple(row["figure_number"] for row in interpreted.values()) == figure_ids

    streams[-1]["stream"] = streams[0]["stream"]
    with pytest.raises(ValueError, match="does not identify"):
        census.name_outputs(streams, products)
    with pytest.raises(ValueError, match="shared orbit bases"):
        census.name_outputs(streams[:-1], products)


def test_fixed_zero_probe_leaves_fitted_inputs_and_original_packet_intact(census):
    packet = dict(
        arms=dict(
            c0=dict(endpoint_latlon=[1., 2.], residual_rms_hz=33.),
            fitted_c=dict(endpoint_latlon=[3., 4.], residual_rms_hz=37.),
        ),
        rows=dict(c0=["zero"], fitted_c=["fitted"]),
        position_path=dict(stages=[]),
    )
    altered = census.altered_fixed_zero(packet)
    assert altered["arms"]["c0"]["endpoint_latlon"] == [1.001, 2.]
    assert altered["arms"]["c0"]["residual_rms_hz"] == 40.
    assert packet["arms"]["c0"]["endpoint_latlon"] == [1., 2.]
    assert packet["arms"]["c0"]["residual_rms_hz"] == 33.
    assert altered["arms"]["fitted_c"] == packet["arms"]["fitted_c"]
    assert altered["rows"] is packet["rows"]
    assert altered["position_path"] is packet["position_path"]
