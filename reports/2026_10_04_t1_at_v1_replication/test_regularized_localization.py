from types import SimpleNamespace
import numpy as np
import pytest
from regularized_localization import select_input, remap_seed


def fixture():
    d=SimpleNamespace(**{k:np.arange(4,dtype=float) for k in ('times','measured','rf','margin')},
        receiver=np.zeros(4,int),channel=np.ones(4,int),group=np.arange(4),original_rows=np.array([10,20,30,40]),
        numbers=np.array([100,200,300]),position=np.zeros((3,2,3)),velocity=np.ones((3,2,3)),
        initial=np.r_[1.,2.,np.zeros(7)])
    receipt=dict(final=dict(assignments=[dict(row_index=40,catalog_number=300),dict(row_index=20,catalog_number=100)],
        selected=[dict(catalog_number=300,offset_s=2.),dict(catalog_number=100,offset_s=-3.)]))
    return d,receipt


def test_selection_preserves_raw_data_and_calibration_per_window():
    raw,receipt=fixture();d=select_input(raw,np.full(4,10.),receipt)
    np.testing.assert_array_equal(d.original_rows,[20,40])
    np.testing.assert_array_equal(d.owners,[100,300])
    np.testing.assert_array_equal(d.numbers,[100,300])
    np.testing.assert_allclose(d.measured,[-9.,-7.])
    np.testing.assert_array_equal(raw.measured,np.arange(4))
    np.testing.assert_array_equal(d.initial,[1.,2.,0.,0.,0.,0.,-3.,2.])


def test_duplicate_windows_rejected():
    raw,receipt=fixture();receipt['final']['assignments']*=2
    with pytest.raises(ValueError,match='Duplicate'):select_input(raw,np.zeros(4),receipt)


def test_seed_transfer_uses_catalog_ids_and_new_association_timing():
    raw,receipt=fixture();d=select_input(raw,np.zeros(4),receipt)
    old=dict(parameters=np.r_[np.arange(6),[7.,8.]],coefficient=42.,point_km=[.1,.2])
    new=remap_seed(old,np.array([200,100]),d)
    np.testing.assert_array_equal(new['parameters'],np.r_[np.arange(6),[8.,2.]])
    assert new['coefficient']==42.
