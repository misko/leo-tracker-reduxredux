"""Thin application of immutable 5654 policy to root's sealed single-source control."""
import time
STARTED = time.monotonic()
import argparse
import json
from pathlib import Path
import unittest
import experiment as e
import continuity as c

HERE = Path(__file__).resolve().parent
OUT = HERE/'single_application'
INPUT = HERE.parent/'single_source'


def port_window(slot, rx, name):
    start = round(slot['time_s']*e.RATE); receiver = int(rx['receiver_id'])
    wid = e.identity(f'{name}:RX{receiver}:{start}')
    original = e.identity(f"synthetic:{name}:RX{receiver}:visit{slot['visit']}")
    w = dict(window_id=wid, observation_id=original,
        physical_acquisition_id=e.identity(f'{name}:{start}'), receiver_id=str(receiver),
        channel=1, actual_rf_hz=10940312500., time_s=slot['time_s']+.01,
        sample_rate_hz=e.RATE, window_start_counter=start, origin_counter=0,
        duration_samples=200000, candidates=[])
    exported = []
    for peak in rx['candidates']:
        complete = peak['fractional_epoch_status'] == 'complete' and all(peak[k] is not None for k in
            ('fractional_epoch_offset_samples', 'fractional_tracking_cfo_hz', 'fractional_exact_score',
             'fractional_control_score', 'fractional_margin'))
        if complete:
            exported.append(dict(candidate_rank=peak['candidate_rank'], integer_epoch_sample=peak['epoch_sample'],
                fractional_epoch_offset_samples=peak['fractional_epoch_offset_samples'],
                fractional_tracking_cfo_hz=peak['fractional_tracking_cfo_hz'], fractional_margin=peak['fractional_margin'],
                passed_fractional_margin_gate=peak['fractional_margin'] >= .025))
    exported.sort(key=lambda x:x['candidate_rank'])
    dedup = e.load_module('single_application_dedup', e.REPO/'tools/ds23_frame_registration.py')
    for peak in dedup.unique_peaks(exported, e.RATE):
        native = next(x for x in rx['candidates'] if x['candidate_rank'] == peak['rank'])
        w['candidates'].append(dict(candidate_id=e.identity(wid+':rank'+str(peak['rank'])),
            candidate_rank=peak['rank'], cfo_hz=peak['cfo'], margin=peak['margin'],
            local_epoch_samples=peak['epoch'], global_epoch_samples=c.global_epoch(start,0,peak['epoch'],e.RATE),
            acquired_cfo_hz=native['acquired_cfo_hz']))
    return w


def prepare():
    OUT.mkdir(exist_ok=False)
    seal = json.loads((INPUT/'RF_seal.json').read_text())
    # The root detector seal may use relative or absolute file keys; both bind exact bytes.
    for path, digest in seal['files'].items():
        p=Path(path);p=p if p.is_absolute() else INPUT/p
        if e.sha(p) != digest: raise ValueError('new sealed control changed: '+str(p))
    windows=[];ledger=[]
    for i in range(24):
        s=json.loads((INPUT/'slots'/f'single_source_{i:02}.json').read_text())
        if s['status']!='complete': raise ValueError('control slot unavailable')
        for rx in s['receivers']:
            w=port_window(s,rx,'single_source');windows.append(w)
            ledger.append(dict(window_id=w['window_id'],raw_candidates=rx['candidates'],
                               retained_ranks=[c['candidate_rank'] for c in w['candidates']]))
    windows.sort(key=lambda w:(w['receiver_id'],w['time_s']))
    for rx in ('0','1'): c.validate([w for w in windows if w['receiver_id']==rx],e.RATE)
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_single_application.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise RuntimeError('thin adapter test failed')
    e.write(OUT/'rows.json',dict(schema='rf-candidate-windows/v1',sample_rate_hz=e.RATE,
        frame_rate_hz=750,windows=windows,raw_ledger=ledger))
    e.write(OUT/'preparation.json',dict(all_passed=True,seconds=time.monotonic()-STARTED,
        windows=len(windows),candidates=sum(len(w['candidates']) for w in windows),tests_run=result.testsRun,
        truth_fields_used=False,new_detector_calls=0))


