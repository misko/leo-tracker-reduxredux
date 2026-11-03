import importlib.util,sys,zipfile
from pathlib import Path
import numpy as np,pytest
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("fixed_geoid",HERE/"geoid.py"); assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=module; SPEC.loader.exec_module(module)


def tiny_grid(path):
    text="0 238 1 1 2 2 1\n-40 -30\n-20 -10\n"
    with zipfile.ZipFile(path,"w") as z:z.writestr("tiny.asc",text)


def test_bilinear_and_height_sign(tmp_path):
    path=tmp_path/"grid.zip"; tiny_grid(path); digest=module._sha256(path)
    model=module.load_height_model(path,expected_sha256=digest)
    # Patch coordinates through the grid midpoint without involving geodesic mapping.
    object.__setattr__(model,"lat0",module.CENTER_LAT_DEG-0.5)
    object.__setattr__(model,"lon0_360",module.CENTER_LON_DEG%360-0.5)
    assert model.geoid_undulation_m(0,0)==pytest.approx(-25.)
    assert model(0,0)==pytest.approx((30.48-25.)/1000.)


def test_authoritative_grid_matches_archived_roof_value():
    if not module.DEFAULT_GRID.exists(): pytest.skip("requires cached NOAA GEOID18 grid")
    model=module.load_height_model()
    # EN offset under the same authalic mapping, determined by inverse great-circle geometry.
    east,north=-87.04460986596906,-80.98813710699791
    assert model.geoid_undulation_m(east,north)==pytest.approx(-32.477,abs=.002)
    value,gradient=model.value_and_gradient(east,north)
    assert value==pytest.approx(-.001997,abs=2e-6)
    assert np.all(np.isfinite(gradient))
    assert all(np.isfinite(model(e,n)) for e,n in ((489,0),(-489,0),(0,489),(0,-489)))


def test_digest_and_bounds_are_enforced(tmp_path):
    path=tmp_path/"grid.zip"; tiny_grid(path)
    with pytest.raises(ValueError,match="digest mismatch"): module.load_height_model(path)
