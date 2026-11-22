from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from math import cos, radians
from pathlib import Path

from PIL import Image, PngImagePlugin
import pytest


def report(name):
    folder = Path(__file__).resolve().parents[2]/"reports/ALGO08/single-core-2x"
    spec = spec_from_file_location(name, folder/(name+".py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("site", [(47., 16.), (-32., 21.)])
def test_exact_face_differs_from_a_contained_site_one_hundred_metres_inside(site):
    trial = report("edge_trial")
    for recording in ("opaque-a","opaque-b","opaque-c","opaque-d"):
        offer = trial.near_offer(recording, site, 25.)
        assert not trial.on_face(site, offer)
    assert trial.on_face((site[0]+12.5/111.,site[1]), dict(center=site,width_km=25.))


def test_png_trial_checks_pixels_and_text_and_density():
    trial = report("png_trial")
    raw = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Software","test")
    Image.new("RGBA",(6,7),(5,25,120,180)).save(raw, format="PNG", pnginfo=metadata, dpi=(120,120))
    image = Image.open(BytesIO(raw.getvalue()))
    rows = trial.compare([(raw.getvalue(),image)])
    assert len(rows)==6
    assert all(row["pixels_and_metadata_matched"]==1 for row in rows)


@pytest.mark.parametrize("site", [(47., 16.), (-32., 21.)])
def test_mirrored_offers_bracket_same_face_with_signed_clearance(site):
    trial = report("edge_trial")
    for recording in ("first", "second", "third", "fourth"):
        inside, outside = [trial.near_offer(recording, site, 25., outside=flag) for flag in (False, True)]
        offsets = []
        for offer in (inside, outside):
            lat, lon = offer["center"]
            offsets.append(((lat-site[0])*111., (lon-site[1])*111.32*cos(radians(lat))))
        axis = max(range(2), key=lambda i: abs(offsets[0][i]))
        assert offsets[0][axis] * offsets[1][axis] > 0
        assert [abs(delta[axis]) for delta in offsets] == pytest.approx([12.4, 12.6])
        assert all(delta[1-axis] == 0 for delta in offsets)
