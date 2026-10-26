"""Small independent numeric and saved-artifact checks; no scientific reruns."""
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import subprocess
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (ROOT/'audit'/name).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n')


def bindings(files):
    bad = [path for path,digest in files.items() if sha(path) != digest]
    assert not bad, bad
    return len(files)


def csv_rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def circular(value, period):
    return (np.asarray(value)+period/2)%period-period/2


def phase_oracle(start, origin, local, fs):
    """Integer counter reduction followed by the local fractional epoch."""
    from fractions import Fraction
    period = Fraction(int(fs),750)
    integer = Fraction(int(start)-int(origin)) % period
    return float((integer+Fraction(float(local))) % period)


def grid_readback():
    began = time.monotonic(); here = ROOT/'grid'
    summary = read(here/'summary.json')
    checked = bindings(summary['source_bindings'])
    checked += bindings(read(here/'seal.json')['files'])
    rows = csv_rows(here/'all_pairs.csv')
    assert len(rows) == summary['pairs'] == 501
    assert len({r['observation_id'] for r in rows}) == summary['unique_winning_windows'] == 483
    step = (1/4.4e-6)/512
    assert abs(step-summary['step_hz']) < 1e-10
    gaps = np.array([float(r['circular_CFO_delta_hz']) for r in rows])
    multiple = np.rint(gaps/step).astype(int)
    multiple[multiple==0] = np.sign(gaps[multiple==0]).astype(int)
    residual = gaps-multiple*step
    np.testing.assert_array_equal(multiple,[int(r['nearest_nonzero_bin_multiple']) for r in rows])
    np.testing.assert_allclose(residual,[float(r['bin_residual_hz']) for r in rows],rtol=0,atol=1e-10)
    counts = {str(t):int(np.sum(abs(residual)<=t)) for t in (1,5,25)}
    assert counts == summary['within_hz_counts'] == {'1':0,'5':6,'25':30}
    for percentile,value in summary['absolute_bin_residual_percentiles_hz'].items():
        assert abs(np.percentile(abs(residual),float(percentile))-value) < 1e-10
    save('grid_readback.json',dict(all_passed=True,summary_sha256=sha(here/'summary.json'),
        frozen_bindings_checked=checked,pairs=501,unique_winning_windows=483,
        within_bin_residual_Hz=counts,absolute_gap_min_median_max_Hz=np.percentile(abs(gaps),[0,50,100]).tolist(),
        audit_seconds=time.monotonic()-began,detector_calls=0,graph_calls=0,
        scope='Descriptive bin/gap alignment; not independent sources, physical ambiguity prevalence or a selection rule.'))


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def recorded_preflight():
    began=time.monotonic(); here=ROOT/'recorded'
    protocol=read(here/'protocol.json');checked=bindings(protocol['bindings'])
    assert protocol['original_winners']==3754 and protocol['original_owners']==117
    assert protocol['path_outcomes_not_viewed'] and not protocol['acquired_CFO_available']
    assert protocol['cap_worker_seconds']==180 and protocol['numerical_workers']==protocol['BLAS_threads']==1
    assert protocol['prior_metadata_read_charge_seconds']==2
    smoke=read(here/'smoke.json');assert smoke['metadata_only'] and smoke['no_path_outcomes']
    assert smoke['original_winner_count']==3754 and smoke['original_owner_count']==117
    module=load_module('audited_recorded_continuity',here/'continuity.py')
    errors=[]
    for origin in (1613490476683,10**17+123):
        for delta in (0,13333,40000,10_000_003,3_000_000_001):
            for local in (-.25,127.25,13333.75):
                expected=phase_oracle(origin+delta,origin,local,10_000_000)
                actual=module.global_phase(origin+delta,origin,local,10_000_000)
                errors.append(abs(actual-expected));assert abs(actual-expected)<1e-8
    first=smoke['first_window']
    assert first['observation_id'] and first['window_id']!=first['observation_id']
    assert first['window_start_counter']==first['origin_counter']
    assert all(row['observation_id']==first['observation_id'] and row['acquired_cfo_hz'] is None
        for row in smoke['all_exported_candidates'])
    for row in smoke['all_exported_candidates']:
        expected=phase_oracle(row['window_start_counter'],row['origin_counter'],row['local_epoch_samples'],10_000_000)
        assert abs(expected-row['global_epoch_samples'])<1e-8
    test=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',str(here/'test_continuity.py')],
        text=True,capture_output=True,timeout=30,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(protocol['bindings'])==checked
    save('recorded_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),
        frozen_bindings_checked=checked,rational_counter_phase_tests=len(errors),
        maximum_phase_oracle_error_samples=max(errors),historical_native_IDs_distinct_from_research_window_IDs=True,
        fixed_engineering_thresholds_reviewed=True,test_stdout=test.stdout,test_stderr=test.stderr,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_graph_calls=0,
        scope='Frozen RF persistence inventory; no new physical observations or independently identified sources.'))


