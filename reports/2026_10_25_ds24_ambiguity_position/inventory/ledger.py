"""Metadata pool and ownership replay; no nomination, position fit or geography."""
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
STUDY=HERE.parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
COHORT=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
OLD=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/information')
ARMS=('c0','fitted_c')
OLD_FOUR=tuple(f'DS24-{i:04d}' for i in range(10,14))
RECEIPTS=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')

def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n')

def cases():
    rows=[q for q in read(COHORT)['rows'] if q['eligible']]
    assert len(rows)==24
    return sorted(rows,key=lambda q:(q['captured_utc_ns'],q['case']))

def exposure():
    out={};bindings={}
    p=OLD/'inventory.json';bindings[str(p)]=sha(p)
    for row in read(p)['sources']:
        if row['eligible']:
            out.setdefault((row['case'],row['component']),[]).append(dict(kind='prior complete-owner local-information experiment',artifact=str(p)))
    for case in ('DS24-0087','DS24-0095'):
        p=RECOVERY/case/'inventory.json';bindings[str(p)]=sha(p)
        for row in read(p)['candidate_targets']:
            out.setdefault((case,row['component']),[]).append(dict(kind='prior whole-source graph/support recovery experiment',artifact=str(p)))
    return out,bindings

def make_rows(case,tracks,parent,coverage,known):
    selected=parent['selected'] if parent['accepted'] else None
    node=selected['node'] if selected else parent['baseline_node']
    entries=selected['entries'] if selected else parent['baseline_entries']
    canonical={};cursor=0
    mask=parent['original_mask']
    for k,(row,alias) in enumerate(zip(node['seed']['rows'],node['aliases'],strict=True)):
        n=row['points'];active=mask[cursor:cursor+n];cursor+=n
        assert len(active)==n and row['component'] not in canonical
        canonical[row['component']]=(k,row,alias,active)
    assert cursor==len(mask)
    likelihood={a:set(coverage[a]['curved_observation_ids']+coverage[a]['predictive_observation_ids']) for a in ARMS} if coverage else None
    accepted={a:set(coverage[a]['accepted_observation_ids']) for a in ARMS} if coverage else None
    families={a:set(coverage[a]['active_curved_families'])|{e['candidate_index'] for e in entries} for a in ARMS} if coverage else None
    if families:assert families['c0']==families['fitted_c']
    rows=[];allids=[]
    for i,t in enumerate(tracks):
        ids=t['observation_ids'];assert len(ids)==len(t['times'])==len(set(ids));allids+=ids
        z=canonical.get(t['key']);reasons=[]
        if z:
            k,row,alias,active=z
            assert row['points']==len(ids)
            if not row['active_curvature']:reasons.append('canonical row lacks original active curvature')
            if any(active):reasons.append('contains original curved likelihood IDs')
        else:
            k,row,alias,active=None,{},None,[]
            reasons.append('no archived original curved canonical nominee/alias')
        if coverage is None:reasons.append('complete accepted-ID ownership not reconstructed')
        overlap={a:sorted(set(ids)&accepted[a]) for a in ARMS} if coverage else None
        if overlap and any(overlap.values()):reasons.append('overlaps original accepted union, including postfit-only IDs')
        history=known.get((case,t['key']),[])
        r=dict(case=case,component=t['key'],track_index=i,row_index=k,
            receiver=t['receiver'],channel=t['channel'],rf_hz=t['rf_hz'],points=len(ids),
            start_s=min(t['times']),end_s=max(t['times']),span_s=max(t['times'])-min(t['times']),
            observation_ids=ids,canonical_candidate_index=row.get('candidate_index'),
            candidate_index=row.get('candidate_index'),candidate_norad=row.get('candidate_norad'),alias=alias,
            archived_original_active_curvature=row.get('active_curvature',False),
            archived_nomination_compatible=row.get('compatible'),
            archived_feasible_candidates=row.get('feasible_candidates'),
            quality_status=t.get('quality_status'),quality_flags=t.get('diagnostic',{}).get('quality_flags'),
            family_has_parent_likelihood=(row.get('candidate_index') in families['c0']) if families else None,
            accepted_ID_overlap=overlap,
            likelihood_ID_overlap={a:sorted(set(ids)&likelihood[a]) for a in ARMS} if coverage else None,
            postfit_only_ID_overlap={a:sorted(set(ids)&set(coverage[a]['postfit_only_observation_ids'])) for a in ARMS} if coverage else None,
            prior_source_specific_work=history,unexhausted_within_declared_audit=not history,
            case_excluded_from_new_choice=case in OLD_FOUR,
            eligible=not reasons,exclusion_reasons=reasons,identity_qualified=False)
        rows.append(r)
    assert len(allids)==len(set(allids))
    return rows

def metadata():
    began=time.monotonic();known,bindings=exposure();rows=[];members=[]
    bindings[str(COHORT)]=sha(COHORT)
    for q in cases():
        case=q['case'];tp=SOURCE/case/'tracks.json';pp=SOURCE/'family_cavity/position'/f'{case}.json'
        bindings.update({str(tp):sha(tp),str(pp):sha(pp)})
        parent=read(pp);assert parent['status']=='complete'
        coverage=None;receipt=RECEIPTS/case/'parent.json'
        if receipt.exists():
            p=read(receipt)
            assert p['source_parent_sha256']==sha(pp) and p['source_tracks_sha256']==sha(tp)
            assert p['source_observations_sha256']==sha(SOURCE/case/'observations.json')
            coverage=p['coverage'];bindings[str(receipt)]=sha(receipt)
        elif case in ('DS24-0087','DS24-0095'):
            receipt=RECOVERY/case/'parent.json';p=read(receipt)
            # This older receipt lacks independent input hashes. Do not reuse it
            # as authoritative without a fresh exact-context ownership replay.
            bindings[str(receipt)]=sha(receipt)
        rows.extend(make_rows(case,read(tp),parent,coverage,known))
        members.append(dict(case=case,captured_utc_ns=q['captured_utc_ns'],recording_id=q['recording_id'],
            session_id=q['session_id'],sample_rate_hz=q['sample_rate_hz'],mode=q['mode'],
            original_cohort_exposure=q['exposure'],ownership_status='reused_bound_receipt' if coverage else 'requires_fixed_endpoint_replay',
            ownership_receipt=str(receipt) if coverage else None,
            tracks_sha256=sha(tp),parent_sha256=sha(pp)))
    write(HERE/'metadata.json',dict(cases=members,sources=rows,bindings=bindings,seconds=time.monotonic()-began,
        scope='all24 exposed DS24 development scans; complete native owners, including all exclusions; no CFO/position-error fields used',
        source_exposure_scope='exact previous information/inventory and original recovery candidate_targets ledgers; original graph/cavity nomination and other corpus-wide baseline analysis already exposed every case; absence of this small-ledger match does not prove no prior inspection',
        owner_pool='whole original curved graph owners, unchanged canonical candidate/alias; both-arm full accepted-ID union exclusion',
        provisional_until_full_ownership=True,no_new_nominations=True,no_position_fits=True,no_GPS_or_errors=True))
    print(json.dumps(dict(cases=len(members),native_owners=len(rows),requires_replay=sum(q['ownership_status'].startswith('requires') for q in members),seconds=time.monotonic()-began)))

if __name__=='__main__':metadata()
