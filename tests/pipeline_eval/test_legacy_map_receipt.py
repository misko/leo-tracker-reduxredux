import json
from math import nan

import pytest

from reports.ALGO08.v3.legacy_map_receipt import write


def test_legacy_map_receipt_keeps_exact_schema_order_precision_and_line_end(tmp_path):
    sample = dict(cutoff_utc_ns=1794702096144017710, utc="2026-11-15T00:21:36.144017710Z", members=[
        dict(kind="map", map=None, committed_bytes=24960000, elapsed_s=0.00019307445734739304, note="φ"),
        dict(kind="ordinary", counts={"full": 8, "prefix": 19}, cpu_s=-0.0)])
    path = tmp_path/"legacy-map-acquisition.json"
    write(path, sample)
    expected = (json.dumps(sample, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    assert path.read_bytes() == expected
    assert list(tmp_path.iterdir()) == [path]


def test_map_receipt_cannot_replace_an_existing_file(tmp_path):
    path = tmp_path/"legacy-map-acquisition.json"
    path.write_bytes(b"first")
    with pytest.raises(FileExistsError):
        write(path, {"different": True})
    assert path.read_bytes() == b"first"
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_numbers_publish_no_partial_target(tmp_path):
    with pytest.raises(ValueError):
        write(tmp_path/"legacy-map-acquisition.json", {"invalid": nan})
    assert not list(tmp_path.iterdir())