def prototype_preflight():
    began=time.monotonic();here=ROOT/'prototype'
    protocol=read(here/'protocol.json');checked=bindings(protocol['files'])
    assert protocol['lane_method_slots']==24 and protocol['receiver_lanes']==8 and protocol['episodes']==4
    assert protocol['methods']==['original_winners','cfo_only','epoch_cfo']
    assert protocol['numerical_budget_seconds']==300 and protocol['workers']==protocol['blas_threads']==1
    assert not protocol['true_labels_for_selection'] and not protocol['operational_acceptance']
    assert protocol['new_detector_calls']==0
    module=load_module('audited_prototype_continuity',here/'continuity.py')
    assert module.SETTINGS==protocol['settings'] and module.SETTINGS['maximum_paths']==2
    prep=read(here/'preparation.json');port=read(here/'prepared/synthetic_rows.json')
    assert prep['all_passed'] and prep['old_winner_graph_parity'] and prep['tests_run']==10
    assert prep['windows']==128 and prep['source_raw_candidates']==1024 and prep['gated_dedup_candidates']==386
    assert not prep['truth_fields_used_by_adapter'] and prep['new_detector_calls']==0
    assert len(port['episodes'])==4 and port['sample_rate_hz']==10_000_000
    window_count=candidate_count=0;phase_errors=[]
    old=ROOT.parent/'ds24-measurement-continuity-r01/measurement'
    for episode in port['episodes']:
        assert len(episode['windows'])==32 and len(episode['raw_ledger'])==32
        expected_rows=read(old/'graphs'/(episode['name']+'.json'))['actual']['rows']
        expected={row['observation_id']:row for row in expected_rows}
        assert len(expected)==32
        for receiver in ('0','1'):
            module.validate([w for w in episode['windows'] if w['receiver_id']==receiver],port['sample_rate_hz'])
        for w in episode['windows']:
            window_count+=1;candidate_count+=len(w['candidates'])
            assert w['observation_id'] in expected
            assert w['time_s']==w['window_start_counter']/port['sample_rate_hz']+.01
            assert len(w['candidates'])==len({c['candidate_id'] for c in w['candidates']})
            selected=max(w['candidates'],key=lambda c:(c['margin'],-c['candidate_rank']))
            assert selected['cfo_hz']==expected[w['observation_id']]['measured_cfo_hz']
            for row in w['candidates']:
                err=abs(float(circular(row['global_epoch_samples']-phase_oracle(w['window_start_counter'],w['origin_counter'],
                    row['local_epoch_samples'],port['sample_rate_hz']),port['sample_rate_hz']/750)))
                phase_errors.append(err);assert err<1e-8
                assert row['margin']>=.025
                assert not any(key in row for key in ('truth','source','source_label','norad','position'))
    assert window_count==128 and candidate_count==386
    test=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(here),'-p','test_continuity.py'],
        text=True,capture_output=True,timeout=30,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(protocol['files'])==checked
    save('prototype_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),
        frozen_bindings_checked=checked,receiver_windows=128,retained_candidate_hypotheses=386,
        independent_counter_phase_maximum_error_samples=max(phase_errors),original_winner_inputs_exact=True,
        test_stdout=test.stdout,test_stderr=test.stderr,audit_seconds=time.monotonic()-began,
        new_detector_calls=0,new_scientific_graph_reconstructions=0,
        scope='Fixed engineering path comparison; max2 is hypothesis capacity, not source count, and shared windows are correlated.'))


