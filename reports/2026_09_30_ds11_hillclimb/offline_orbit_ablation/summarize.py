import importlib.util
import json
from pathlib import Path
from fixed_model import read,digest
HERE=Path(__file__).resolve().parent


def main():
    sealed_path=HERE/'sealed.json';sealed=read(sealed_path)
    for p,h in sealed['sources'].items():assert digest(p)==h,p
    reference_path=HERE.parent.parent/'2026_09_30_ds11_single10/summarize.py'
    spec=importlib.util.spec_from_file_location('ablation_reference',reference_path);reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    sources={str(p):digest(p) for p in (Path(__file__),sealed_path,reference_path)};rows=[]
    for cell in sealed['rows']:
        row={k:cell[k] for k in ('index','states','labels')}
        if cell['selected'] is None:row['qualified']=False
        else:
            fit=read(cell['selected']['path']);row.update(qualified=fit['qualified'],distance_m=reference.distance(fit['coordinates_deg']),held_score=fit['held_score'],training_score=fit['score'],start=fit['start'],gradient_max=fit['gradient_max'],derivative_discrepancy=fit['derivative_audit']['discrepancy'])
        rows.append(row)
    result=dict(rows=rows,offline_diagnostic=True,causal_improvement_established=False,labels_authenticated=False,sources=sources)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
