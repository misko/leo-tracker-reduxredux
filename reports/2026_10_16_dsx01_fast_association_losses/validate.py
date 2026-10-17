"""Validate DSX01 frozen membership independently of scientific fit outcomes."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def check_membership(dataset,context,members):
    observations={(p['source_id'],p['observation_id']):p for p in context}
    assert len(observations)==len(context),'Duplicate source observation'
    assert len({r['region_id'] for r in dataset['regions']})==len(dataset['regions'])
    actual=[(m['region_id'],m['source_id'],m['observation_id']) for m in members]
    assert len(set(actual))==len(actual),'Duplicate membership'
    expected=[]
    for region in dataset['regions']:
        matching=[p for p in context if p['source_id']==region['source_id'] and
            p['receiver']==region['receiver'] and p['channel']==region['channel'] and
            region['start_s']<=p['time_s']<=region['end_s']]
        assert len(matching)==region['observation_count'] and matching
        associated=sum(p['original_associated'] for p in matching)
        assert associated==region['original_associated_count']
        assert len(matching)-associated==region['original_unassociated_count']
        expected.extend((region['region_id'],p['source_id'],p['observation_id']) for p in matching)
    assert set(actual)==set(expected),'Membership differs from exact requested bounds'
    assert len(members)==dataset['membership_count']
    assert len({(m['source_id'],m['observation_id']) for m in members})==dataset['unique_member_observation_count']
    assert len(context)==dataset['full_scan_context_observation_count']
    return Counter(p['source_id'] for p in context)


def main():
    dataset=json.loads((ROOT/'dataset.json').read_text());sources=json.loads((ROOT/'sources.json').read_text())
    for name,digest in dataset['membership_sha256'].items():
        assert 'sha256:'+hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    context=[json.loads(line) for line in (ROOT/'context-observations.jsonl').read_text().splitlines()]
    with (ROOT/'membership.csv').open(newline='') as stream:members=list(csv.DictReader(stream))
    counts=check_membership(dataset,context,members)
    assert dataset['recording_count']==len(sources)==len(counts)==5
    assert dataset['region_count']==len(dataset['regions'])==15
    for source in sources:
        assert counts[source['source_id']]==source['observation_count']
        assert source['tle_collected_utc_ns']<source['first_sample_estimate_utc_ns']
    negative=[]
    for label,changed in [('dropped member',members[1:]),('duplicated member',members+members[:1]),
        ('changed source',[dict(members[0],source_id='nonexistent')]+members[1:])]:
        try:check_membership(dataset,context,changed)
        except AssertionError:negative.append(label)
        else:raise AssertionError('Failed to reject '+label)
    findings=json.loads((ROOT/'findings.json').read_text())
    assert {f['region_id'] for f in findings['regions']}=={r['region_id'] for r in dataset['regions']}
    for finding in findings['regions']:assert not finding['independent_identity_truth'] and not finding['independent_position_truth']
    for receipt in findings['evidence_snapshots']:
        assert 'sha256:'+hashlib.sha256((ROOT/receipt['snapshot_path']).read_bytes()).hexdigest()==receipt['sha256']
    controls=json.loads((ROOT/'auxiliary-controls.json').read_text())
    assert len(controls)==7 and len({c['control_id'] for c in controls})==7
    for control in controls:
        assert 'sha256:'+hashlib.sha256((ROOT/control['snapshot_evidence_path']).read_bytes()).hexdigest()==control['evidence_sha256']
    result=dict(dataset_id='DSX01',version=1,regions=15,recordings=5,members=len(members),
        context_observations=len(context),membership_hashes_verified=True,
        exhaustive_receiver_channel_time_selection_verified=True,causal_snapshots_verified=True,
        mutation_rejections=negative,primary_original_associated=sum(r['original_associated_count'] for r in dataset['regions']),
        primary_original_unassociated=sum(r['original_unassociated_count'] for r in dataset['regions']),auxiliary_controls=7)
    (ROOT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