def recorded_terminal():
    from collections import Counter,defaultdict
    began=time.monotonic();here=ROOT/'recorded'
    protocol=read(here/'protocol.json');seal=read(here/'RF_seal.json')
    checked=bindings(protocol['bindings'])+bindings(seal['files'])
    assert seal['protocol_sha256']==sha(here/'protocol.json')
    assert seal['preflight_sha256']==sha(ROOT/'audit/recorded_preflight.json')
    summary=read(here/'summary.json');port=read(here/'all_windows.json');windows=port['windows']
    owners=read(here/'owners.json');rows=csv_rows(here/'all_candidate_rows.csv')
    source=ROOT.parent/'ds25-20261024/DS24-0011'
    obs={r['observation_id']:r for r in read(source/'observations.json')}
    tracks={r['key']:r for r in read(source/'tracks.json')}
    original=read(source/'tracking.json');fs=port['sample_rate_hz'];period=fs/750;fperiod=1/4.4e-6
    assert len(windows)==summary['probes']==len(original['source']['probes'])==13484
    assert len({w['window_id'] for w in windows})==len(windows)
    assert len(rows)==summary['raw_candidate_rows']==60391
    assert len({r['candidate_id'] for r in rows})==len(rows)
    bywindow=defaultdict(list)
    for r in rows:bywindow[r['window_id']].append(r)
    flags=set();nearby=0;seen=set();phaseerror=0.;phys=defaultdict(set);ownerids=defaultdict(set)
    for w,probe in zip(windows,original['source']['probes']):
        assert w['window_start_counter']==int(probe['valid_start_counter'])+round(probe['probe_start_ms']*fs/1000)
        assert w['receiver_id']==probe['receiver_id'] and w['channel']==probe['channel']
        assert abs(w['time_s']-((w['window_start_counter']-w['origin_counter'])/fs+.01))<1e-10
        assert w['origin_counter']==original['clock_anchor']['sample_counter']
        phys[w['physical_window_id']].add(w['receiver_id'])
        raw=bywindow[w['window_id']];assert len(raw)==len(probe['candidates'])
        assert {r['candidate_id'] for r in raw if r['dedup_retained']=='True'}=={r['candidate_id'] for r in w['candidates']}
        winners=[r for r in raw if r['original_winner']=='True'];assert len(winners)<=1
        winner=winners[0] if winners else None
        if winner:
            oid=w['observation_id'];assert oid in obs and oid not in seen;seen.add(oid)
            native=obs[oid]
            assert float(winner['cfo_hz'])==native['measured_cfo_hz'] and float(winner['margin'])==native['fractional_margin']
            assert abs(w['time_s']-native['time_s'])<1e-10
            if w['original_owner']:ownerids[w['original_owner']].add(oid)
            best=max((r for r in raw if r['gate_passed']=='True'),key=lambda r:(float(r['margin']),-int(r['candidate_rank'])))
            assert best['candidate_id']==winner['candidate_id']
        else:assert w['observation_id'] is None
        for r,q in zip(raw,probe['candidates']):
            assert int(r['candidate_rank'])==q['candidate_rank']
            assert float(r['cfo_hz'])==q['fractional_tracking_cfo_hz'] and float(r['margin'])==q['fractional_margin']
            assert r['gate_passed']==str(q['passed_fractional_margin_gate'])
            assert r['acquired_cfo_hz']=='' and r['acquired_cfo_status']=='unavailable_in_original_contract'
            local=q['integer_epoch_sample']+q['fractional_epoch_offset_samples']
            error=abs(float(circular(float(r['global_epoch_samples'])-phase_oracle(w['window_start_counter'],w['origin_counter'],local,fs),period)))
            phaseerror=max(phaseerror,error);assert error<1e-8
            isnear=False
            if winner:
                fg=float(circular(float(r['cfo_hz'])-float(winner['cfo_hz']),fperiod))
                eg=float(circular(local-float(winner['local_epoch_samples']),period))
                assert abs(fg-float(r['winner_CFO_gap_Hz']))<1e-9 and abs(eg-float(r['winner_epoch_gap_samples']))<1e-9
                isnear=r['dedup_retained']=='True' and r['original_winner']=='False' and abs(eg)<=3 and 250<abs(fg)<=5000
            assert (r['nearby_alternative']=='True')==isnear
            if isnear:flags.add(w['window_id']);nearby+=1
    assert len(seen)==3754 and len(owners)==len(tracks)==117
    assert len(flags)==summary['flagged_windows']==483 and nearby==summary['nearby_alternative_rows']==501
    assert sum(r['gate_passed']=='True' for r in rows)==summary['gatepassing_candidate_rows']==10428
    assert sum(r['dedup_retained']=='True' for r in rows)==summary['deduplicated_candidate_rows']==5206
    assert sum(not w['original_owner'] for w in windows if w['observation_id'])==439
    assert all(len(v)==2 for v in phys.values()) and len(phys)==6742
    for owner in owners:
        assert owner['status']=='complete' and owner['path'] is None and not owner['persistent']
        assert ownerids[owner['owner']]==set(owner['original_native_ids'])==set(tracks[owner['owner']]['observation_ids'])
        own=sorted((w for w in windows if w['original_owner']==owner['owner']),key=lambda w:w['time_s'])
        times=np.array([w['time_s'] for w in own]);nflag=sum(w['window_id'] in flags for w in own)
        assert nflag==owner['pointwise_flagged_windows']
        eligible=len(own)>=5 and np.ptp(times)>=3 and np.max(np.diff(times))<=2 and nflag==0
        assert bool(eligible)==owner['control_eligible']
    controls=sorted((r for r in owners if r['control_eligible']),key=lambda r:(r['start_s'],r['receiver'],r['channel'],r['owner']))
    selection=read(here/'selection.json')
    assert len(controls)==summary['control_eligible_owners']==3
    assert selection['positive'] is None and selection['control']==controls[0]['owner'] and selection['no_replacement']
    assert not read(here/'positive_port.json')['windows']
    control=read(here/'control_port.json')
    assert {w['observation_id'] for w in control['windows']}==set(controls[0]['original_native_ids'])
    assert summary['persistent_owners']==0 and summary['completed_owners']==117 and summary['failure'] is None
    assert summary['cumulative_worker_seconds']<protocol['cap_worker_seconds']
    save('recorded_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,receiver_windows=13484,physical_acquisitions=6742,native_winners=3754,
        raw_candidates=60391,gated_candidates=10428,dedup_candidates=5206,owners_complete=117,
        maximum_counter_phase_error_samples=phaseerror,flagged_windows=483,nearby_alternatives=501,
        persistent_owners=0,positive_selection=None,control_eligible=3,selected_control=controls[0]['owner'],
        original_native_membership_exact=True,source_candidate_and_winner_join_exact=True,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_path_searches=0,
        scope='No positive under this frozen nearby-alternative persistence rule; not absence of sources or a source-count measurement.'))


