"""Actual independent epoch perturbations and complete association-weight gradients."""
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save,digest,verify_sources
from acquire import enu_state_ecef_km,WGS84_A_KM,WGS84_F
from visibility_geometry_adapter import visibility_geometry
from visibility_state_gradient import weight_components,selected_weight_gradient
from shared_visibility_port import SharedVisibilityPort

HERE=Path(__file__).resolve().parent


def main():
    cases=[('DS9-B01-S1',0,'independent-v2/DS9-B01'),('DS10-B01-S1',0,'independent-v2/DS10-B01'),
           ('DS11-B01-S1',0,'independent-v2/DS11-B01'),('DS11-B03-D2',60,'constituent-pair-v3/DS11-B03-D2')]
    rows=[];inputs={};scales=np.array([WGS84_A_KM**2,WGS84_A_KM**2,(WGS84_A_KM*(1-WGS84_F))**2])
    for unit,track,directory in cases:
        path=HERE/directory/(unit+'.json');assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        receipt=json.loads(path.read_text());verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs']);inputs[str(path)]=digest(path)
        binding,scans,columns,precision,ports=prepare_window(unit);port=ports[track];likelihood=port.local.likelihood
        assert receipt['inputs']=={k:v for s,_,_ in scans for k,v in s.inputs.items()}
        state=np.asarray(receipt['best']['mean'])[port.columns];config=likelihood.config
        def receiver(e,n):return enu_state_ecef_km(e,n,likelihood.height_surface(e,n),config.prior_center_lat_deg,config.prior_center_lon_deg)
        def evaluate(x):
            margins,jac=visibility_geometry(likelihood,x,receiver,scales)
            return margins,weight_components(margins,jac,.1,config.signal_prior)
        margins,components=evaluate(state);count=len(components[2])
        selected=sorted(set([0,count-1,int(np.argmin(abs(margins.min(axis=1))))]))
        model=SharedVisibilityPort(port.local,.1)
        selected=sorted(set(selected+[int(np.argmax(model.score_all(state)[:-1]))]))
        branches=selected+[count];checks=[]
        for coordinate in [0,1,2,3,4,*[5+i for i in selected]]:
            delta=np.zeros_like(state);delta[coordinate]=.0001
            mp,cp=evaluate(state+delta);mm,cm=evaluate(state-delta)
            if coordinate>=5:
                other=np.arange(count)!=coordinate-5
                assert np.array_equal(mp[other],mm[other]),'epoch perturbed unrelated candidates'
            numeric=(model.score_all(state+delta)-model.score_all(state-delta))/.0002
            error=max(abs(numeric[i]-model.score_gradient(state,i)[coordinate]) for i in branches)
            assert error<1e-4,(unit,coordinate,error)
            checks.append(dict(coordinate=coordinate,max_error=float(error)))
        bg=selected_weight_gradient(components,count)
        assert abs(bg[2]-sum(bg[5:]))<1e-12
        rows.append(dict(unit=unit,track=track,candidates=count,selected_candidate_indices=selected,checks=checks,
                         epoch_isolation_exact=True,background_clock_equals_epoch_sum=True))
    save(HERE/'shared-visibility-port-check-v1.json',dict(rows=rows,input_sha256=inputs,
        source_sha256={str(p):digest(p) for p in [Path(__file__).resolve(),HERE/'shared_visibility_port.py',HERE/'visibility_state_gradient.py',HERE/'shared_threshold_weights.py',HERE/'visibility_geometry_adapter.py']},
        qualification='Full signal/background branch scores at illustrative0.1degree width. Four fixed tracks; selected epoch and signal branches plus background checked. No optimization or geographic scoring.'))
    print(json.dumps(rows,indent=2),flush=True)


if __name__=='__main__':main()
