"""One separately released geographic evaluation of immutable completed endpoints."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
OUT=HERE/'geographic'
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024/family_cavity/position/DS24-0011.json')
read=lambda path:json.loads(Path(path).read_bytes())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def latlon(point):
    return 37.906+point[1]/111., -122.545+point[0]/(111.32*math.cos(math.radians(37.906)))


def distance(a,b):
    la,lo,lb,lp=map(math.radians,(*a,*b))
    h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def evaluated_row(row,reference,original):
    baseline=distance(latlon(original),reference)
    complete=row['raw_endpoint_available']=='True'
    error=distance(latlon([float(row['east_km']),float(row['north_km'])]),reference) if complete else None
    return dict(arm=row['arm'],method=row['method'],status=row['status'],final_endpoint_available=complete,
        raw_position_error_km=error,original_reference_error_km=baseline,
        raw_error_minus_reference_m=1000*(error-baseline) if error is not None else None,
        operational_policy_error_km=baseline,operational_policy='exact_original_reference',
        parent_frequency_RMS_hz=float(row['parent_frequency_RMS_hz']) if row['parent_frequency_RMS_hz'] else None,
        target_profile_RMS_hz=float(row['original_target_profile_RMS_hz']) if row['original_target_profile_RMS_hz'] else None,
        target_conditional_RMS_hz=float(row['original_target_conditional_RMS_hz']) if row['original_target_conditional_RMS_hz'] else None,
        target_association_qualified=False,original_accepted_IDs_lost=int(row['original_accepted_IDs_lost']) if row['original_accepted_IDs_lost'] else None,
        point_numerically_stable=row['point_numerically_stable']=='True',partial_epoch_substituted=False)


def freeze():
    files={str(path):sha(path) for path in (Path(__file__),HERE/'test_evaluate.py')}
    with (HERE/'evaluation_freeze.json').open('x') as stream:json.dump(dict(files=files,geographic_data_read=False),stream,indent=2);stream.write('\n')


def run(reference):
    for seal in [HERE/'evaluation_freeze.json',HERE/'RF_seal.json',HERE/'rf_report/seal.json']:
        for name,digest in read(seal)['files'].items():
            if sha(name)!=digest:raise ValueError('bound file changed: '+name)
    audit=read(HERE.parent/'audit/position_terminal.json')
    if (audit.get('all_passed') is not True or audit.get('RF_ready_for_separate_geographic_evaluation') is not True
        or audit.get('RF_seal_sha256')!=sha(HERE/'RF_seal.json') or audit.get('protocol_sha256')!=sha(HERE/'protocol.json')):
        raise ValueError('exact passing RF audit required')
    OUT.mkdir(exist_ok=False)
    saved=read(SOURCE)['policy_arms']
    with (HERE/'rf_report/outcomes.csv').open() as stream:
        rows=[evaluated_row(row,reference,saved[row['arm']]['endpoint_east_north_km']) for row in csv.DictReader(stream)]
    if len(rows)!=6 or sum(row['final_endpoint_available'] for row in rows)!=4:
        raise ValueError('frozen four-final/six-slot denominator changed')
    if any(row['method']=='mixture' and row['final_endpoint_available'] for row in rows):
        raise ValueError('partial mixture must never become final geographic result')
    with (OUT/'outcomes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (OUT/'summary.json').open('x') as stream:
        json.dump(dict(reference_latlon=reference,root_release='explicit coordinator message after passing RF terminal audit',
            rows=rows,declared_slots=6,completed_final_endpoints=4,mixture_final_endpoints=0,new_fits=0),stream,indent=2);stream.write('\n')
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        group=[row for row in rows if row['arm']==arm]
        for x,row in enumerate(group):
            if row['final_endpoint_available']:
                ax.bar(x,row['raw_position_error_km'],width=.55,color='#333333' if row['method']=='no_addition' else '#b34c32')
                ax.text(x,row['raw_position_error_km'],f"{row['raw_position_error_km']:.3f}",ha='center',va='bottom',fontsize=9)
            else:
                ax.text(x,.1,'No final\nendpoint',ha='center',va='bottom',fontsize=9)
        baseline=group[0]['original_reference_error_km']
        ax.axhline(baseline,color='#00796b',ls='--',label='Unchanged operational policy')
        ax.set_xticks(range(3),['No addition','Hard 58175','Mixture'])
        ax.set_ylim(0,max(row['raw_position_error_km'] or 0 for row in group)*1.18)
        ax.set_ylabel('Position error (km)');ax.set_title('c=0' if arm=='c0' else 'fitted c')
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('DS24-0011: completed raw diagnostics and exact reference fallback\nBoth added-source methods remain unqualified; no mixture epoch0 error is substituted.',fontsize=10)
    fig.savefig(OUT/'paired_position_errors.png',dpi=180);plt.close(fig)
    files={str(path):sha(path) for path in OUT.iterdir() if path.is_file()}
    for path in [Path(__file__),HERE/'evaluation_freeze.json',HERE/'RF_seal.json',HERE/'rf_report/seal.json',HERE.parent/'audit/position_terminal.json',SOURCE]:files[str(path)]=sha(path)
    with (OUT/'seal.json').open('x') as stream:json.dump(dict(files=files,scientific_model_changed=False),stream,indent=2);stream.write('\n')
    print(json.dumps(rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run'])
    parser.add_argument('--reference-latlon',nargs=2,type=float)
    args=parser.parse_args()
    if args.action=='freeze':freeze()
    elif args.reference_latlon is None:parser.error('explicit released evaluation reference required')
    else:run(args.reference_latlon)