def prototype_terminal():
    from collections import Counter
    began=time.monotonic();here=ROOT/'prototype';protocol=read(here/'protocol.json');seal=read(here/'RF_seal.json')
    checked=bindings(protocol['files'])+bindings(seal['files'])
    assert seal['protocol_sha256']==sha(here/'protocol.json') and seal['all_selected_terminal'] and seal['new_detector_calls']==0
    execution=read(here/'execution.json');port=read(here/'prepared/synthetic_rows.json');cfg=protocol['settings']
    assert execution['total']==execution['completed']==len(execution['records'])==24
    assert execution['cumulative_worker_seconds']<300 and not execution['truth_evaluation_before_seal']
    episodes={e['name']:e for e in port['episodes']};quality=Counter();slots=[];maxscoreerr=0.;totalpaths=0
    for record in execution['records']:
        assert record['status']=='complete'
        for key in ('selection','graph'):assert sha(record[key+'_file'])==record[key+'_sha256']
        windows=[w for w in episodes[record['episode']]['windows'] if w['receiver_id']==record['receiver_id']]
        bywindow={w['window_id']:w for w in windows}
        candidates={c['candidate_id']:(c,w) for w in windows for c in w['candidates']}
        selection=read(record['selection_file']);graphs=read(record['graph_file']);paths=selection['paths']
        assert len(paths)==len(graphs)<=2
        used=set();usedwindows=set();shared=Counter()
        for path,graph in zip(paths,graphs):
            totalpaths+=1;nodes=path['nodes'];nids=[n['candidate_id'] for n in nodes]
            assert len(nids)==len(set(nids)) and not (set(nids)&used);used.update(nids)
            wids=[candidates[n['candidate_id']][1]['window_id'] for n in nodes]
            assert len(wids)==len(set(wids));usedwindows.update(wids);shared.update(wids)
            times=np.array([bywindow[wid]['time_s'] for wid in wids]);assert np.all(np.diff(times)>0)
            for node in nodes:
                original,w=candidates[node['candidate_id']]
                if 'window_id' in node:assert w['window_id']==node['window_id']
                for key in ('cfo_hz','global_epoch_samples','local_epoch_samples','margin','candidate_rank'):
                    assert node[key]==original[key]
            if record['method']=='original_winners':
                expected=[max(w['candidates'],key=lambda c:(c['margin'],-c['candidate_rank']))['candidate_id'] for w in windows if w['candidates']]
                assert nids==expected and path['score'] is None
            else:
                assert len(nodes)>=8 and np.ptp(times)>=6
                reward=[9+math.log(n['margin']/max(c['margin'] for c in bywindow[n['window_id']]['candidates'])) for n in nodes]
                dt=np.diff(times);assert np.all((dt>=.15)&(dt<=10))
                vf=circular(np.diff([n['cfo_hz'] for n in nodes]),cfg['cfo_period_hz'])/dt
                ve=circular(np.diff([n['global_epoch_samples'] for n in nodes]),port['sample_rate_hz']/750)/dt
                assert np.max(abs(vf))<=8000
                score=sum(reward)-18-.05*sum(dt)
                for sigma,accel,velocity in [(150.,20.,vf)]+([(3.,20.,ve)] if record['method']=='epoch_cfo' else []):
                    a,b=dt[:-1],dt[1:]
                    variance=2*sigma**2*(1/a**2+1/b**2+1/(a*b))+(accel*(a+b)/2)**2
                    score-=float(np.sum(2*np.diff(velocity)**2/variance))
                error=abs(score-path['score']);maxscoreerr=max(maxscoreerr,error);assert error<1e-8
                for k,interval in enumerate(path['intervals']):
                    assert abs(interval['elapsed_s']-dt[k])<1e-10
                    assert abs(interval['cfo_slope_hz_s']-vf[k])<1e-8 and abs(interval['epoch_slope_samples_s']-ve[k])<1e-8
                    assert interval['epoch_winding_not_physically_identified']
                for field,velocity,period in [('cfo_hz',vf,cfg['cfo_period_hz']),('global_epoch_samples',ve,port['sample_rate_hz']/750)]:
                    lifted=np.r_[nodes[0][field],nodes[0][field]+np.cumsum(velocity*dt)]
                    label='cfo_alias_lift' if field=='cfo_hz' else 'epoch_winding_lift'
                    assert [n[label] for n in nodes]==np.rint((lifted-np.array([n[field] for n in nodes]))/period).astype(int).tolist()
            assert not graph['independent_source_evidence'] and graph['original_quality_gates']
            assert len(graph['rows'])==len(nodes)
            rowids={r['observation_id'] for r in graph['rows']};assert len(rowids)==len(graph['rows'])
            for row,node in zip(graph['rows'],nodes):
                assert row['candidate_id']==node['candidate_id'] and row['measured_cfo_hz']==node['cfo_hz']
                assert row['observation_id']==candidates[node['candidate_id']][1]['observation_id']
            for track in graph['tracks']:
                assert set(track['observation_ids'])<=rowids and len(track['observation_ids'])<=16
                assert track['quality_status']!='no_structure_detected';quality[track['quality_status']]+=1
                ix=track['indices'];values=np.array([graph['rows'][i]['measured_cfo_hz'] for i in ix])
                assert np.max(abs(circular(values-np.array(track['values']),cfg['cfo_period_hz'])))<1e-8
        assert selection['candidate_hypotheses_selected']==len(used)
        assert selection['unique_receiver_windows']==len(usedwindows) and selection['total_receiver_windows']==16
        assert set(selection['windows_without_selected_path'])==set(bywindow)-usedwindows
        if record['method']!='original_winners':
            assert set(selection['unselected_candidate_ids'])==set(candidates)-used
            assert selection['shared_window_counts']=={wid:shared[wid] for wid in bywindow}
        slots.append(dict(episode=record['episode'],receiver=record['receiver_id'],method=record['method'],
            paths=len(paths),selected_candidate_hypotheses=len(used),unique_windows=len(usedwindows),
            shared_windows=sum(v>1 for v in shared.values())))
    save('prototype_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,terminal_slots=24,path_hypotheses=totalpaths,slots=slots,
        maximum_independent_path_score_error=maxscoreerr,literal_graph_quality_counts=dict(quality),
        all_graph_tracks_below20points=True,no_quality_qualified_tracks=True,candidate_exclusivity_and_unique_windows_passed=True,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_graph_calls=0,new_path_searches=0,
        scope='Engineering candidate paths on reused toy sequences, not independent observations, calibrated identities or operational associations.'))


