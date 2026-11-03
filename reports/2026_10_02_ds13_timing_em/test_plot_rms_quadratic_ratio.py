import json
import pytest
from plot_rms_quadratic_ratio import SOURCE, rms_ratio, track_rows


def test_ratio_direction():
    assert rms_ratio(100.,50.)==2.
    assert rms_ratio(50.,50.)==1.


@pytest.mark.parametrize('a,b',[(10,0),(10,-1),(float('nan'),2),(10,11)])
def test_invalid_ratio(a,b):
    with pytest.raises(ValueError):rms_ratio(a,b)


def test_all_saved_tracks_reproduce():
    rows=track_rows(json.loads(SOURCE.read_text()))
    assert len(rows)==22
    assert len({(r['scan'],r['catalog_number'],r['receiver']) for r in rows})==22
    assert all(r['ratio'] >= 1 for r in rows)
    largest=max(rows,key=lambda r:r['ratio'])
    assert (largest['scan'],largest['catalog_number'])==('A',64361)
