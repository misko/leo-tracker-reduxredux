import copy
from retry_predictive_numerical_failures import numerical_only


def test_numerical_retry_cannot_override_physical_or_ownership_failure():
    row=dict(gates=dict(tracks=[dict(compatible=True)]),linear_gates=[],final_phase_change_s=.001,
        endpoint_east_north_km=[0,0],lost_points=0,history=[dict(success=False)],
        phase_resolution_audit=dict(local_agreement=True),family=dict(phase_boundary_mass=0))
    control=dict(arms={a:copy.deepcopy(row) for a in ('c0','fitted_c')},paired_valid=False)
    addition=copy.deepcopy(control);replay=dict(all_verified=True)
    assert numerical_only(control,addition,replay)
    assert not numerical_only(control,addition,dict(all_verified=False))
    addition['arms']['c0']['gates']['tracks'][0]['compatible']=False
    assert not numerical_only(control,addition,replay)
    addition=copy.deepcopy(control);addition['arms']['fitted_c']['lost_points']=1
    assert not numerical_only(control,addition,replay)