def final_seal():
    began=time.monotonic();here=ROOT/'audit'
    receipt_names=['grid_readback.json','recorded_preflight.json','recorded_terminal.json',
        'prototype_preflight.json','prototype_terminal.json','single_source_preflight.json',
        'single_source_terminal.json','single_application_preflight.json','single_application_terminal.json']
    receipts=[read(here/n) for n in receipt_names]
    assert all(r['all_passed'] for r in receipts)
    paths=[here/n for n in receipt_names]+[here/'check.py',here/'FINDINGS.md',here/'NEXT_DIRECTIONS.md',
        here/'grid_attempt01.json',here/'prototype_terminal_attempt01.json',here/'final_seal_attempt01.json']
    for branch,protocol_name in [('recorded','protocol.json'),('prototype','protocol.json'),
        ('single_source','protocol.json'),('prototype/single_application','protocol.json')]:
        branch=ROOT/branch;protocol=read(branch/protocol_name)
        bindings(protocol.get('bindings',protocol.get('files')))
        bindings(read(branch/'RF_seal.json')['files'])
        paths.extend([branch/protocol_name,branch/'RF_seal.json'])
    for report in ['grid/seal.json','recorded/report/seal.json','prototype/report/seal.json','prototype/report02/seal.json']:
        p=ROOT/report
        base=ROOT/report.split('/')[0]
        bindings({str(Path(k) if Path(k).is_absolute() else base/k):v for k,v in read(p)['files'].items()})
        paths.append(p)
    paths.extend([ROOT/'recorded/FINDINGS.md',ROOT/'prototype/FINDINGS.md'])
    for episode in read(ROOT/'prototype/prepared/synthetic_rows.json')['episodes']:
        for rx in ('0','1'):
            choices=[]
            for method in ('cfo_only','epoch_cfo'):
                d=read(ROOT/'prototype/selections'/f"{episode['name']}_RX{rx}_{method}.json")
                choices.append([[n['candidate_id'] for n in p['nodes']] for p in d['paths']])
            assert choices[0]==choices[1]
    # Independent saved-value truth readback; no selection is performed.
    truth_cache={};truth_rows=csv_rows(ROOT/'prototype/report/selected_hypotheses.csv')
    for row in truth_rows:
        visit=int(float(row['time_s'])-.01+.5);key=(row['episode'],visit)
        if key not in truth_cache:
            truth_cache[key]=read(ROOT.parent/'ds24-measurement-continuity-r01/measurement/slots'/f'{key[0]}_{key[1]:02}.json')['sources']
        errors=[];epochs=[]
        for source in truth_cache[key]:
            errors.append(float(circular(float(row['cfo_hz'])-source['cfo0']-source['rate']*float(row['time_s']),1/4.4e-6)))
            epochs.append(float(circular(float(row['global_epoch_samples'])-source['epoch'],10_000_000/750)))
        for i,letter in enumerate(('A','B')):
            assert abs(errors[i]-float(row[f'CFO_error_{letter}_Hz']))<1e-8
            assert abs(epochs[i]-float(row[f'epoch_error_{letter}_samples']))<1e-8
        for label,ix in [('cfo_label',[i for i,v in enumerate(errors) if abs(v)<=450]),
            ('joint_label',[i for i,v in enumerate(errors) if abs(v)<=450 and abs(epochs[i])<=3])]:
            expected=('A','B')[ix[0]] if len(ix)==1 else ('ambiguous' if ix else 'unmatched')
            assert row[label]==expected
    assert read(ROOT/'prototype/report02/summary.json')['new_scientific_runs']==0
    total=sum(r['audit_seconds'] for r in receipts)+3+(time.monotonic()-began)
    assert total<120
    save('final_seal.json',dict(all_passed=True,passed_receipts=len(receipts),
        files={str(p):sha(p) for p in paths},audit_seconds_including_three_conservative_reader_failure_charges=total,
        independent_saved_truth_rows_checked=len(truth_rows),CFO_only_and_epoch_CFO_paths_identical_in_all_eight_primary_lanes=True,
        new_detector_calls=0,new_graph_calls=0,new_scientific_path_searches=0,
        scope='Scientific and final branch-report checks; root publication narrative/outer manifests are sealed independently, avoiding circular dependencies.'))


