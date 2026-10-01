"""Validate actual E/N and clock elevation derivatives; no inference or geography."""
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save,digest,verify_sources
from acquire import enu_state_ecef_km,WGS84_A_KM,WGS84_F
from visibility_geometry_adapter import visibility_geometry

HERE=Path(__file__).resolve().parent


def main():
    cases=[('DS9-B01-S1',0,'independent-v2/DS9-B01'),('DS10-B01-S1',0,'independent-v2/DS10-B01'),
           ('DS11-B01-S1',0,'independent-v2/DS11-B01'),('DS11-B03-D2',60,'constituent-pair-v3/DS11-B03-D2')]
    rows=[];inputs={}
    scales=np.array([WGS84_A_KM**2,WGS84_A_KM**2,(WGS84_A_KM*(1-WGS84_F))**2])
    for unit,index,directory in cases:
        path=HERE/directory/(unit+'.json');assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        receipt=json.loads(path.read_text());verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
        inputs[str(path)]=digest(path)
        binding,scans,columns,precision,ports=prepare_window(unit);port=ports[index];likelihood=port.local.likelihood
        assert receipt['binding']==binding and receipt['inputs']=={k:v for s,_,_ in scans for k,v in s.inputs.items()}
        state=np.asarray(receipt['best']['mean'])[port.columns];config=likelihood.config
        def receiver(e,n):return enu_state_ecef_km(e,n,likelihood.height_surface(e,n),config.prior_center_lat_deg,config.prior_center_lon_deg)
        def margins(x):
            p,_=likelihood._orbit_states_per_satellite(x[2]+x[5:]);r=receiver(x[0],x[1])
            line=p-r;direction=line/np.linalg.norm(line,axis=-1,keepdims=True);up=r/scales;up/=np.linalg.norm(up)
            return np.degrees(np.arcsin(np.clip(direction@up,-1,1)))+config.horizon_margin_deg
        value,jac=visibility_geometry(likelihood,state,receiver,scales)
        assert np.max(abs(value-margins(state)))<1e-9
        checks=[]
        for d in [0,1,2]:
            for h in [.0005,.0001]:
                delta=np.zeros_like(state);delta[d]=h
                finite=(margins(state+delta)-margins(state-delta))/(2*h)
                error=float(np.max(abs(finite-jac[...,d])))
                checks.append(dict(coordinate=['east_km','north_km','clock_s'][d],step=h,max_error=error))
                assert error<1e-4,(unit,d,h,error)
        rows.append(dict(unit=unit,track=index,candidates=value.shape[0],observations=value.shape[1],checks=checks))
    save(HERE/'visibility-geometry-check-v1.json',dict(rows=rows,input_sha256=inputs,
        source_sha256={str(p):digest(p) for p in [Path(__file__).resolve(),HERE/'visibility_geometry_adapter.py',HERE/'elevation_geometry.py']},
        qualification='All candidate elevation margins in four fixed tracks. Hermite position derivative analytic; receiver spatial mapping derivative central difference at0.001km. Independent full-score geometry differences at0.0005/0.0001 coordinate units. No fit or reference scoring.'))
    print(json.dumps(rows,indent=2),flush=True)


if __name__=='__main__':main()
