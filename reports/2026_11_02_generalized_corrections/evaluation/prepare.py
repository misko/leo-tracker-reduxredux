"""Freeze the complete available comparator roster with geography removed."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SOURCE = REPO/'reports/2026_11_02_family_reliability/population/protocol.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(destination):
    source = json.loads(SOURCE.read_text())
    rows = []
    for record in source['cases']:
        row = {k:record[k] for k in ('case','dataset','identities','origin_utc_ns','input_path','input_sha256','authority','selected')}
        row['baseline'] = {arm:{k:item[k] for k in ('objective','associated','selected','source','source_sha256')}
                           for arm,item in record['baseline'].items()}
        rows.append(row)
    plan = dict(cases=sorted(rows,key=lambda r:r['case']), available=len(rows),
                total_source_members=source['total_source_members'],
                unavailable_source_members=source['missing_source_members'],
                source_roster=str(SOURCE),source_roster_sha256=sha(SOURCE),
                per_cohort=source['per_cohort'],
                geography_removed=True, no_candidate_outcomes_read=True)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('Refusing to replace an existing RF roster')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(plan,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(destination),sha256=sha(destination),available=len(rows))))


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'rf_roster.json')
    prepare(ap.parse_args().output)