def single_application_terminal():
    from collections import Counter
    began=time.monotonic();here=ROOT/'prototype/single_application'
    protocol=read(here/'protocol.json');seal=read(here/'RF_seal.json')
    checked=bindings(protocol['files'])+bindings(seal['files'])
    assert seal['protocol_sha256']==sha(here/'protocol.json') and seal['all_selected_terminal']
    execution=read(here/'execution.json');port=read(here/'rows.json')
    assert execution['total']==execution['completed']==len(execution['records'])==6
    assert execution['cumulative_original_A_budget_seconds']<300
    assert execution['new_detector_calls_by_A']==0 and not execution['truth_evaluation_before_seal']
    slots=[];quality=Counter();maxerr=0.
    for record in execution['records']:
        assert record['status']=='complete'
        for key in ('selection','graph'):assert sha(record[key+'_file'])==record[key+'_sha256']
        windows=[w for w in port['windows'] if w['receiver_id']==record['receiver_id']]
        candidate={c['candidate_id']:(c,w) for w in windows for c in w['candidates']}
        selection=read(record['selection_file']);graphs=read(record['graph_file']);paths=selection['paths']
        assert len(paths)==len(graphs)<=2;used=set();shared=Counter();joint_errors=[]
        for path,graph in zip(paths,graphs):
            nodes=path['nodes'];ids=[n['candidate_id'] for n in nodes]
            assert len(ids)==len(set(ids)) and not used.intersection(ids);used.update(ids)
            wids=[candidate[n['candidate_id']][1]['window_id'] for n in nodes]
            assert len(set(wids))==len(nodes);shared.update(wids)
            t=np.array([candidate[n['candidate_id']][1]['time_s'] for n in nodes]);assert np.all(np.diff(t)>0)
            for node in nodes:
                c,w=candidate[node['candidate_id']]
                for field in ('candidate_rank','cfo_hz','local_epoch_samples','global_epoch_samples','margin'):
                    assert node[field]==c[field]
            if record['method']=='original_winners':
                assert ids==[max(w['candidates'],key=lambda c:(c['margin'],-c['candidate_rank']))['candidate_id'] for w in windows]
                assert path['score'] is None
            else:
                assert len(nodes)>=8 and np.ptp(t)>=6
                dt=np.diff(t);assert np.all((dt>=.15)&(dt<=10))
                f=circular(np.diff([n['cfo_hz'] for n in nodes]),1/4.4e-6)/dt
                e=circular(np.diff([n['global_epoch_samples'] for n in nodes]),10_000_000/750)/dt
                assert max(abs(f))<=8000
                score=sum(9+math.log(n['margin']/max(c['margin'] for c in candidate[n['candidate_id']][1]['candidates'])) for n in nodes)-18-.05*sum(dt)
                for sigma,velocity in [(150,f)]+([(3,e)] if record['method']=='epoch_cfo' else []):
                    a,b=dt[:-1],dt[1:];variance=2*sigma**2*(1/a**2+1/b**2+1/(a*b))+(20*(a+b)/2)**2
                    score-=float(np.sum(2*np.diff(velocity)**2/variance))
                err=abs(score-path['score']);assert err<1e-8;maxerr=max(maxerr,err)
                for k,interval in enumerate(path['intervals']):
                    assert abs(interval['elapsed_s']-dt[k])<1e-10
                    assert abs(interval['cfo_slope_hz_s']-f[k])<1e-8 and abs(interval['epoch_slope_samples_s']-e[k])<1e-8
            assert len(graph['rows'])==len(nodes) and not graph['independent_source_evidence']
            for row,node in zip(graph['rows'],nodes):
                c,w=candidate[node['candidate_id']]
                assert row['candidate_id']==node['candidate_id'] and row['observation_id']==w['observation_id']
                assert row['measured_cfo_hz']==node['cfo_hz'] and row['time_s']==w['time_s']
            for track in graph['tracks']:
                assert track['quality_status']!='no_structure_detected';quality[track['quality_status']]+=1
                assert set(track['observation_ids'])<={row['observation_id'] for row in graph['rows']}
        assert selection['candidate_hypotheses_selected']==len(used)
        assert selection['unique_receiver_windows']==len(shared) and selection['total_receiver_windows']==24
        if record['method']!='original_winners':
            assert set(selection['unselected_candidate_ids'])==set(candidate)-used
            assert selection['shared_window_counts']=={w['window_id']:shared[w['window_id']] for w in windows}
        slots.append(dict(receiver=record['receiver_id'],method=record['method'],path_points=[len(p['nodes']) for p in paths],
            unique_receiver_windows=len(shared),shared_windows=sum(v>1 for v in shared.values())))
    save('single_application_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,terminal_slots=6,slots=slots,maximum_independent_path_score_error=maxerr,
        literal_graph_quality_counts=dict(quality),no_quality_qualified_tracks=True,candidate_ownership_and_unique_windows_passed=True,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_graph_calls=0,new_path_searches=0,
        scope='One injected source produces secondary path hypotheses; none is a quality-qualified extra track, and this is not an empirical false-acceptance rate.'))


