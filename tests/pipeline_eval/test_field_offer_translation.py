import math

import pytest

from reports.ALGO08.v3.field_offer_translation import OFFER_PINS, PINS, digest, read, translated_offer


@pytest.mark.parametrize("label,direction", [("east", 1), ("west", -1)])
def test_translated_offers_use_original_frame(label, direction):
    offer = {"center": [37.906, -122.545], "width_km": 25.0, "screen_center": [37.5, -122.0]}
    expected = PINS / f"field-offer-translation-{label}.json"
    translated = translated_offer(offer, direction)
    assert translated == read(expected)
    assert digest(expected) == OFFER_PINS[label]
    assert translated["center"][0] == offer["center"][0]
    assert translated["screen_center"] == offer["screen_center"]
    assert translated["width_km"] == offer["width_km"]
    scale = 111.32 * math.cos(math.radians(offer["center"][0]))
    assert (translated["center"][1] - offer["center"][1]) * scale == pytest.approx(direction * 12.5)


def test_region_figure_uses_one_fixed_frame_for_bars_survey_and_estimates():
    from reports.ALGO08.v3.field_offer_translation_figure import figure

    data = {name: dict(region=dict(center=[0, east/111.32], width_km=25.),
                       arms=dict(fitted_c=dict(latlon=[0, point/111.32], error_km=abs(point-5))))
            for name, east, point in (("original", 0, 5), ("east", 12.5, 5), ("west", -12.5, 0))}
    axes, = figure(data, [0, 5/111.32]).axes
    assert [bar.get_x() for bar in axes.patches] == pytest.approx([-12.5, 0, -25])
    assert [dots.get_offsets()[0][0] for dots in axes.collections] == pytest.approx([5, 5, 0])
    assert axes.lines[0].get_xdata() == pytest.approx([5, 5])
