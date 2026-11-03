"""Geographic comparison of sealed offline and original endpoints."""
import importlib.util
import json
from pathlib import Path
from seal import digest
HERE=Path(__file__).resolve().parent


def main():
    sealed_path=HERE/'sealed.json';sealed=json.loads(sealed_path.read_text())
    for p,h in sealed['sources'].items():assert digest(p)==h,p
    reference_path=HERE.parent.parent/'2026_09_30_ds11_single10/summarize.py'
    spec=importlib.util.spec_from_file_location('offline_reference_metric',reference_path);reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    sources={str(p):digest(p) for p in (Path(__file__),sealed_path,reference_path)};rows=[]
    for index in sorted({r['index'] for r in sealed['rows']}):
        original_path=reference_path.parent/f'runs/{index:02d}_iid.json';sources[str(original_path)]=digest(original_path)
        row=dict(index=index,published_original_error_m=reference.distance(json.loads(original_path.read_text())['selected']['estimate_deg']))
        fits={}
        for arm in ('original','offline'):
            selected=next(r for r in sealed['rows'] if r['index']==index and r['arm']==arm)['selected']
            if selected is None:row[arm]=dict(qualified=False);continue
            fit=json.loads(Path(selected['path']).read_text());fits[arm]=fit
            row[arm]=dict(qualified=fit['qualified'],distance_m=reference.distance(fit['coordinates_deg']),held_score=fit['diagnostics']['held_score'],start=fit['start'],gradient_max=fit['gradient_max'],derivative_discrepancy=fit['derivative_audit']['discrepancy'],elapsed_s=fit['elapsed_s'])
        if len(fits)==2:
            before={r['track_id']:r for r in fits['original']['diagnostics']['identities']};after={r['track_id']:r for r in fits['offline']['diagnostics']['identities']};assert before.keys()==after.keys()
            row['identity_changes']=sum(before[t]['norad']!=after[t]['norad'] for t in before)
            row['initially_high_confidence_identity_changes']=sum(before[t]['confidence']>=.99 and before[t]['norad']!=after[t]['norad'] for t in before)
            row['error_change_m']=row['offline']['distance_m']-row['original']['distance_m']
            row['held_score_change']=row['offline']['held_score']-row['original']['held_score']
        rows.append(row)
    result=dict(rows=rows,offline_only=True,causal_improvement_established=False,reference_limitation='unsurveyed installation coordinate',sources=sources)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
