"""Verify and summarize all nine discrepancy-port prerequisites."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def digest(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    output=HERE/'scan-discrepancy-port-summary-v1.json'
    if output.exists():raise FileExistsError(output)
    inputs={};rows=[]
    for ds in ('DS9','DS10','DS11'):
        for suffix in ('S1','D1','Q'):
            path=HERE/'scan-discrepancy-port-check-v1'/(ds+'-B01-'+suffix+'.json')
            assert digest(path)==path.with_suffix('.sha256').read_text().strip()
            result=json.loads(path.read_text());inputs[str(path)]=digest(path)
            for key in ('sources','inputs'):
                for p,h in result[key].items():assert digest(p)==h,p
            assert result['maximum_gradient_error']<.002
            rows.append({k:result[k] for k in ('unit','tracks','signal_tracks_at_zero','directions','maximum_gradient_error')})
    result=dict(rows=rows,inputs=inputs,source_sha256=digest(__file__),
        qualification='Nine prerequisite checks, not fitted estimates or geographic scores. Same numerical threshold for every window.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True)
    ax.bar([r['unit'] for r in rows],[r['maximum_gradient_error'] for r in rows])
    ax.axhline(.002,color='red',linestyle='--',label='Unchanged prerequisite threshold')
    ax.set_yscale('log');ax.set_ylabel('Maximum absolute directional gradient error')
    ax.tick_params(axis='x',rotation=40);ax.legend()
    ax.set_title('Nonzero scan offsets: full-objective checks at two step sizes')
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
