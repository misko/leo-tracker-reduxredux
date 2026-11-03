"""Predeclared information check: reject numerically flat all-null fits."""
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import harness


def check(model,x):
    x=np.asarray(x,dtype=float)
    result=model.evaluate(x)
    columns=[]
    for axis,step in enumerate((.001,.001,.0001)):
        delta=np.eye(3)[axis]*step
        columns.append(-(model.evaluate(x+delta)['gradient']-model.evaluate(x-delta)['gradient'])/(2*step))
    raw=np.column_stack(columns)
    matrix=(raw+raw.T)/2
    finite=bool(np.isfinite(matrix).all())
    eigen=np.linalg.eigvalsh(matrix) if finite else np.full(3,np.nan)
    positive=bool(finite and eigen.min()>0)
    horizontal=None
    if positive:
        schur=matrix[:2,:2]-np.outer(matrix[:2,2],matrix[2,:2])/matrix[2,2]
        horizontal=np.linalg.eigvalsh(schur).tolist()
    weight=float(sum(result['signal_weights']))
    qualified=bool(positive and weight>=3 and horizontal[0]>=1/144)
    return dict(scientifically_qualified=qualified,effective_signal_tracks=weight,
                information=matrix.tolist(),eigenvalues=eigen.tolist(),
                horizontal_profile_eigenvalues=horizontal,
                gradient_jacobian_asymmetry=float(np.max(np.abs(raw-raw.T))),
                minimum_required_horizontal_information=1/144)


def main(stage,variant,index):
    import model as plugin
    sys.path.insert(0,str(harness.ROOT/'tools'))
    import ds7_fast_baseline_adapter as baseline
    path=HERE/'runs'/stage/f'{variant}_{index:02d}.json'
    record=json.loads(path.read_text())
    plan=json.loads((harness.BASE/'plan.json').read_text())
    entry=plan['inputs'][index]
    for artifact in entry['artifacts']:
        assert 'sha256:'+harness.digest(artifact['path'])==artifact['sha256']
    documents=baseline.load_documents(dict(config=plan['config'],inputs=[entry]))
    model=plugin.build_model(documents,plan['config'],variant,index)
    selected=record['selected']
    result=check(model,selected['x']) if selected else dict(scientifically_qualified=False,reason='numerically_unqualified')
    result.update(index=index,variant=variant,stage=stage,numerically_qualified=selected is not None,
                  source_sha256={str(p):harness.digest(p) for p in (path,Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md')})
    folder=HERE/'information'/stage
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/f'{variant}_{index:02d}.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result))


if __name__=='__main__':
    main(sys.argv[1],sys.argv[2],int(sys.argv[3]))
