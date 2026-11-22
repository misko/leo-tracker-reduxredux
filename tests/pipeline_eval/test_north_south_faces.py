from importlib import import_module

import pytest
from tools.pipeline_eval.qualification.score_paired_holdout import offset_km

faces = import_module("reports.ALGO08.single-core-2x.north_south_faces")


@pytest.mark.parametrize("lat, sign", [(48., 1), (-33., -1)])
def test_public_offers_cross_the_assigned_face_without_disclosing_a_coordinate(lat, sign):
    site = (lat, 20.)
    regions = faces.offers(site, sign)
    for name, offset in (("inside", 12.4), ("outside", 12.6)):
        region = regions[name]
        assert all(a != b for a, b in zip(site, region["center"], strict=True))
        assert region["screen_center"] == region["center"]
        assert offset_km(region, site) == pytest.approx((sign * 5., sign * offset))
