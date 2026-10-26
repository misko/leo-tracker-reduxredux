"""Frozen CH8-only/CH7-only ordinary-VI delta partition, no GPS."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import time
import traceback

from prepare import HERE,load,sha,write
import localize as loc


def subsets(rows):
    result={channel:[r for r in rows if r['role']==role] for channel,role in
            (('CH8_only','CH8_target'),('CH7_only','CH7_control'))}
    ids=[r['native_observation_id'] for rr in result.values() for r in rr]
    if len(ids)!=len(set(ids)) or set(ids)!={r['native_observation_id'] for r in rows}:
        raise ValueError('channel subsets must exactly partition complete native vector')
    return result


def freeze():
    rows=load(HERE/'corrections.json')['rows'];partition=subsets(rows)
    write(HERE/'channel_subsets.json',dict(subsets=partition,counts={k:len(v) for k,v in partition.items()},
        no_GPS_selection=True,source_corrections_sha256=sha(HERE/'corrections.json'),
        same_vectors_both_c_arms=True,expected_owner_cells=8,available_owner_cells=7))
    paths=[Path(__file__),HERE/'ADDENDUM_02.md',HERE/'channel_subsets.json',HERE/'localize.py',HERE/'position/protocol.json',HERE/'RF_seal.json']
    write(HERE/'channel_protocol.json',dict(files={str(p):sha(p) for p in paths},fits=8,models=['ordinary_VI'],
        methods=['CH8_only','CH7_only'],start_km=[0.,0.],phase='zero',phase_rounds=5,iterations=48,
        per_case_seconds=70,outer_job_seconds=90,shared_originals='position/*/ordinary_VI/original',GPS_used=False))
    print('CHANNEL_FROZEN',sha(HERE/'channel_protocol.json'),flush=True)


def case_job(case):
    began=time.monotonic();deadline=began+70.;rows=[]
    try:
        loc.alarm(deadline-time.monotonic());d=loc.r.context(case)
        packets=load(HERE/'position/packets.json')
        controls={(r['case'],r['arm']):r for r in load(HERE/'position/preparation.json')['controls']}
        for method,subset in load(HERE/'channel_subsets.json')['subsets'].items():
            selected=[r for r in subset if r['case']==case]
            updated,receipt=loc.replacement.inject(d,selected,[r['native_observation_id'] for r in selected])
            loc.save(Path(case)/'ordinary_VI'/method/'injection.json',receipt)
            for arm in ('c0','fitted_c'):
                try:
                    row=loc.solve(updated,arm,'ordinary_VI',method,packets[case+'_'+arm],controls[(case,arm)],deadline)
                except Exception as exc:
                    row=dict(case=case,kind='ordinary_VI',method=method,arm=arm,status='failed',error=repr(exc),traceback=traceback.format_exc(),GPS_used=False)
                    loc.save(Path(case)/'ordinary_VI'/method/(arm+'_result.json'),row)
                finally:
                    signal.setitimer(signal.ITIMER_REAL,0)
                rows.append(row)
    except Exception as exc:
        loc.save(Path(case)/'channel_failure.json',dict(error=repr(exc),traceback=traceback.format_exc()))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    return dict(case=case,rows=rows,seconds=time.monotonic()-began,GPS_used=False)


def run():
    for path,digest in load(HERE/'channel_protocol.json')['files'].items():
        assert sha(path)==digest,'frozen channel source changed '+path
    for path,digest in load(HERE/'position/RF_seal.json')['files'].items():
        assert sha(path)==digest,'main inference artifact changed '+path
    write(HERE/'channel_launch.json',dict(protocol_sha256=sha(HERE/'channel_protocol.json'),main_inference_RF_seal_sha256=sha(HERE/'position/RF_seal.json'),GPS_used=False))
    with ProcessPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(case_job,('DS24-0010','DS24-0011')))
    write(HERE/'channel_execution.json',dict(results=results,cumulative_worker_seconds=sum(r['seconds'] for r in results),GPS_used=False))
    paths=[HERE/'channel_protocol.json',HERE/'channel_subsets.json',HERE/'channel_launch.json',HERE/'channel_execution.json',HERE/'position/RF_seal.json']
    paths += [p for p in (HERE/'position').rglob('*.json') if 'CH7_only' in p.parts or 'CH8_only' in p.parts]
    write(HERE/'channel_RF_seal.json',dict(files={str(p):sha(p) for p in paths},GPS_used=False))
    print('CHANNEL_INFERENCE_SEALED',sha(HERE/'channel_RF_seal.json'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
