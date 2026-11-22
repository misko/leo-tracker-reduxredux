from importlib import import_module

import pytest


trial = import_module("reports.ALGO08.single-core-2x.frame_plane_offers")


@pytest.mark.parametrize("site,other", [("north", "south"), ("south", "north")])
def test_shifted_offers_bind_search_and_sky_screen_to_the_measured_site(site, other):
    offers = trial.saved_offers()
    original = offers[f"{site}-edge"]["offer"]
    shifted = trial.shifted_offers(site, original, offers)
    assert shifted == {k: offers[k]["offer"] for k in (f"{site}-mirror-outside", f"{site}-far")}
    with pytest.raises(ValueError, match="screening"):
        trial.shifted_offers(site, dict(original, screen_center=offers[f"{other}-edge"]["offer"]["center"]), offers)
    with pytest.raises(ValueError, match="search"):
        trial.shifted_offers(other, original, offers)
