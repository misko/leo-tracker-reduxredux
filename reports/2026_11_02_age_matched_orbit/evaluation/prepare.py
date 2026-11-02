"""RF-only immutable comparators and previous generic nominations; no refits."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PREVIOUS=ROOT.parent.parent/'2026_11_02_generalized_corrections'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def prepare(destination):
    old_path=PREVIOUS/'evaluation/combined_results.json';old=read(old_path)
    audit_path=PREVIOUS/'review/combined_audit.json';audit=read(audit_path)
    if audit['status']!='passed' or audit['results_sha256']!=sha(old_path):raise ValueError('Previous independent RF audit binding differs')
    old_roster_path=PREVIOUS/'evaluation/rf_roster.json';old_roster=read(old_roster_path)
    rows={r['case']:r for r in old['rows']}
    if len(rows)!=205 or set(rows)!={r['case'] for r in old_roster['cases']}:raise ValueError('Previous complete205 roster differs')
    records=[]
    for original in old_roster['cases']:
        row=rows[original['case']]
        if row['input_sha256']!=original['input_sha256']:raise ValueError('Previous input binding differs')
        target=row.get('target_family')
        if target is not None and (not row.get('eligible_families') or target!=row['eligible_families'][0]):
            raise ValueError('Previous target differs from first generic RF nomination')
        nomination={k:row[k] for k in ('family_ranking','eligible_families','target_family') if k in row}
        record=dict(original,previous_row_sha256=digest(row),previous_status=row['status'],
            previous_authority=old['provenance'][row['case']],target_family=target,
            saved_nomination_sha256=digest(nomination) if target is not None else None,
            saved_eligible_families=row.get('eligible_families',[]),
            selected_A=row['variants']['A']['selected_output'],selected_B=row['variants']['A+B']['selected_output'],
            old_A_accepted=row['variants']['A']['accepted'],old_B_accepted=row['variants']['A+B']['accepted'],
            previous_baseline_replay=row.get('baseline_replay'))
        records.append(record)
    output=dict(cases=sorted(records,key=lambda r:r['case']),available=205,
        total_source_members=old['total_source_members'],unavailable_source_members=old['unavailable_source_members'],
        previous_combined_path=str(old_path),previous_combined_sha256=sha(old_path),
        previous_audit_path=str(audit_path),previous_audit_sha256=sha(audit_path),
        previous_roster_path=str(old_roster_path),previous_roster_sha256=sha(old_roster_path),
        reusable_targets=sum(r['target_family'] is not None for r in records),
        target_cohort_counts=dict(Counter(r['dataset'] for r in records if r['target_family'] is not None)),
        geographic_truth_read=False,reranking_performed=False,position_fits_performed=False)
    destination=Path(destination)
    if destination.exists():raise FileExistsError('Refusing to replace RF comparator roster')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(destination),sha256=sha(destination),reusable_targets=output['reusable_targets'],target_cohorts=output['target_cohort_counts'])))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'rf_roster.json')
    prepare(ap.parse_args().output)