def freeze():
    if (OUT/'protocol.json').exists():raise FileExistsError('already frozen')
    primary=json.loads((HERE/'execution.json').read_text())
    files=[Path(__file__),HERE/'test_single_application.py',HERE/'continuity.py',HERE/'experiment.py',
        HERE/'protocol.json',HERE/'RF_seal.json',HERE/'execution.json',OUT/'preparation.json',OUT/'rows.json',
        INPUT/'protocol.json',INPUT/'RF_seal.json',e.CONFIG,e.REPO/'tools/ds23_frame_registration.py']
    files+=sorted((INPUT/'slots').glob('single_source_*.json'))
    e.write(OUT/'protocol.json',dict(files={str(p):e.sha(p) for p in files},settings=c.SETTINGS,
        selector_protocol_sha256=e.sha(HERE/'protocol.json'),methods=['original_winners','cfo_only','epoch_cfo'],
        lane_method_slots=6,previous_primary_cumulative_seconds=primary['cumulative_worker_seconds'],
        preparation_seconds=json.loads((OUT/'preparation.json').read_text())['seconds'],
        total_original_numerical_budget_seconds=300.,new_detector_calls_by_A=0,
        no_source_count_inference=True,no_policy_change=True))


def run():
    if (OUT/'execution.json').exists():raise FileExistsError('no reruns')
    p=json.loads((OUT/'protocol.json').read_text())
    for path,digest in p['files'].items():
        if e.sha(path)!=digest:raise ValueError('frozen input/source changed: '+path)
    audit=json.loads((HERE.parent/'audit/single_application_preflight.json').read_text())
    if not audit['all_passed'] or audit['protocol_sha256']!=e.sha(OUT/'protocol.json'):
        raise ValueError('exact B binding preflight required')
    deadline=STARTED+300.-p['previous_primary_cumulative_seconds']-p['preparation_seconds']
    port=json.loads((OUT/'rows.json').read_text());records=[]
    for rx in ('0','1'):
        windows=[w for w in port['windows'] if w['receiver_id']==rx]
        for method in p['methods']:
            record=dict(receiver_id=rx,method=method);began=time.monotonic()
            try:
                e.alarm(deadline-time.monotonic())
                if method=='original_winners':
                    nodes=c.winner_rows(windows)
                    result=dict(paths=[dict(nodes=nodes,score=None)],candidate_hypotheses_selected=len(nodes),
                        unique_receiver_windows=len(nodes),total_receiver_windows=len(windows))
                else:result=c.select_paths(windows,e.RATE,include_epoch=method=='epoch_cfo')
                path=OUT/'selections'/f'RX{rx}_{method}.json';e.write(path,result)
                graph=[e.graph_for(windows,q['nodes'],f'single_source_RX{rx}_{method}_P{i}') for i,q in enumerate(result['paths'])]
                graphpath=OUT/'graphs'/path.name;e.write(graphpath,graph)
                record.update(status='complete',selection_file=str(path),selection_sha256=e.sha(path),
                              graph_file=str(graphpath),graph_sha256=e.sha(graphpath))
            except Exception as exc:record.update(status='failed',error=repr(exc))
            finally:
                import signal
                signal.setitimer(signal.ITIMER_REAL,0)
            record['seconds']=time.monotonic()-began;records.append(record)
    total=p['previous_primary_cumulative_seconds']+p['preparation_seconds']+time.monotonic()-STARTED
    e.write(OUT/'execution.json',dict(records=records,total=6,completed=sum(x['status']=='complete' for x in records),
        cumulative_original_A_budget_seconds=total,new_detector_calls_by_A=0,truth_evaluation_before_seal=False))
    files=[x for x in OUT.rglob('*') if x.is_file() and x.name!='RF_seal.json']
    e.write(OUT/'RF_seal.json',dict(protocol_sha256=e.sha(OUT/'protocol.json'),all_selected_terminal=True,
        files={str(x):e.sha(x) for x in files}))
    print(json.dumps(dict(completed=sum(x['status']=='complete' for x in records),total=6,cumulative_seconds=total)))


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('command',choices=('prepare','freeze','run'))
    args=a.parse_args();{'prepare':prepare,'freeze':freeze,'run':run}[args.command]()
