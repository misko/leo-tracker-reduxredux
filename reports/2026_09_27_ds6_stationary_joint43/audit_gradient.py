"""Independent full-profile finite differences at frozen joint winners."""
import argparse
import json
import numpy as np
from run_stationary_joint import HERE, REPORTS, digest, load_model


def run(name):
    output=HERE/f'{name}-gradient.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'run_stationary_joint.py')==protocol['source_sha256']
    for path,value in protocol['files'].items():assert digest(REPORTS/path)==value
    result_path=HERE/f'{name}.json'
    result=json.loads(result_path.read_text())
    assert result['complete'] and result['protocol_sha256']==digest(HERE/'protocol.json')
    assert result['sessions']==protocol['splits'][name]
    x=np.array(result['best']['x']);rows=[]
    for i,session in enumerate(result['sessions']):
        model,_,_=load_model(session,protocol['center'])
        point=np.array([x[0],x[1],x[i+2]])
        analytic=model.evaluate(point,True)['gradient'];numeric=[]
        for j in range(3):
            plus=point.copy();minus=point.copy();plus[j]+=1e-4;minus[j]-=1e-4
            if j==2:plus[j]=min(5.,plus[j]);minus[j]=max(-5.,minus[j])
            numeric.append((model.evaluate(plus)['train']-model.evaluate(minus)['train'])/(plus[j]-minus[j]))
        rows.append(dict(session_id=session,envelope_gradient=analytic.tolist(),numeric_gradient=numeric,
            maximum_difference=float(np.max(np.abs(analytic-numeric)))))
        print(json.dumps(rows[-1]),flush=True)
    envelope=np.array([r['envelope_gradient'] for r in rows]);numeric=np.array([r['numeric_gradient'] for r in rows])
    global_envelope=np.r_[envelope[:,:2].sum(axis=0),envelope[:,2]]
    global_numeric=np.r_[numeric[:,:2].sum(axis=0),numeric[:,2]]
    audit=dict(fit=name,complete=True,source_sha256=digest(HERE/'audit_gradient.py'),result_sha256=digest(result_path),
        rows=rows,global_envelope_gradient=global_envelope.tolist(),global_numeric_gradient=global_numeric.tolist(),
        maximum_global_difference=float(np.max(np.abs(global_envelope-global_numeric))))
    with output.open('x') as f:json.dump(audit,f,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fit',choices=['all','A','B'],required=True)
    run(parser.parse_args().fit)
