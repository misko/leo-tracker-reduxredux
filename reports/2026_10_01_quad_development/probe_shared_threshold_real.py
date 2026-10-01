"""One rejected track's clock perturbation under an alternative visibility model."""
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save,digest,verify_sources
from acquire import enu_state_ecef_km,WGS84_A_KM,WGS84_F
from shared_threshold_weights import shared_log_weights

HERE=Path(__file__).resolve().parent


def main():
    unit='DS11-B03-D2';path=HERE/'constituent-pair-v3'/unit/(unit+'.json')
    assert digest(path)==path.with_suffix('.sha256').read_text().strip()
    receipt=json.loads(path.read_text());verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert receipt['binding']==binding and receipt['inputs']=={k:v for s,_,_ in scans for k,v in s.inputs.items()}
    state=np.asarray(receipt['best']['mean']);port=ports[60];likelihood=port.local.likelihood
    assert receipt['best']['associations'][60]==port.candidate_count
    local=state[port.columns];config=likelihood.config
    receiver=enu_state_ecef_km(local[0],local[1],likelihood.height_surface(local[0],local[1]),
                             config.prior_center_lat_deg,config.prior_center_lon_deg)
    b=WGS84_A_KM*(1-WGS84_F);up=receiver/np.array([WGS84_A_KM**2,WGS84_A_KM**2,b*b]);up/=np.linalg.norm(up)
    def margins(clock_delta):
        position,_=likelihood._orbit_states_per_satellite(local[2]+clock_delta+local[5:])
        line=position-receiver;direction=line/np.linalg.norm(line,axis=-1,keepdims=True)
        return np.degrees(np.arcsin(np.clip(direction@up,-1,1)))+config.horizon_margin_deg
    center=margins(0);h=1e-5;jac=((margins(h)-margins(-h))/(2*h))[:,:,None]
    def alternative(delta):
        weights,gradient,info=shared_log_weights(margins(delta),jac,.1,config.signal_prior)
        return float(weights[-1]+likelihood.background_log_likelihood),gradient,info
    value,g,info=alternative(0);assert g is not None
    rows=[]
    for step in [1e-3,5e-4,1e-4,1e-5,1e-6]:
        minus=alternative(-step)[0];plus=alternative(step)[0]
        rows.append(dict(step_s=step,score_jump=plus-minus,finite_derivative=(plus-minus)/(2*step),
            chain_derivative=float(g[-1,0])))
    save(HERE/'shared-threshold-real-probe-v1.json',dict(unit=unit,track_index=60,width_deg=.1,
        background_score=value,minimum_ties=int(np.sum(info['tie_counts']>1)),rows=rows,
        input_sha256={str(path):digest(path)},source_sha256={str(p):digest(p) for p in [Path(__file__).resolve(),HERE/'shared_threshold_weights.py',HERE/'smooth_visibility_weights.py']},
        qualification='One fixed background track; no fit, assignment update, complete objective audit or geographic scoring. Width0.1deg illustrative. Geometry clock derivative uses central differences at1e-5s. Original rejected outcome unchanged.'))
    print(json.dumps(rows,indent=2),flush=True)


if __name__=='__main__':main()