def single_application_preflight():
    began=time.monotonic();here=ROOT/'prototype/single_application'
    protocol=read(here/'protocol.json');checked=bindings(protocol['files'])
    assert sha(here/'protocol.json')=='2d0dd365f3b848698cce6ef8dd17285c04f9f6a66a3afb425b8f74cf69fb4e3c'
    assert protocol['selector_protocol_sha256']==sha(ROOT/'prototype/protocol.json')
    assert protocol['settings']==read(ROOT/'prototype/protocol.json')['settings']
    assert protocol['lane_method_slots']==6 and protocol['no_policy_change'] and protocol['new_detector_calls_by_A']==0
    assert protocol['previous_primary_cumulative_seconds']==read(ROOT/'prototype/execution.json')['cumulative_worker_seconds']
    assert protocol['total_original_numerical_budget_seconds']==300
    assert read(ROOT/'audit/single_source_terminal.json')['all_passed']
    port=read(here/'rows.json');prep=read(here/'preparation.json')
    assert prep['all_passed'] and prep['windows']==len(port['windows'])==48 and prep['candidates']==78
    assert len({w['window_id'] for w in port['windows']})==48
    n=0
    for w in port['windows']:
        visit=round(w['window_start_counter']/10_000_000)
        slot=read(ROOT/'single_source/slots'/f'single_source_{visit:02}.json')
        rx=next(r for r in slot['receivers'] if str(r['receiver_id'])==w['receiver_id'])
        raw={p['candidate_rank']:p for p in rx['candidates']};n+=len(raw)
        assert w['time_s']==visit+.01 and w['duration_samples']==200000
        for c in w['candidates']:
            p=raw[c['candidate_rank']]
            assert c['cfo_hz']==p['fractional_tracking_cfo_hz'] and c['margin']==p['fractional_margin']
            assert c['local_epoch_samples']==p['epoch_sample']+p['fractional_epoch_offset_samples']
            expected=phase_oracle(w['window_start_counter'],w['origin_counter'],c['local_epoch_samples'],10_000_000)
            assert abs(expected-c['global_epoch_samples'])<1e-8
            assert not any(k in c for k in ('source','truth','label','norad'))
    assert n==384
    test=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'prototype'),'-p','test_single_application.py'],
        capture_output=True,text=True,timeout=15,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(protocol['files'])==checked
    save('single_application_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),
        frozen_bindings_checked=checked,receiver_windows=48,raw_peaks=384,retained_hypotheses=78,
        exact_original_selector_and_settings=True,test_stdout=test.stdout,test_stderr=test.stderr,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_graph_calls=0,
        scope='Thin port-only application to the response-sealed single-source control, no selector or graph-policy change.'))


