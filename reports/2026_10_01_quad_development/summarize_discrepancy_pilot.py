"""All eighteen predeclared outcomes with process gates and offset diagnostics."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest,sealed
from summarize_cold_seed_limits import arm_row

HERE=Path(__file__).resolve().parent


def main():
    output=HERE/'scan-discrepancy-pilot-summary-v1.json'
    if output.exists():raise FileExistsError(output)
    inputs={};frozen={};rows=[]
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    for ds in ('DS9','DS10','DS11'):
        for suffix in ('S1','D1','Q'):
            unit=f'{ds}-B01-{suffix}';arms={};states={}
            for arm in ('baseline','sigma1'):
                directory=HERE/'scan-discrepancy-pilot-v1'/unit/arm
                outcome=read(directory/'outcome.json');freeze=read(directory/'sources.json')
                for key in ('source_sha256','inputs'):
                    for p,h in freeze[key].items():
                        if p in frozen:assert frozen[p]==h
                        frozen[p]=h
                launch=read(directory/(unit+'.launch.json'));audit=read(directory/'audit-launch.json')
                assert launch==outcome['launch'] and audit==outcome['audit_launch']
                assert launch['freeze_sha256']==digest(directory/'sources.json')
                if (directory/'evaluation.json').exists():assert read(directory/'evaluation.json')==outcome['evaluation']
                r=arm_row(unit,arm,outcome);r['arm']=r.pop('seed_limit')
                r.update(incremental_seconds=launch['incremental_seconds'],original_seconds=launch['original_seconds'])
                assert abs(r['wall_seconds']-r['incremental_seconds']-r['original_seconds'])<1e-8
                path=directory/(unit+'.json')
                if path.exists():
                    receipt=read(path);parent=read(Path(freeze['parent_receipt']))
                    assert digest(path)==launch['receipt_sha256']
                    meta=receipt['discrepancy_pilot'];base=meta['base_dimension'];size=parent['binding']['size']
                    assert meta['parent_sha256']==digest(freeze['parent_receipt'])
                    expected=parent['best']['mean']+([0.]*(2*size) if arm=='sigma1' else [])
                    assert meta['initial_state']==freeze['initial_state']==expected
                    assert receipt['observations']==parent['observations']
                    state=np.asarray(receipt['best']['mean']);states[arm]=state[:2]
                    offsets=state[base:].reshape(size,2) if arm=='sigma1' else np.zeros((size,2))
                    r.update(iterations=receipt['best']['iterations'],reason=receipt['best']['reason'],
                        offsets_m=(1000*offsets).tolist(),offset_sum_m=(1000*offsets.sum(axis=0)).tolist(),
                        maximum_offset_m=float(1000*np.linalg.norm(offsets,axis=1).max()),
                        apparent_positions_km=(state[:2]+offsets).tolist(),
                        changed_labels_from_parent=sum(a!=b for a,b in zip(receipt['best']['associations'],parent['best']['associations'])))
                arms[arm]=r
            comparison=dict(unit=unit,size={'S1':1,'D1':2,'Q':4}[suffix],arms=arms)
            if all(r['accepted'] for r in arms.values()):
                comparison.update(error_change_m=arms['sigma1']['error_m']-arms['baseline']['error_m'],
                    shared_position_change_m=float(1000*np.linalg.norm(states['sigma1']-states['baseline'])))
            rows.append(comparison)
    for p,h in frozen.items():assert digest(p)==h,p
    sources={str(p):digest(p) for p in (Path(__file__).resolve(),HERE/'summarize_cold_seed_limits.py')}
    result=dict(rows=rows,inputs=inputs,frozen_sources_and_inputs=frozen,sources=sources,
        qualification='Warm fixed1km sensitivity with same original parent state/evidence and charged work. All eighteen outcomes retained; errors only after process and numerical acceptance. Overlapping previously exposed development windows, not independent validation.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
    for ax,ds in zip(axes,('DS9','DS10','DS11')):
        selected=[r for r in rows if r['unit'].startswith(ds+'-')]
        for arm,label in (('baseline','Warm baseline'),('sigma1','1 km discrepancy')):
            ax.plot(range(3),[r['arms'][arm]['error_m'] if r['arms'][arm]['accepted'] else np.nan for r in selected],'-o',label=label)
        ax.set_xticks(range(3),['Single','Pair','Quad']);ax.set_title(ds);ax.set_ylabel('Accepted reference error (m)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Fixed scan-discrepancy pilot; missing points are rejected outcomes')
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
