"""All-cohort structural and dimensional audit of frozen receiver adapters."""
from pathlib import Path
import json
import numpy as np
from witness import replay,read,write,HERE
from adapter import build_method
from probe_ds23_graph_seeded_paths import build as original_build
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from matched_controls import factor_contract,measurement_binding,assert_factor_contract

def check_loading(p,method,*,predictive=False):
    width=p.smooth.shape[1]//2;old=width-31
    assert old==11 and width==42
    expected=projected_receiver_basis(p.flat_times,spacing_s=10.,width_s=5.)*50.
    if method=='fast_rx1_rf50':expected*=p.q[:,None]
    actual=p.smooth[:,old:width]*200.
    # In a view, receiver ownership is encoded by its hardware offset columns.
    rx1=(p.hardware[:,:2]!=0).any(axis=1)
    expected*=rx1[:,None]
    difference=float(np.max(abs(expected-actual))) if len(actual) else 0.
    assert difference<2e-12
    assert np.linalg.norm(p.smooth[:,width+old:]*200.)==0
    return difference

def main():
    protocol=read(HERE/'protocol.json');records=[];maximum=0.
    for case in protocol['cases']:
        d=replay(case);binding=measurement_binding(d);reference=np.zeros(len(d['means']));contracts=[]
        for arm in ('c0','fitted_c'):
            baseline=original_build(d,'default',arm,reference);expected=factor_contract(baseline,d['entries']);contracts.append(expected)
            for method in ('fast_rx1_rf50','fast_rx1_hz50'):
                p=build_method(d,arm,reference,case,method)
                assert_factor_contract(p,d['entries'],expected)
                assert p.labels==baseline.labels and p.supported==baseline.supported
                for name in ('hardware','constants','phase_sigma','point_noise'):
                    np.testing.assert_array_equal(getattr(p,name),getattr(baseline,name))
                old=baseline.smooth.shape[1]//2;new=p.smooth.shape[1]//2
                np.testing.assert_array_equal(p.smooth[:,:old],baseline.smooth[:,:old])
                np.testing.assert_array_equal(p.smooth[:,new:new+old],baseline.smooth[:,old:])
                difference=check_loading(p,method);predictive_difference=None
                if d['entries']:
                    view,values,sigma,groups,slices=linear_geometry(p,d['entries'])
                    old_view,old_values,old_sigma,old_groups,old_slices=linear_geometry(baseline,d['entries'])
                    np.testing.assert_array_equal(values,old_values);np.testing.assert_array_equal(sigma,old_sigma)
                    np.testing.assert_array_equal(groups,old_groups)
                    predictive_difference=check_loading(view,method,predictive=True)
                    maximum=max(maximum,predictive_difference)
                maximum=max(maximum,difference)
                assert measurement_binding(d)==binding
                assert all(b.shape[1]==11 for b in d['scan'].rx_basis)
                records.append(dict(case=case,arm=arm,method=method,physical_factor_contract=expected,
                    active_points=int(p.keep.sum()),predictive_entries=len(d['entries']),
                    maximum_curved_loading_error_hz=difference,maximum_predictive_loading_error_hz=predictive_difference,
                    original_inputs_unchanged=True,point_noise_unchanged=True,causal_receipt_unchanged=True,
                    old_receiver_features_unchanged=True,all_RX2_extra_columns_zero=True))
        assert contracts[0]==contracts[1]
        print(case,'both arms and loadings passed',flush=True)
    write(HERE/'final_adapter_audit.json',dict(records=records,passed=True,records_checked=len(records),
        cases=protocol['cases'],maximum_loading_error_hz=maximum,
        membership_identical_across_both_c_arms_and_both_receiver_interventions=True,
        RF_loading='50 Hz * (RF/11.5 GHz) * fixed temporal basis on RX1',
        Hz_loading='50 Hz * fixed temporal basis on RX1',
        target_causal_orbit_priors_and_all_original_measurement_factors_unchanged=True))

if __name__=='__main__':main()
