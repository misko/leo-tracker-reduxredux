from types import SimpleNamespace
import numpy as np
import pytest

from ds23_converter_drift import target_loadings,change_scan


def geometry():
    return dict(targets=[dict(channel=c,edge='lower',rf_center_hz=rf,lnb_lo_hz=lo,if_center_hz=rf-lo)
        for c,rf,lo in [(1,10.71e9,9.75e9),(2,10.96e9,9.75e9),(5,11.71e9,10.6e9),(6,11.96e9,10.6e9)]])


def test_trace_normalization_preserves_average_pointwise_variance():
    g=geometry();reference,_=target_loadings(g,'RF')
    for law in ('LNB','tuner'):
        actual,_=target_loadings(g,law)
        assert np.mean(actual**2)==pytest.approx(np.mean(reference**2),rel=1e-14)


def test_same_LO_channels_share_loading_and_same_IF_channels_would_share_tuner_loading():
    g=geometry();lo,_=target_loadings(g,'LNB');assert lo[0]==lo[1] and lo[2]==lo[3]
    tuner,_=target_loadings(g,'tuner');assert tuner[1]>tuner[0]


def test_null_exact_and_physical_changes_do_not_change_observations_or_doppler_frequency():
    g=geometry();tracks=[dict(channel=t['channel'],rf_hz=t['rf_center_hz'],values=np.array([1.,2.])) for t in g['targets']]
    scan=SimpleNamespace(tracks=tracks,rx_basis=[np.eye(2) for _ in tracks])
    null,_=change_scan(scan,g,'RF')
    for a,b in zip(null.rx_basis,scan.rx_basis):np.testing.assert_array_equal(a,b)
    changed,receipt=change_scan(scan,g,'LNB')
    assert changed.tracks is scan.tracks
    for i,t in enumerate(tracks):
        expected=target_loadings(g,'LNB')[0][i]
        np.testing.assert_allclose((t['rf_hz']/11.5e9)*changed.rx_basis[i],expected*scan.rx_basis[i])
        assert changed.rx_basis[i].shape==scan.rx_basis[i].shape
    assert receipt['orbital_Doppler_RF_scale_unchanged']


def test_ambiguous_or_inconsistent_converter_metadata_is_rejected():
    g=geometry();g['targets'][0]['if_center_hz']+=1e6
    with pytest.raises(ValueError):target_loadings(g,'LNB')
