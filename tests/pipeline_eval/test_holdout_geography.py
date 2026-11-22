import numpy as np

from tools.pipeline_eval.qualification import holdout_geography
from tools.pipeline_eval.qualification.compact_blind_generator import local_offset
from tools.pipeline_eval.qualification.holdout_geography import CONTAINING, DEVELOPMENT_CENTERS, EDGE_CASES, fresh_layout, fresh_offers, verifies_drawn_sites
from tools.pipeline_eval.scoring import distance_km


def test_frozen_seed_reproduces_sites_and_edges_and_respects_site_level_separation():
    orientations = set()
    for seed in range(32):
        layout = fresh_layout(np.random.default_rng(seed))
        assert layout == fresh_layout(np.random.default_rng(seed))
        (first, edge_a), (second, edge_b) = layout
        assert {edge_a, edge_b} == {"lower", "upper"}
        assert first[0] * second[0] < 0
        assert 8 <= abs(first[0]) <= 26 and 34 <= abs(second[0]) <= 54
        assert distance_km(first, second) >= 1600
        assert all(distance_km(new, old) >= 1600 for new in (first, second)
                   for old in DEVELOPMENT_CENTERS)
        orientations.add((first[0] > 0, edge_a))
    assert len(orientations) == 4


def test_offer_labels_match_the_search_square_across_widths_and_hemispheres():
    rng = np.random.default_rng(592)
    for _ in range(10):
        for site, _edge in fresh_layout(rng):
            width, offers = fresh_offers(rng, site)
            assert 18 <= width <= 40
            assert set(offers) == EDGE_CASES
            edge_faces = []
            for name, center in offers.items():
                east_north = local_offset(site, center)
                axis = int(np.argmax(np.abs(east_north)))
                offset = abs(east_north[axis])
                assert all(abs(x) > 0 for x in east_north)
                assert (offset < width / 2) == (name in CONTAINING)
                assert (offset > width) == (name == "far")
                if name.startswith("edge-"):
                    assert .05 <= abs(offset - width / 2) <= .25
                    edge_faces.append((axis, np.sign(east_north[axis])))
            assert len(set(edge_faces)) == 1


def test_actual_sites_must_cover_both_private_boxes_even_with_distinct_recordings():
    seed = (45).to_bytes(32, "big").hex()
    (a, _), (b, _) = fresh_layout(np.random.default_rng(45))
    jittered = [(a[0] + 1.99, a[1] - 1.99), (b[0] - 1.9, b[1] + .5)]
    assert verifies_drawn_sites(seed, list(reversed(jittered)))
    assert not verifies_drawn_sites(seed, [a, jittered[0]])
    assert not verifies_drawn_sites(seed, [a, DEVELOPMENT_CENTERS[0]])
    assert not verifies_drawn_sites(None, jittered)


def test_offers_redraw_an_along_face_offset_that_rounds_onto_the_receiver():
    class Draw:
        def __init__(self):
            self.rng = np.random.default_rng(17)
            self.along_draws = 0

        def uniform(self, low, high):
            if (low, high) == (-.75, .75):
                self.along_draws += 1
                if self.along_draws == 1:
                    return 1e-18
            return self.rng.uniform(low, high)

        def integers(self, high):
            return self.rng.integers(high)

        def choice(self, values):
            return self.rng.choice(values)

    draw = Draw()
    site = (-41., 33.)
    _, offers = fresh_offers(draw, site)
    assert draw.along_draws == 5
    assert all(lat != site[0] and lon != site[1] for lat, lon in offers.values())


def test_draw_discards_a_height_development_area_before_creating_waveforms(monkeypatch):
    overlaps, independent = (v.to_bytes(32, "big") for v in (9, 45))
    assert not verifies_drawn_sites(overlaps.hex(), holdout_geography.seeded_centers(overlaps))
    assert verifies_drawn_sites(independent.hex(), holdout_geography.seeded_centers(independent))
    seeds = iter([overlaps, independent])
    monkeypatch.setattr(holdout_geography.secrets, "token_bytes", lambda _n: next(seeds))
    assert holdout_geography.new_confirmation_seed() == independent


def test_austin_receiver_area_is_excluded_from_selection_and_final_scoring(monkeypatch):
    overlap, independent = (v.to_bytes(32, "big") for v in (1, 45))
    independent_sites = holdout_geography.seeded_centers(independent)
    austin_sites = [(29.8, -98.1), independent_sites[1]]
    # Inject draws to check both consumers without touching a real confirmation seed.
    monkeypatch.setattr(holdout_geography, "seeded_layout", {
        seed: list(zip(sites, ("lower", "upper"), strict=True))
        for seed, sites in [(overlap, austin_sites), (independent, independent_sites)]
    }.__getitem__)
    seeds = iter([overlap, independent])
    monkeypatch.setattr(holdout_geography.secrets, "token_bytes", lambda _n: next(seeds))
    assert holdout_geography.new_confirmation_seed() == independent
    assert not verifies_drawn_sites(overlap.hex(), austin_sites)
    assert verifies_drawn_sites(independent.hex(), independent_sites)