def single_source_terminal():
    began=time.monotonic();here=ROOT/'single_source'
    protocol=read(here/'protocol.json');seal=read(here/'RF_seal.json')
    checked=bindings(protocol['bindings'])+bindings(seal['files'])
    execution=read(here/'execution.json');prep=read(here/'preparation.json')
    assert execution['identity_before']==execution['identity_after']==prep['identity']
    assert execution['slots']==execution['complete']==execution['detector_calls_attempted']==seal['complete']==24
    assert execution['position_fits']==0 and execution['cumulative_worker_seconds']<=120
    assert abs(execution['cumulative_worker_seconds']-execution['run_seconds']-protocol['initial_preparation_seconds'])<1e-5
    hashes=set();noises=set();rxrows=peaks=0
    for visit in range(24):
        slot=read(here/'slots'/f'single_source_{visit:02}.json')
        assert slot['status']=='complete' and slot['visit']==slot['time_s']==visit
        assert slot['law']=='sampled_deployed' and slot['sources']==[protocol['source']]
        inp=slot['input'];assert inp['sources']==[protocol['source']] and inp['source_count']==1
        assert inp['seed']==[2026102603,visit] and inp['clipping_samples']==0
        assert inp['global_start_seconds']==float(visit)
        hashes.add(inp['iq_sha256']);noises.add(inp['noise_sha256'])
        assert {r['receiver_id'] for r in slot['receivers']}=={0,1}
        for rx in slot['receivers']:
            rxrows+=1;peaks+=len(rx['candidates'])
            assert len({p['candidate_rank'] for p in rx['candidates']})==len(rx['candidates'])
            for p in rx['candidates']:
                if p['fractional_epoch_status']=='complete':
                    assert abs(p['fractional_frame_phase_sample']-p['epoch_sample']-p['fractional_epoch_offset_samples'])<1e-10
                    assert math.isfinite(p['fractional_tracking_cfo_hz']) and math.isfinite(p['fractional_margin'])
    assert len(hashes)==len(noises)==24 and rxrows==48
    save('single_source_terminal.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),RF_seal_sha256=sha(here/'RF_seal.json'),
        frozen_bindings_checked=checked,detector_calls=24,receiver_outputs=48,exported_peak_hypotheses=peaks,
        source_count_per_window=1,complete_calls=24,failed_calls=0,unique_IQ_hashes=24,unique_noise_hashes=24,
        cumulative_worker_seconds=execution['cumulative_worker_seconds'],historical_identity_exact=True,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_graph_calls=0,
        scope='Response-only single-source toy control. Selector application and source-proximity evaluation are separate post-seal artifacts.'))


def single_source_preflight():
    began=time.monotonic();here=ROOT/'single_source'
    protocol=read(here/'protocol.json');checked=bindings(protocol['bindings'])
    assert sha(here/'protocol.json')=='42173ff1e0a73abf998681a0639b749799f8de9298669a1ff27d8470c5f1fa95'
    assert protocol['visits']==list(range(24)) and protocol['detector_calls']==24
    assert protocol['receivers']==2 and protocol['cap_seconds']==120 and protocol['seed']==2026102603
    assert protocol['source']==dict(name='A',cfo0=100000.,rate=200.,amplitude=1000.,phase=.3,epoch=127)
    assert protocol['law']=='sampled_deployed' and protocol['no_position_fit']
    assert protocol['selector_protocol_sha256']==sha(ROOT/'prototype/protocol.json')
    assert read(ROOT/'audit/prototype_preflight.json')['all_passed']
    prep=read(here/'preparation.json');assert prep['all_passed'] and prep['tests']==4 and prep['detector_calls']==0
    assert prep['identity']==read(ROOT.parent/'ds24-measurement-continuity-r01/measurement/detector_identity.json')
    env=dict(os.environ,PYTHONPATH='/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src',
        PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    test=subprocess.run(['/opt/leo-fast-auto/20261010-r1/venv/bin/python','-B','-m','unittest','discover',
        '-s',str(here),'-p','test_single.py'],env=env,capture_output=True,text=True,timeout=15)
    assert test.returncode==0,test.stdout+test.stderr
    assert bindings(protocol['bindings'])==checked
    save('single_source_preflight.json',dict(all_passed=True,protocol_sha256=sha(here/'protocol.json'),
        frozen_bindings_checked=checked,tests_stdout=test.stdout,tests_stderr=test.stderr,
        audit_seconds=time.monotonic()-began,new_detector_calls=0,new_graph_calls=0,
        selector_unchanged=True,pre_response_freeze=True,
        scope='Known-single-source sampled-template negative control; inverse-model test, not waveform authority or empirical field false-positive calibration.'))


if __name__ == '__main__':
    globals()[sys.argv[1]]()
