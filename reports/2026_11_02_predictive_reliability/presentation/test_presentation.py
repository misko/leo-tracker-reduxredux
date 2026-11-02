"""Check that published figure inputs preserve sealed evidence and missingness."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def test_presented_joint_gains_and_qualification_match_sealed_decisions():
    d=json.loads((ROOT.parent/'decisions.json').read_text())
    index={(case,r['split'],r['arm']):r for case,v in d['cases'].items()for r in v['comparisons']}
    for r in csv.DictReader((ROOT/'predictive_scores.csv').open()):
        key=(r['case'],r['split'],r['arm'])
        if key in index:
            assert abs(float(r['all_gain_SD4'])-index[key]['gain_SD4'])<1e-9
            assert (r['paired_four_fit_qualified']=='True')==index[key]['paired_qualified']


def test_unsupported_and_absent_marginal_scores_are_empty_not_zero():
    for r in csv.DictReader((ROOT/'predictive_scores.csv').open()):
        if r['supported']=='False':
            assert all(r[k+'_gain_SD4']==''for k in ['all','target','other'])
        if r['kind']=='family_receiver':assert r['other_gain_SD4']==''


def test_manifest_inputs_match_unchanged_rf_seals():
    m=json.loads((ROOT/'manifest.json').read_text())
    assert not m['geography_read']and not m['inference_run']
    for path,digest in m['inputs_sha256'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
