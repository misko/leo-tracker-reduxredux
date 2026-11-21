import pytest

from leo.contracts.algo08_region import Algo08Region


def test_screen_defaults_to_search_and_round_trips_with_explicit_override():
    offer = Algo08Region.parse(dict(center=[-38, 23], width_km=18))
    assert offer.screen_center == offer.center == (-38, 23)
    separate = Algo08Region.parse(dict(offer.document(), screen_center=[-37.5, 24]))
    assert separate.center == offer.center and separate.screen_center != offer.screen_center
    assert Algo08Region.parse(separate.document()) == separate


@pytest.mark.parametrize("change", [
    {"center": [True, 0]}, {"center": [89.99, 0]}, {"center": [0, 179.99]},
    {"screen_center": [1, float("nan")]}, {"center": [1]}, {"width_km": float("inf")},
    {"width_km": 0}, {"width_km": True}, {"evaluation_reference": [0, 0]},
])
def test_invalid_or_unrepresentable_offer_is_rejected(change):
    with pytest.raises(ValueError):
        Algo08Region.parse(dict({"center": [20, 30], "width_km": 40}, **change))
