"""Conditional local geometry information retained after nuisance projection."""
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

def projected_information(jacobian,nuisance):
    j=np.asarray(jacobian,float);x=np.asarray(nuisance,float)
    residual=j-x@np.linalg.lstsq(x,j,rcond=None)[0] if x.shape[1] else j
    return residual.T@residual

def main():
    root=Path(__file__).resolve().parent;banks=json.loads((root/'banks.json').read_text());protocol=json.loads((root/'protocol.json').read_text())
    time_scores=sum(logsumexp(np.array(b['cfo_train']),axis=-1) for b in banks);ti=int(np.argmax(time_scores));jac=[];delay=[];group_ids=[];assignments=[]
    for gi,b in enumerate(banks):
        ci=int(np.argmax(np.array(b['cfo_train'])[ti]));jac.extend(np.array(b['geometry_jacobian_rad_per_km'])[ti,ci]);delay.extend(2*np.pi*np.array(b['df'])*1e-6);group_ids.extend([gi]*len(b['df']));assignments.append(ci)
    jac=np.array(jac);group_ids=np.array(group_ids);raw=projected_information(jac,np.empty((len(jac),0)));ind=projected_information(jac,np.column_stack([group_ids==i for i in range(len(banks))]));shared=projected_information(jac,np.array(delay)[:,None])
    result=dict(scope='Conditional MAP source-pair geometry, local fixed-baseline Jacobian; unit phase precision; not position accuracy or a calibrated posterior',orbit_time_s=protocol['timing_offsets_s'][ti],pair_indices=assignments,observations=len(jac),models={})
    for name,matrix in [('known_response',raw),('independent_pair_offsets',ind),('shared_delay',shared)]:
        result['models'][name]=dict(information_per_km2=matrix.tolist(),eigenvalues_per_km2=np.linalg.eigvalsh(matrix).tolist(),trace_fraction_of_known_response=float(np.trace(matrix)/np.trace(raw)))
    (root/'information.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
