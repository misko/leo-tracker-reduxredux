"""Strict-issuance and independent-group audit; no RF/GPS or model fitting."""
from collections import Counter
import copy
import json
from pathlib import Path
import numpy as np
from age_covariance import POLICY,base,select_pairs,sha

ROOT=Path(__file__).resolve().parent
SEED=20261102


def main():
    roster_path=ROOT.parent/'evaluation/rf_roster.json';roster=json.loads(roster_path.read_text())
    families={int(r['target_family']) for r in roster['cases'] if r.get('target_family') is not None}
    parents={n:n for n in families};snapshot_owner={};forecasts=[];skipped=Counter()
    def find(n):
        while parents[n]!=n:parents[n]=parents[parents[n]];n=parents[n]
        return n
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parents[max(a,b)]=min(a,b)
    for record in roster['cases']:
        family=record.get('target_family')
        if family is None:continue
        z=json.loads(Path(record['input_path']).read_text());native=Path(z['native_path'])
        raw=json.loads((native.parent/'causal_phase_history'/(native.name+'.json')).read_text())
        nominal=json.loads((native/'nominal_elements.json').read_text())[str(family)]
        obs=json.loads((native/'observations.json').read_text());times=[v['time_s'] for v in obs]
        current_h=(z['scan_receipt']['origin_utc_ns']+round((min(times)+max(times))/2*1e9)-base.tle_epoch(nominal['lines']))/3.6e12
        cutoff=z['scan_receipt']['cutoff_utc_ns'];oldest=cutoff-int(72*3.6e12)
        # Validate full provenance first; all pairing below is metadata-only.
        select_pairs(raw,nominal,cutoff,z['scan_receipt']['origin_utc_ns'],family,current_h)
        versions=[r for r in raw['past_versions'][str(family)] if oldest<=r['epoch']<=base.tle_epoch(nominal['lines'])
                  and oldest<=r['collected_utc_ns']<=cutoff]
        for r in versions:
            digest=r['snapshot_sha256']
            if digest in snapshot_owner:union(family,snapshot_owner[digest])
            else:snapshot_owner[digest]=family
        tolerance=max(2.,.25*current_h)
        for older in versions:
            issue=older['collected_utc_ns']
            if older['epoch']>issue:skipped['older_epoch_after_issuance']+=1;continue
            prefix_versions=[r for r in raw['past_versions'][str(family)] if r['collected_utc_ns']<=issue and r['epoch']<=issue]
            if older['epoch']!=max(r['epoch'] for r in prefix_versions):skipped['older_not_latest_at_issuance']+=1;continue
            for newer in versions:
                h=(newer['epoch']-older['epoch'])/3.6e12
                if h<=0 or abs(h-current_h)>tolerance:continue
                if issue>newer['epoch'] or newer['collected_utc_ns']<=issue:
                    skipped['held_revision_not_future_of_issuance']+=1;continue
                prefix=copy.deepcopy(raw);prefix['cutoff_utc_ns']=prefix['origin_utc_ns']=issue
                prefix['past_versions']={str(family):prefix_versions}
                prefix['sources']=[s for s in raw['sources'] if s['collected_utc_ns']<=issue]
                old_nominal=dict(lines=older['lines'],provenance=dict(collected_utc_ns=issue,
                    element_epoch_utc_ns=older['epoch'],snapshot_digest='sha256:'+older['snapshot_sha256']))
                pairs,info=select_pairs(prefix,old_nominal,issue,issue,family,h)
                old_history,old_info=base.validate_and_select(prefix,old_nominal,issue,issue,family)
                forecasts.append(dict(case=record['case'],family=family,issuance_utc_ns=issue,
                    older_epoch_utc_ns=older['epoch'],target_epoch_utc_ns=newer['epoch'],
                    held_newer_collected_utc_ns=newer['collected_utc_ns'],horizon_hours=h,
                    older_element_sha256=base.element_sha(older['lines']),held_newer_element_sha256=base.element_sha(newer['lines']),
                    strict_prefix_age_pair_count=len(pairs),strict_prefix_oldB_history_count=len(old_history),
                    age2_and_oldB_prefix_supported=len(pairs)>=2 and len(old_history)>=3,
                    age3_and_oldB_prefix_supported=len(pairs)>=3 and len(old_history)>=3,
                    preprocessing_cutoff='older element first collection/forecast issuance; held newer never included'))
    components={}
    for family in sorted(families):components.setdefault(find(family),[]).append(family)
    keys=sorted(components);rng=np.random.default_rng(SEED);shuffled=list(np.asarray(keys)[rng.permutation(len(keys))])
    held=set(shuffled[:max(1,round(.2*len(shuffled)))])
    groups=[dict(group_id=int(key),families=members,partition='held' if key in held else 'training') for key,members in components.items()]
    paired=[r for r in forecasts if r['age2_and_oldB_prefix_supported']]
    independent=len(components)>=5 and len({find(r['family']) for r in paired})>=2
    packet=dict(seed=SEED,roster_sha256=sha(roster_path),source_sha256=sha(Path(__file__)),
        target_families=len(families),shared_snapshot_connected_groups=len(components),groups=groups,
        split='Randomized whole connected groups of satellite families sharing any causal snapshot/element; same family always together',
        issuance_policy='Older first collection; all preprocessing epochs and collection receipts at or before issuance; later newer revision used only as held outcome',
        forecasts=forecasts,forecast_count=len(forecasts),paired_age2_oldB_prefix_supported=len(paired),
        paired_age3_oldB_prefix_supported=sum(r['age3_and_oldB_prefix_supported'] for r in forecasts),
        skipped=dict(skipped),status='requires_numerical_validation' if independent else 'unsupported_independent_validation',
        numerical_revision_density_comparison_performed=False,
        reason='Too few independent shared-snapshot groups and/or strictly issued forecasts with both priors supported',
        prefix_archive_coverage='Only already exported pre-RF72-hour banks; earlier pre-issuance archive receipts outside these banks are unavailable here',
        RF_or_GPS_or_position_fit_used=False)
    (ROOT/'archive_validation_support.json').write_text(json.dumps(packet,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in packet.items() if k not in ['forecasts','groups']},indent=2))


if __name__=='__main__':main()
