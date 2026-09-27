"""Artifact coverage and consistency checks; not a positioning truth test."""
import json
from pathlib import Path
import numpy as np
import pytest
from robust import robust_scores,fit_offset
HERE=Path(__file__).resolve().parent

@pytest.mark.parametrize('folder',['','robust','robust-extended'])
def test_exact_search_covers_same_points_and_frozen_time_grids(folder):
    protocol=json.loads((HERE/folder/'protocol.json').read_text());results=json.loads((HERE/folder/'results.json').read_text())
    assert results['complete']
    intended={tuple(p) for p in protocol['coordinates']}
    assert len(intended)==81
    for arm in ['integer','quarter']:
        rows=[r for r in results['rows'] if r['arm']==arm]
        assert len(rows)==81
        assert {(r['latitude'],r['longitude']) for r in rows}==intended
        for key in ['cfo','joint']:
            assert results['best'][arm][key]==max(rows,key=lambda r:r[key+'_train'])
            time=results['best'][arm][key][key+'_map_time_s']
            assert -5<=time<=5 and np.isclose(time*(1 if arm=='integer' else 4),round(time*(1 if arm=='integer' else 4)))

@pytest.mark.parametrize('folder',['','robust','robust-extended'])
def test_shortlists_are_unique_and_cover_every_input_track(folder):
    s=json.loads((HERE/folder/'shortlists.json').read_text());inputs=json.loads((HERE.parent/'2026_09_27_ds6_alltrack_phase/inputs.json').read_text())
    assert {t['track_id'] for t in s['tracks']}=={t['track_id'] for t in inputs['tracks']}
    for track in s['tracks']:
        assert len(track['catalogue_indices'])==len(set(track['catalogue_indices']))==len(track['satellite_numbers'])
    assert 0<=s['minimum_top_eight_mass_at_anchors']<=1

def test_robust_offset_resists_one_large_outlier():
    data=np.array([0.,5.,-5.,0.,10000.])
    assert abs(fit_offset(data))<2.
    assert abs(data.mean())>1900

def test_held_samples_do_not_fit_robust_offset_or_training_score():
    data=np.array([400.,420.,380.,410.,415.,390.]);mask=np.array([True,True,True,False,False,False])
    a,j=robust_scores(data,mask);data[~mask]+=10000;b,k=robust_scores(data,mask)
    assert a==b and k<j
