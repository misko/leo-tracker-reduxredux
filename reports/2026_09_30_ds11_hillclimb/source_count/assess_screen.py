"""Verify the complete frozen screen before reference-error assessment."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('count_screen_harness',HILL/'harness.py')
harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
def main():
    plan=read(HERE/'screen-plan.json')
    for path,h in plan['sources'].items():assert digest(path)==h,path
    attempts=[];sources=dict(plan['sources']);qualified_starts=0
    for index in plan['indices']:
        stem=HERE/'runs'/plan['stage']/f"{plan['variant']}_{index:02d}"
        receipt=read(stem.with_suffix('.receipt.json'))
        assert receipt['index']==index and receipt['family']=='source_count' and receipt['variant']==plan['variant']
        result=read(stem.with_suffix('.json')) if receipt['exit_code']==0 else None
        sources[str(stem.with_suffix('.receipt.json'))]=digest(stem.with_suffix('.receipt.json'))
        if result:
            sources[str(stem.with_suffix('.json'))]=digest(stem.with_suffix('.json'))
            assert result['index']==index and result['variant']==plan['variant'] and len(result['starts'])==4
            for path,h in result['sources'].items():assert digest(path)==h,path
            valid=[]
            for start in result['starts']:
                boundary=any(min(x-lo,hi-x)<.001 for x,(lo,hi) in zip(start['x'],result['bounds']))
                finite=all(math.isfinite(v) for v in start['x']+[start['score'],start['gradient'],start['audit']])
                good=start['success'] and finite and not boundary and start['gradient']<=.01 and start['audit']<=.02
                assert good==start['qualified'] and boundary==start['boundary'];qualified_starts+=good
                if good:valid.append(start)
            selected=result['selected']
            if valid:
                best=max(valid,key=lambda s:s['score']);assert all(selected[k]==v for k,v in best.items())
            else:assert selected is None
        attempts.append(dict(index=index,receipt=receipt,result=result))
    sealed=dict(attempts=attempts,plan_sha256=digest(HERE/'screen-plan.json'),reference_used=False)
    with (HERE/'screen-selections.json').open('x') as f:json.dump(sealed,f,indent=2)
    rows=[]
    for a in attempts:
        original=read(HILL.parent/f"2026_09_30_ds11_single10/runs/{a['index']:02d}_iid.json")['selected']
        selected=a['result']['selected'] if a['result'] else None
        rows.append(dict(index=a['index'],baseline_error_m=harness.distance(original['estimate_deg']),
                         challenger_error_m=harness.distance(selected['estimate_deg']) if selected else None,
                         common_iid_held_gain=selected['common_iid']['held']-selected['incumbent_common_iid']['held'] if selected else None))
    good=[r for r in rows if r['challenger_error_m'] is not None];old=[r['baseline_error_m'] for r in rows]
    errors=[r['challenger_error_m'] for r in good];complete=len(good)==8
    summary=dict(qualified_outputs=len(good),qualified_starts=qualified_starts,attempted_starts=sum(len(a['result']['starts']) for a in attempts if a['result']),
                 paired_wins=sum(r['challenger_error_m']<r['baseline_error_m'] for r in good),baseline_median_m=statistics.median(old),baseline_p90_m=harness.percentile(old,.9),
                 challenger_median_m=statistics.median(errors) if complete else None,challenger_p90_m=harness.percentile(errors,.9) if complete else None)
    summary['gate_pass']=complete and summary['paired_wins']>=5 and summary['challenger_median_m']<=.9*summary['baseline_median_m'] and summary['challenger_p90_m']<=summary['baseline_p90_m']
    sources.update({str(p):digest(p) for p in (Path(__file__),HERE/'screen-plan.json',HERE/'screen-selections.json')})
    result=dict(summary=summary,rows=rows,sources=sources,promotion=False,optimizer_replayed=False)
    with (HERE/'screen-outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(summary=summary,rows=rows),indent=2))
if __name__=='__main__':main()
