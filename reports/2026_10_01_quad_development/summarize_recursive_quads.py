"""Frozen quad comparisons with explicit pending and failed outcomes."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest
from finalize_panel import statistics
from summarize_full_pairs import compare
PILOT=('DS9-B01-Q','DS10-B01-Q','DS11-B01-Q')

HERE = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert Path(args.name).name==args.name
    output=HERE/(args.name+'.json');assert not output.exists() and not output.with_suffix('.png').exists()
    inputs={}
    def load(path):
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        inputs[str(path)]=digest(path);return json.loads(path.read_text())
    plan=load(HERE/'recursive-quad-queue-v1/plan.json')
    selection=load(HERE/'selection.json')
    assert digest(HERE/'selection.json')==plan['source_sha256'][str(HERE/'selection.json')]
    bindings={u['unit_id']:u for u in selection['evaluation_units'] if u['size']==4}
    assert list(bindings)==plan['units'] and len(bindings)==16
    entries=[]
    for unit,binding in bindings.items():
        baseline_dir=HERE/'independent-v2'/binding['block_id']
        baseline=next(r for r in load(baseline_dir/'evaluation.json')['rows'] if r['unit']==unit)
        reference=baseline;reference_dir=baseline_dir
        continued=HERE/'continuation-v1'/unit/'evaluation.json'
        if not baseline['accepted'] and continued.exists():
            reference=load(continued)['rows'][0];assert reference['unit']==unit
            reference_dir=continued.parent
        variant_dir=HERE/'recursive-quad-v1'/unit
        variant_path=variant_dir/'evaluation.json'
        variant=None;objective_changes={}
        if variant_path.exists():
            rows=load(variant_path)['rows'];assert len(rows)==1 and rows[0]['unit']==unit
            variant=rows[0];assert variant['scans']==binding['scans']
            if variant['accepted']:
                fitted=load(variant_dir/(unit+'.json'))
                assert digest(variant_dir/(unit+'.json'))==variant['receipt_sha256']
                for label,row,directory in [('baseline',baseline,baseline_dir),('recovered',reference,reference_dir)]:
                    if row['accepted']:
                        original=load(directory/(unit+'.json'))
                        assert digest(directory/(unit+'.json'))==row['receipt_sha256']
                        objective_changes[label]=fitted['best']['objectives'][-1]-original['best']['objectives'][-1]
        entries.append(dict(unit=unit,dataset=unit.split('-')[0],pilot=unit in PILOT,
            baseline=baseline,recovered=reference,variant=variant,objective_changes=objective_changes))
    groups={'all':entries,'outside_original_pilot':[e for e in entries if not e['pilot']]}
    groups.update({d:[e for e in entries if e['dataset']==d] for d in ['DS9','DS10','DS11']})
    summary={g:{r:compare(es,r) for r in ['baseline','recovered']} for g,es in groups.items()}
    for g,es in groups.items():
        summary[g]['failure_types']={kind:sum(e['variant'] is not None and not e['variant']['accepted'] and (e['variant'].get('fit_status')=='policy_failure')==is_policy for e in es)
            for kind,is_policy in [('constituent_admission_or_budget',True),('fit_or_audit',False)]}
    result=dict(summary=summary,rows=entries,input_sha256=inputs,summarizer_sha256=digest(__file__),
        qualification='Exposed development data. Pending excluded from audited statistics but counted explicitly. Failed outcomes remain in audited denominators. Error quantiles condition on acceptance. Improvements smaller than one metre treated as ties. Warm constituent work charged; not cold end-to-end timing.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
    for dataset,color in [('DS9','#3178a8'),('DS10','#da8b32'),('DS11','#5b9953')]:
        common=[e for e in entries if e['dataset']==dataset and e['variant'] is not None and e['variant']['accepted'] and e['recovered']['accepted']]
        for ax,field in zip(axes,['error_m','runtime_s']):
            ax.scatter([e['recovered'][field] for e in common],[e['variant'][field] for e in common],label=dataset,color=color)
    for ax,title in zip(axes,['Horizontal error (m)','Charged inference wall time (s)']):
        ax.set_xscale('log');ax.set_yscale('log')
        low=min(ax.get_xlim()[0],ax.get_ylim()[0]);high=max(ax.get_xlim()[1],ax.get_ylim()[1])
        ax.plot([low,high],[low,high],'k--',alpha=.5);ax.set_xlim(low,high);ax.set_ylim(low,high)
        ax.set_xlabel('Baseline with fixed continuation');ax.set_ylabel('Recursive pair starts');ax.set_title(title)
        ax.grid(alpha=.2);ax.legend()
    counts=summary['all']['recovered']
    fig.suptitle(f"{counts['audited']}/16 quads audited; plots show jointly accepted fits only\nBelow diagonal favors constituent starts; all failure counts retained in JSON")
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(summary['all'],indent=2),flush=True)


if __name__=='__main__':main()
