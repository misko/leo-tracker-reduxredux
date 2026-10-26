"""Prior evaluator arithmetic/fallback, extended to six completed final slots."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geometry_cache as gc

HERE=Path(__file__).resolve().parent
PRIOR=Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01/position')
spec=importlib.util.spec_from_file_location('original_geographic_evaluator',PRIOR/'evaluate.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
read=original.read


def evaluate_rows(rfrows,reference,original_arms):
    return [original.evaluated_row(row,reference,original_arms[row['arm']]['endpoint_east_north_km']) for row in rfrows]


def freeze():
    files={str(path):gc.sha(path) for path in [Path(__file__),HERE/'test_evaluate_cached.py',PRIOR/'evaluate.py']}
    with (HERE/'evaluation_freeze.json').open('x') as stream:json.dump(dict(files=files,geographic_data_read=False),stream,indent=2);stream.write('\n')


def run(reference):
    for path in [HERE/'evaluation_freeze.json',HERE/'RF_seal.json',HERE/'report/readback_seal.json']:
        for name,digest in read(path)['files'].items():
            if gc.sha(name)!=digest:raise ValueError('bound file changed:'+name)
    audit=read(HERE.parent/'audit/position_terminal.json')
    if (audit.get('all_passed') is not True or audit.get('RF_ready_for_separate_geographic_evaluation') is not True
        or audit['RF_seal_sha256']!=gc.sha(HERE/'RF_seal.json') or audit['protocol_sha256']!=gc.sha(HERE/'protocol.json')):
        raise ValueError('exact passing RF audit required')
    with (HERE/'report/outcomes.csv').open() as stream:rfrows=list(csv.DictReader(stream))
    rows=evaluate_rows(rfrows,reference,read(original.SOURCE)['policy_arms'])
    if len(rows)!=6 or sum(row['final_endpoint_available'] for row in rows)!=6:
        raise ValueError('frozen completed-six-slot denominator changed')
    out=HERE/'geographic';out.mkdir(exist_ok=False)
    with (out/'outcomes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (out/'summary.json').open('x') as stream:
        json.dump(dict(reference_latlon=reference,rows=rows,completed_final_endpoints=6,partial_epochs_scored=False,
            arithmetic='exact original evaluate.py latlon/haversine/evaluated_row; only final-slot count extended from4to6',
            operational_policy='exact_original_reference'),stream,indent=2);stream.write('\n')
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        group=[row for row in rows if row['arm']==arm]
        for index,(row,color) in enumerate(zip(group,('#333333','#b34c32','#00796b'),strict=True)):
            error=row['raw_position_error_km'];ax.bar(index,error,color=color,width=.55)
            ax.text(index,error,f'{error:.3f}',ha='center',va='bottom',fontsize=9)
        ax.axhline(group[0]['original_reference_error_km'],ls='--',color='#65758b',label='Unchanged operational policy')
        ax.set_xticks(range(3),['No addition','Hard 58175','Full mixture']);ax.set_xlim(-.6,2.6)
        ax.set_ylim(0,max(row['raw_position_error_km'] for row in group)*1.18)
        ax.set_ylabel('Position error (km)');ax.set_title('c=0' if arm=='c0' else 'fitted c')
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('DS24-0011: all six final endpoints, original source qualification retained\nRaw diagnostics are unqualified; operational fallback remains the original reference.',fontsize=10)
    fig.savefig(out/'paired_position_errors.png',dpi=180);plt.close(fig)
    files={str(path):gc.sha(path) for path in out.iterdir() if path.is_file()}
    for path in [Path(__file__),HERE/'evaluation_freeze.json',HERE/'RF_seal.json',HERE/'report/readback_seal.json',HERE.parent/'audit/position_terminal.json',original.SOURCE]:files[str(path)]=gc.sha(path)
    with (out/'seal.json').open('x') as stream:json.dump(dict(files=files,new_fits=0),stream,indent=2);stream.write('\n')
    print(json.dumps(rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);parser.add_argument('--reference-latlon',nargs=2,type=float)
    args=parser.parse_args()
    if args.action=='freeze':freeze()
    elif args.reference_latlon is None:parser.error('explicit released evaluation reference required')
    else:run(args.reference_latlon)
