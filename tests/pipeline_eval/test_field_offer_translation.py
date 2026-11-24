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
