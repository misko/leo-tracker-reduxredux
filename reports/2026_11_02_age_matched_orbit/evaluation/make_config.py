"""Generate the pre-outcome bounded execution configuration from orbit support."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPORT=ROOT.parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configure(output):
    roster=ROOT/'rf_roster.json';inventory=REPORT/'covariance/derived_inventory.json'
    support=json.loads(inventory.read_text());covariance=REPORT/'covariance/age_covariance.py'
    if support['roster_sha256']!=sha(roster) or support['covariance_source_sha256']!=sha(covariance):
        raise ValueError('Orbit inventory must bind the final RF roster and covariance source')
    ready=sorted(r['case'] for r in support['rows'] if r['status']=='ready' and r.get('pair_count',0)>=2)
    value=dict(roster_path=str(roster),roster_sha256=sha(roster),support_inventory_path=str(inventory),
        support_inventory_sha256=sha(inventory),candidate_cases=ready,covariance_module='covariance/age_covariance.py',
        age_policy_minimum_pairs=dict(Age3=3,Age2=2),workers=8,total_seconds=1200,cell_seconds=120,preparation_seconds=60,
        solver=dict(max_rounds=15,maxiter=35,maxfun=140,rescue_maxfun=140,max_actual_calls=800))
    output=Path(output)
    if output.exists():raise FileExistsError('Refusing to replace existing candidate configuration')
    output.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),sha256=sha(output),candidate_cases=len(ready))))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'proposed_configuration.json')
    configure(ap.parse_args().output)
