"""Freeze the comparable recent fast cohorts and rank unique scan outcomes."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
REPO=OUT.parents[1]
READINESS=REPO/'reports/2026_11_01_promotion_readiness'
DATA=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports')
ROOTS={'DS24':DATA/'2026_11_01_ds25_fast_causal_variants',
       'DS26':DATA/'2026_11_01_ds26_ds27_causal_variants',
       'DS27':DATA/'2026_11_01_ds26_ds27_causal_variants',
       'DS28':DATA/'2026_11_01_ds28_revision2_evaluation',
       'FRSH':READINESS/'fresh'}


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    paths=[READINESS/'population_positions.csv',READINESS/'ds24/positions.csv',READINESS/'fresh_positions.csv']
    rows=[]
    for index,path in enumerate(paths):
        for row in csv.DictReader(path.open()):
            if row['arm']!='fitted_c' or index==0 and row['method']!='guarded_candidate':continue
            case=row['case'];dataset=case[:4];source=ROOTS[dataset]/'inputs'/(case+'.json')
            z=read(source);inventory=read(z['inventory_path'])
            identity=tuple(sorted(inventory['job']['identities']))
            error=float(row['error_m'] if index==0 else row['candidate_error_m'] if index==1 else row['candidate_m'])
            rows.append(dict(case=case,dataset=dataset,identities=identity,error_m=error,
                origin_utc_ns=z['scan_receipt']['origin_utc_ns'],input_path=str(source),input_sha256=sha(source),
                authority='retrospective_guarded_policy_audit' if index==0 else 'frozen_guarded_runner_execution',
                selected=row.get('selected') or None))
    identities=[tuple(r['identities']) for r in rows]
    if len(identities)!=len(set(identities)):raise ValueError('Repeated acquisition in comparable cohorts')
    rows.sort(key=lambda r:(-r['error_m'],r['case']))
    for rank,row in enumerate(rows,1):row['initial_rank']=rank
    manifest=dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        model='algo07-causal-guarded-reassociation-v1',source_sha256={str(p):sha(p) for p in [Path(__file__),*paths]},
        scope='Recent comparable DS24/26/27/28 fast cohorts plus five fresh fast validation recordings; DS25 is adaptive only and not counted again',
        available=205,total_members=229,missing=24,deduplicated_by='native recording identity tuple',
        per_cohort={'DS24':{'available':25,'members':34},'DS26':{'available':148,'members':159},
                    'DS27':{'available':13,'members':15},'DS28':{'available':14,'members':16},'FRSH':{'available':5,'members':5}},
        evaluation_site=[37.849061591561885,-122.48574968092912],
        truth_usage='Ranks outlier evaluation errors and reports postfit accuracy only; not identity selection, fitted priors or optimization starts',
        initial_top10=[r['case'] for r in rows[:10]],
        ranking_controls=['DS26-0034','DS26-0251'],
        controls_reason='Fresh execution must confirm retrospective repairs did not hide an outlier; DS26-0066 already has exact promoted-code replay',
        source_scope='Saved composed ALGO06 graph/GLRT outcomes; this is not a raw-IQ rerun or historical public production terminal claim',
        rows=rows)
    if len(rows)!=manifest['available']:raise ValueError('Unexpected cohort availability')
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    with (OUT/'initial_ranking.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=['initial_rank','case','dataset','error_m','origin_utc_ns','authority','selected'])
        writer.writeheader();writer.writerows({k:r[k] for k in writer.fieldnames} for r in rows)
    print(json.dumps({'available':len(rows),'top10':manifest['initial_top10'],'duplicates':0}))


if __name__=='__main__':main()
