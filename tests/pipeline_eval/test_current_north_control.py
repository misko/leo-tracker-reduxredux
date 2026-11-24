from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from current_north_control import comparison


def test_compare_both_encoded_and_decoded_image_hashes_after_json_roundtrip():
    common = dict(native_sha256="raw", opportunity_sha256="timeline", grid_points=137,
                  verified=dict(arms={}, owners={}, receipt={"terminal_sha256":"terminal"}))
    dims = dict(sha256="encoded", rgba_sha256="decoded")
    old = dict(common, figures={"position": dict(dims, size=[100, 80])})
    new = dict(common, figures={"position": dict(dims, size=(100, 80))})
    assert all(comparison(old, new).values())
    new["figures"]["position"]["rgba_sha256"] = "different"
    assert not comparison(old, new)["images"]
