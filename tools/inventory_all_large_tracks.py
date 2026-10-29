"""Canonical DS24 and current-day graph inventory, including recovered evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
import hashlib
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from debug_fast_graph_unassociated import read,write
from inventory_joint_attachment_validation import identity
from inventory_cohort_unassociated import remaining_track
from stress_joint_attachment import supervise
from validate_fast_target_guard import target_guard

ARMS=('c0','fitted_c')


def select_guard(folder):
    path=folder/'result.json'
    if not path.exists():path=folder/'fallback.json'
    source=read(path)
    u=read(folder/'unconstrained.json') if source['status']=='accepted' else None
    return source['policy'] if target_guard(source,u) else source['support'],source['baseline']


def frozen_policy(job):
    kind=job['policy_kind']
    if kind=='baseline':return None,None
    path=Path(job['policy_path'])
    if kind=='guard':return select_guard(path)
    if kind=='attachment':
        r=read(path/'result.json')
        prior=select_guard(Path(job['prior_guard_path']))[1] if job.get('prior_guard_path') else r['baseline']
        return r['variants'].get('covariance_physical',{}).get('policy',r['baseline']),prior
    return None,None


def freeze(args):
    from leo.storage.fast_graph_position import FastGraphPositionStore
    out=args.output;out.mkdir(parents=True,exist_ok=True);study=args.study
    if (out/'protocol.json').exists():raise ValueError('inventory protocol already frozen')
    manifest=read(args.manifest);sample_root=Path('/srv/bulk/leo/research/ds25-20261024')
    aliases={r['recording_id']:r['dataset_label'] for r in read(sample_root/'sample.json')['selected']}
    entries=[];missing=[]
    def add(root,case,label,scope,priority,policy_kind='baseline',policy_path=None,recording=None):
        root=Path(root)
        if not (root/case/'tracks.json').exists() or not (root/'family_cavity/position'/f'{case}.json').exists():
            missing.append(dict(label=label,recording=recording,root=str(root),case=case,
                                reason='missing graph or qualified family baseline',scope=scope));return
        saved=read(root/'family_cavity/position'/f'{case}.json')
        if saved['status']!='complete':
            missing.append(dict(label=label,recording=recording,root=str(root),case=case,reason=saved['status'],scope=scope));return
        document=read(root/case/'tracking.json');source=document.get('source',document)
        entries.append(dict(root=str(root),case=case,label=label,recording=recording or source['session_id'],
            identities=sorted(identity(source)),raw_authority=source.get('raw_recording_authority_digest'),
            sample_rate_hz=source['sample_rate_hz'],scope=scope,priority=priority,
            policy_kind=policy_kind,policy_path=str(policy_path) if policy_path else None,
            tracks_sha256=hashlib.sha256((root/case/'tracks.json').read_bytes()).hexdigest()))
    for member in manifest['members']:
        case=aliases.get(member['recording_id'],member['dataset_label'])
        guard=study/'combined-reentry'/case
        add(sample_root,case,member['dataset_label'],'DS24',100 if (guard/'result.json').exists() else 20,
            'guard' if (guard/'result.json').exists() else 'baseline',guard,member['recording_id'])
    sep=read(study/'separate-fast-validation/protocol.json')
    for case in sep['cases']:
        add(sep['root'],case,case,'session research',100,'guard',study/'separate-fast-validation/recovery'/case)
    add(args.pilot/'run/inference','SCAN','PILOT','session research',120,'attachment',study/'joint-attachment-pilot',
        'fast8-auto-20261029-013224-11b2bf44-1-upper')
    entries[-1]['prior_guard_path']=str(args.pilot/'recovery-accounting-current')
    for n,j in enumerate(read(study/'promotion-panel-v1/protocol.json')['jobs'],1):
        folder=study/'promotion-panel-v1'/j['job_id']
        terminal=read(folder/'terminal.json');a=folder/'attachment'
        attachment=terminal['status']=='complete' and (a/'result.json').exists()
        add(j['root'],'SCAN',f'V{n:02}','session research',110,'attachment' if attachment else 'guard',
            a if attachment else folder/'reentry',j['report_scalar_metadata']['recording_name'])
        if attachment:entries[-1]['prior_guard_path']=str(folder/'reentry')
    # Existing public snapshot contains all completed products discovered in the
    # preceding turn. Recheck public statuses and include those analyzed today.
    public=read(study/'promotion-inventory-v1/inventory.json')
    cutoff=int(datetime.fromisoformat(args.day).replace(tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()*1e9)
    store=FastGraphPositionStore('/srv/bulk/leo')
    public_receipts=[]
    for item in public['rows']:
        status=store.status(item['job_id'])
        if not status or status['state']!='complete':continue
        report=store.inputs_port.detail(status['run_id'],include_points=False)
        is_member=any(m['recording_id']==report.get('recording_name') or m['session_id']==report.get('session_id') for m in manifest['members'])
        if status['updated_utc_ns']<cutoff and not is_member:continue
        terminal,artifact=store.terminal(status)
        root=Path(artifact['path']).parent/'inference'
        add(root,'SCAN','AUTO-'+item['job_id'][:8],'automatic analysis today' if status['updated_utc_ns']>=cutoff else 'DS24 public fallback',10,
            recording=report.get('recording_name',terminal['session_id']))
        public_receipts.append(dict(job_id=item['job_id'],updated_utc_ns=status['updated_utc_ns'],artifact=artifact))
    groups=[]
    for entry in entries:
        hits=[g for g in groups if set(entry['identities']) & set().union(*(set(v['identities']) for v in g))]
        if hits:
            combined=[entry]+[v for g in hits for v in g];groups=[g for g in groups if g not in hits];groups.append(combined)
        else:groups.append([entry])
    jobs=[]
    for group in groups:
        ordered=sorted(group,key=lambda r:(-r['priority'],r['label']))
        best=dict(ordered[0]);best['aliases']=sorted({r['label'] for r in group})
        best['scopes']=sorted({r['scope'] for r in group});best['versions']=ordered
        for member in manifest['members']:
            if member['recording_id']==best['recording'] or set(member.get('session_ids',[member['session_id']]))&set(best['identities']):
                best['aliases']=sorted(set(best['aliases'])|{member['dataset_label']})
                best['scopes']=sorted(set(best['scopes'])|{'DS24'})
        best['job_id']=hashlib.sha256('\n'.join(best['identities']).encode()).hexdigest()[:16]
        jobs.append(best)
    jobs.sort(key=lambda r:r['label'])
    resolved={alias for job in jobs for alias in job['aliases']}
    missing=[m for m in missing if m['label'] not in resolved]
    write(out/'protocol.json',dict(jobs=jobs,unavailable=missing,manifest_path=str(args.manifest),
          manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),day=args.day,
          day_timezone='America/Los_Angeles',day_start_utc_ns=cutoff,public_receipts=public_receipts,
          public_snapshot='preceding promotion inventory; newly completed statuses refreshed',
          large='at least 20 unassociated original GLRT IDs spanning at least 20s; gap retained explicitly',
          no_GPS_selection=True,no_future_TLE=True,workers=8,case_seconds=90))
    print('Canonical jobs',len(jobs),'unavailable DS24 slots',len(missing),flush=True)


def one(args):
    job=read(args.job);root=Path(job['root']);out=args.output;out.mkdir(parents=True,exist_ok=True)
    if (out/'inventory.json').exists():return
    current,original=frozen_policy(job)
    if current is None:
        from benchmark_graph_covariance import load_case,baseline_pair
        d=load_case(root,job['case']);current=original=baseline_pair(d)
    tracks=read(root/job['case']/'tracks.json');observations=read(root/job['case']/'observations.json')
    all_ids={o['observation_id'] for o in observations};graph_ids={o for t in tracks for o in t['observation_ids']}
    rows=[];summary=[]
    for arm in ARMS:
        owned=set(current[arm]['proposed_associated_ids']);old=set(original[arm]['proposed_associated_ids'])
        if not owned<=all_ids:raise ValueError('unknown accepted observation IDs')
        local=[]
        for i,t in enumerate(tracks):
            now=remaining_track(t,owned);before=remaining_track(t,old)
            if now is None and before is None:continue
            ids=sorted(set(t['observation_ids'])-owned)
            track_id=hashlib.sha256(('\n'.join(job['identities'])+'\n'+'\n'.join(sorted(t['observation_ids']))).encode()).hexdigest()[:20]
            row=dict(track_id=track_id,job_id=job['job_id'],label=job['label'],aliases=job['aliases'],arm=arm,
                     component=t['key'],track_index=i,observation_ids=ids,all_track_observation_ids=t['observation_ids'],
                     current=now,earlier=before,earlier_large=bool(before and before['big']),
                     current_large=bool(now and now['big']),recovered_points=len((set(t['observation_ids'])-old)&owned))
            local.append(row)
        large_ids={o for r in local if r['current_large'] for o in r['observation_ids']}
        summary.append(dict(job_id=job['job_id'],label=job['label'],aliases=job['aliases'],scopes=job['scopes'],arm=arm,
               total_GLRT=len(all_ids),associated=len(owned),unassociated=len(all_ids-owned),graph_tracks=len(tracks),
               large_tracks=sum(r['current_large'] for r in local),large_track_unique_points=len(large_ids),
               unassociated_outside_graph=len(all_ids-owned-graph_ids),
               recovered_previously_large=sum(r['earlier_large'] and not r['current_large'] for r in local)))
        rows+=local
    write(out/'inventory.json',dict(job=job,summary=summary,tracks=rows,policy=current,prior_policy=original))
    print(job['label'],[(s['arm'],s['large_tracks']) for s in summary],flush=True)


def run(args):
    protocol=read(args.output/'protocol.json');jobs=protocol['jobs'];receipts=[]
    attempt=args.output/('attempt-'+str(len(list(args.output.glob('attempt-*')))+1))
    attempt.mkdir()
    def work(job):
        if (args.output/job['job_id']/'inventory.json').exists():
            return dict(job_id=job['job_id'],label=job['label'],status='already_complete')
        jp=attempt/(job['job_id']+'-job.json');write(jp,job)
        cmd=[sys.executable,__file__,'one','--job',str(jp),'--output',str(args.output/job['job_id'])]
        r=dict(job_id=job['job_id'],label=job['label'],**supervise(cmd,attempt/(job['job_id']+'.log'),90))
        write(attempt/(job['job_id']+'-terminal.json'),r);return r
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();receipts.append(r);print(r,flush=True)
    write(attempt/'execution.json',receipts)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('freeze','run','one'))
    for name in ('study','pilot','manifest','output','job'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--day',default='2026-10-29');a=p.parse_args()
    {'freeze':freeze,'run':run,'one':one}[a.mode](a)
