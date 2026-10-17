"""Mint DSX01 from inspected windows and verified, existing tracking exports.

Read-only with respect to recordings, the catalogue and production. Dataset
membership is all winning observations in each requested window, never a fitted
candidate's inliers. Candidate hypotheses live in a separate findings snapshot.
"""
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank

SOURCES=[
    ('S01','three-track-20261016','fast8-auto-20261016-161535-99008d35-1-lower','fast-9571943d3dccdf4f327e1346d1bf34b8','dd9c84a33648a347de303cb8345336df'),
    ('S02','upper-210123-three-segments-20261016','fast8-auto-20261016-210123-05c5faad-1-upper','fast-ef14c5e000dab296a85ac4438599a381','bb0433f92daacec744fd80a26a863fb3'),
    ('S03','lower-213139-three-segments-20261016','fast8-auto-20261016-213139-8bb8d5d7-1-lower','fast-6f970ee9ef48a64e2a6a53b9f1d46efb','06d8ec407aa078c45d50dc2df82044c5'),
    ('S04','upper-three-segments-20261016','fast8-auto-20261016-220156-22c968b0-1-upper','fast-7fcf05755907f691219f727f0348a01b','73c4b28b4f002e0d2154bab2f67457b6'),
    ('S05','new-three-segments-20261016','fast8-auto-20261016-223211-029a4eef-1-lower','fast-d626811aa789be76a985a4e33bd1e6f4','075b34f9532dd9f7caf6c70830e4e8e8'),
]

# receiver labels are one-based, as in the UI. Inclusive bounds, seconds from
# each source's own recorded first-sample estimate.
REGIONS=[
    ('S01',1,4,40.,100.,[69333],'timing_optimizer_trap','Strong track-informed recovery; generic reverse cold-start still fails.'),
    ('S01',1,2,50.,75.,[69433],'timing_optimizer_trap','Strong conditional candidate; generic recovery is not established.'),
    ('S01',1,2,170.,190.,[69522],'band_timing_conflict','Lower/upper support conflict; empirical correction transfers conditionally, physical cause unresolved.'),
    ('S02',1,1,65.,100.,[68711,49155,67700],'preliminary_ambiguity','Low full-track fit requires a large timing; half-track identities differ.'),
    ('S02',1,3,95.,127.,[63567,67889],'preliminary_ambiguity','Full-track and half-track candidates disagree; no automatic recovery established.'),
    ('S02',2,2,150.,200.,[63434,63567],'preliminary_fragmentation','Overlapping 55/65-point proposals disagree in extent; large timing and poor temporal transfer.'),
    ('S03',1,4,0.,40.,[66544],'timing_and_detectability','Timing-only 119 Hz; target-informed timing/q diagnostic assigns 34/35 selected track points.'),
    ('S03',1,4,175.,210.,[60127],'timing_and_detectability','Timing-only 139 Hz; target-informed timing/q diagnostic assigns 39/42 selected track points.'),
    ('S03',1,5,175.,200.,[67704],'timing_and_detectability','Timing-only 150 Hz; target-informed timing/q diagnostic assigns 28/30 selected track points.'),
    ('S04',2,5,75.,110.,[62502,66580],'timing_optimizer_trap_with_ambiguity','Retiming 62502 alone assigns 20/46 points and improves full objective; temporal transfer remains imperfect.'),
    ('S04',2,3,110.,140.,[61912,57985,52577,53390],'geometry_identity_ambiguity','Good all-data fits compete with large timings; reverse identity changes.'),
    ('S04',1,3,125.,175.,[48117,59540],'geometry_identity_ambiguity','Geometry-sensitive curve; forward conditional fit can transfer, reverse still weak.'),
    ('S05',1,3,40.,60.,[66854],'timing_optimizer_trap','Retained candidate at +5.16 s; timing-only fit prefers -1.50 s, 237 Hz.'),
    ('S05',1,4,250.,280.,[57864],'candidate_retention','Appeared in discovery but absent from final bank; conditional timing-only fit 152 Hz.'),
    ('S05',1,2,110.,140.,[58362],'timing_optimizer_trap','Retained candidate at +4.14 s; timing-only fit prefers -1.25 s, 210 Hz.'),
]


def digest(data):return 'sha256:'+hashlib.sha256(data).hexdigest()


def save(path,document):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(document,indent=2,allow_nan=False)+'\n')


def csv_file(path,fields,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def original_context(document,terminal,stages):
    source=load_input(document);prepared,nodes=prepare_views(source);obs=prepared['all'].observations
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=next(s for s in archive.list_snapshots() if s.digest==terminal['provenance']['tle_sha256']
        and s.collected_utc_ns==terminal['provenance']['tle_collected_utc_ns'])
    catalogue=parse_element_sets(archive.read(snap));lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    numbers=terminal['candidate_numbers'];prior=RegionalPrior(**terminal['provenance']['prior'])
    bank,_=build_regional_bank(catalogue,[lookup[n] for n in numbers],prepared['all'].start_utc_ns,obs,prior)
    bank=bank.select([list(bank.numbers).index(n) for n in numbers])
    model,fit,audit=selected_model(prepared,bank,prior,nodes,terminal,stages)
    terms=model.evaluate_joint(np.array(fit['vector']),np.array(fit['nuisance']))[3]
    best=terms.responsibilities.argmax(axis=1)
    associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    arrays=dict(times=obs.times_s,measured=obs.measured_hz,rf=obs.rf_hz,receiver=obs.receiver,channel=obs.channel,
        associated=associated,best_number=np.array(numbers)[best],
        satellite_posterior=terms.responsibilities[np.arange(len(best)),best],clutter_posterior=terms.clutter_probability)
    context=dict(window_ids=list(obs.window_ids),source_origin_ns=source.timing.first_sample_estimate_utc_ns)
    return arrays,context,audit


def main():
    if (ROOT/'dataset.json').exists():raise FileExistsError('DSX01 v1 membership already minted; do not overwrite it')
    store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2')
    data={};sources=[];evidence_files=[];context_records=[]
    for key,folder,recording,run_id,job_id in SOURCES:
        job,document,terminal,stages=store.plot_evidence(job_id)
        assert job['run_id']==run_id
        if key=='S01':arrays,ctx,audit=original_context(document,terminal,stages)
        else:
            directory=REPO/'reports'/folder
            baseline=json.loads((directory/'baseline.json').read_text())
            assert baseline['input_sha256']==job['input_sha256'] and baseline['terminal_sha256']==job['terminal']['sha256']
            arrays=dict(np.load(directory/'baseline.npz'));ctx=json.loads((directory/'context.json').read_text());audit=baseline['audit']
        assert len(ctx['window_ids'])==len(arrays['times'])
        assert len(set(ctx['window_ids']))==len(ctx['window_ids'])
        data[key]=(arrays,ctx)
        origin=ctx['source_origin_ns']
        source=dict(source_id=key,recording_id=recording,analysis_run_id=run_id,job_id=job_id,
            tracking_input_path=job['input_path'],tracking_input_sha256=job['input_sha256'],
            terminal_sha256=job['terminal']['sha256'],baseline_model_version=job['model_version'],
            tle_sha256=terminal['provenance']['tle_sha256'],tle_collected_utc_ns=terminal['provenance']['tle_collected_utc_ns'],
            first_sample_estimate_utc_ns=origin,first_sample_estimate_utc=datetime.fromtimestamp(origin/1e9,timezone.utc).isoformat(),
            observation_count=len(arrays['times']),original_associated_count=int(np.sum(arrays['associated'])),
            original_position=terminal['position'],baseline_audit=audit,
            ui_url=f'http://gauss:8090/?scan_id={recording}&scan_kind=fast',report_directory=f'reports/{folder}')
        sources.append(source)
        for i,window_id in enumerate(ctx['window_ids']):
            context_records.append(dict(source_id=key,observation_id=window_id,time_s=float(arrays['times'][i]),
                receiver=int(arrays['receiver'][i])+1,channel=int(arrays['channel'][i]),
                actual_rf_hz=float(arrays['rf'][i]),measured_cfo_hz=float(arrays['measured'][i]),
                original_associated=bool(arrays['associated'][i]),
                original_best_satellite=int(arrays['best_number'][i]),
                original_satellite_posterior=float(arrays['satellite_posterior'][i]),
                original_clutter_posterior=float(arrays['clutter_posterior'][i])))
        save(ROOT/'evidence'/f'{key}-terminal.json',terminal)
        if key!='S01':
            for name in ['baseline.json','shape-controls.json','timing-trials.json','search-results.json','retime-control.json','geometry-control.json','validation.json']:
                path=REPO/'reports'/folder/name
                if path.exists():
                    target=ROOT/'evidence'/f'{key}-{name}';target.write_bytes(path.read_bytes())
                    evidence_files.append(dict(original_path=str(path.relative_to(REPO)),snapshot_path=str(target.relative_to(ROOT)),sha256=digest(target.read_bytes())))
        print(json.dumps(dict(source=key,observations=source['observation_count'],associated=source['original_associated_count'])),flush=True)
    regions=[];members=[];findings=[];region_csv=[]
    for i,(key,rx,ch,left,right,hypotheses,category,note) in enumerate(REGIONS,1):
        region_id=f'DSX01-{i:03d}';a,ctx=data[key]
        rows=np.flatnonzero((a['receiver']==rx-1)&(a['channel']==ch)&(a['times']>=left)&(a['times']<=right))
        assert len(rows)>0
        assoc=int(np.sum(a['associated'][rows]));record=dict(region_id=region_id,source_id=key,receiver=rx,channel=ch,
            start_s=left,end_s=right,bounds='inclusive',observation_count=len(rows),
            original_associated_count=assoc,original_unassociated_count=len(rows)-assoc)
        regions.append(record);region_csv.append(dict(record,recording_id=next(s['recording_id'] for s in sources if s['source_id']==key)))
        for row in rows:members.append(dict(region_id=region_id,source_id=key,observation_id=ctx['window_ids'][row]))
        findings.append(dict(region_id=region_id,hypothesis_satellites=hypotheses,diagnostic_category=category,
            assessment=note,independent_identity_truth=False,independent_position_truth=False))
    aux=[]
    frame=REPO/'reports/three-track-frame-clock-20261016/carrier_identity_checks.json'
    for i,g in enumerate(json.loads(frame.read_text())['groups'],1):
        aux.append(dict(control_id=f'DSX01-C{i:02d}',source_id='S01',receiver=1,
            channel=int(g['group'][2]),kind='frame_carrier_diagnostic',name=g['group'],
            start_s=min(g['times_s']),end_s=max(g['times_s']),times_s=g['times_s'],count=g['count'],
            evidence_path=str(frame.relative_to(REPO)),qualification='Model-selected channel groups; not independent identity labels or additional primary failures.'))
    extension_path=REPO/'reports/three-track-20261016/evidence/late_track_extension.json'
    extension=json.loads(extension_path.read_text());a,ctx=data['S01'];ix=np.array(extension['selected_rows'])
    aux.append(dict(control_id='DSX01-C05',source_id='S01',receiver=1,channel=2,kind='continuity_extension',
        start_s=float(a['times'][ix].min()),end_s=float(a['times'][ix].max()),count=len(ix),
        observation_ids=[ctx['window_ids'][row] for row in ix],evidence_path=str(extension_path.relative_to(REPO)),
        qualification='38-point extension includes original DSX01-003 anchors; overlaps primary membership.'))
    transfer_path=REPO/'reports/three-track-20261016/evidence/rx2_timing_transfer.json'
    transfer=json.loads(transfer_path.read_text())
    aux.append(dict(control_id='DSX01-C06',source_id='S01',receiver=2,channel=2,kind='guided_raw_iq_counterparts',
        count=transfer['count'],evidence_path=str(transfer_path.relative_to(REPO)),
        qualification='20 guided detections; not necessarily present in the original winning-observation export. Do not add them to baseline denominators.'))
    directory=REPO/'reports/lower-213139-three-segments-20261016';base=json.loads((directory/'baseline.json').read_text())
    part=base['groups'][0]['continuity_segments'][1];a,ctx=data['S03']
    aux.append(dict(control_id='DSX01-C07',source_id='S03',receiver=1,channel=4,kind='already_associated_positive_control',
        start_s=part['time_limits_s'][0],end_s=part['time_limits_s'][1],count=part['count'],
        observation_ids=[ctx['window_ids'][row] for row in part['rows']],
        evidence_path='reports/lower-213139-three-segments-20261016/baseline.json',
        qualification='Secondary 12-point trajectory inside DSX01-007; all originally associated. Do not double-count.'))
    auxiliary_snapshots={}
    for control in aux:
        original=control['evidence_path']
        if original not in auxiliary_snapshots:
            source=REPO/original;target=ROOT/'evidence'/f'control-{control["control_id"]}-{source.name}'
            target.write_bytes(source.read_bytes());auxiliary_snapshots[original]=str(target.relative_to(ROOT))
        control['snapshot_evidence_path']=auxiliary_snapshots[original]
        control['evidence_sha256']=digest((ROOT/control['snapshot_evidence_path']).read_bytes())
    save(ROOT/'sources.json',sources);save(ROOT/'findings.json',dict(kind='diagnostic-hypotheses-not-labels',regions=findings,evidence_snapshots=evidence_files))
    save(ROOT/'auxiliary-controls.json',aux)
    with (ROOT/'context-observations.jsonl').open('w') as stream:
        for record in context_records:stream.write(json.dumps(record,separators=(',',':'),allow_nan=False)+'\n')
    csv_file(ROOT/'membership.csv',['region_id','source_id','observation_id'],members)
    csv_file(ROOT/'regions.csv',list(region_csv[0]),region_csv)
    hashes={name:digest((ROOT/name).read_bytes()) for name in ['sources.json','context-observations.jsonl','membership.csv','regions.csv']}
    dataset=dict(schema_version=1,dataset_id='DSX01',version=1,kind='retrospective-fast-association-loss-challenge',
        created_utc=datetime.now(timezone.utc).isoformat(),recording_count=len(sources),region_count=len(regions),
        membership_count=len(members),unique_member_observation_count=len({(m['source_id'],m['observation_id']) for m in members}),
        full_scan_context_observation_count=len(context_records),regions=regions,membership_sha256=hashes,
        denominator_policy='Every original winning observation in each requested RX/channel/time window. Missing estimates remain failures; no fitted-inlier filtering.',
        truth_policy='No independent satellite or geographic labels. Findings are hypotheses; original assignments are model outputs, not truth.',
        exposure='All primary windows were inspected before minting. This is a development challenge, not an untouched validation set.',
        split_policy='Recording-grouped retrospective folds only; no overlapping window/track/counterpart leakage between training and test.',
        context_policy='Whole-scan context permits training and regression checks outside the inspected windows. Raw inputs and IQ remain referenced in place.',
        auxiliary_controls_file='auxiliary-controls.json')
    save(ROOT/'dataset.json',dataset)
    print(json.dumps({k:dataset[k] for k in ['dataset_id','region_count','recording_count','membership_count','unique_member_observation_count','full_scan_context_observation_count']}),flush=True)


if __name__=='__main__':main()
