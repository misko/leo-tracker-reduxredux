"""Verify fixed-origin process receipts; scientific comparisons are separate."""
import argparse
import json
from pathlib import Path


def evaluate(rows, clocks, period_ns, count):
    if not rows or rows[0].get('kind')!='cadence' or rows[-1].get('kind')!='summary':
        raise ValueError('missing controller boundaries')
    header,summary=rows[0],rows[-1]
    if header['period_ns']!=period_ns or header['scans']!=count or len(clocks)!=count:
        raise ValueError('wrong cadence scope')
    if not summary.get('success') or summary['completed_scans']!=count:
        raise ValueError('incomplete controller')
    if header['pending_capacity']!=1 or header['detector_capacity']!=2:
        raise ValueError('unexpected capacity')
    active={};starts={};ends={};pending=[];peak_pending=0;peak_detectors=0;memory=[];last=-1
    for row in rows[1:-1]:
        stamp=row['monotonic_ns']
        if type(stamp) is not int or stamp<last:raise ValueError('nonmonotonic receipt')
        last=stamp
        if row['kind']=='memory':
            if row['pending_scans']!=len(pending) or row['process_tree_rss_kib']<0:
                raise ValueError('memory inventory mismatch')
            memory.append(row['process_tree_rss_kib']);continue
        if row['kind'] not in ('launch','finish'):raise ValueError('unknown event')
        i=row['scan'];detector=row['detector'];key=(i,detector)
        if type(i) is not int or not 0<=i<count or type(detector) is not bool:
            raise ValueError('invalid child identity')
        if row['kind']=='launch':
            if key in starts:raise ValueError('duplicate launch')
            if row['scan_origin_ns']!=header['origin_ns']+period_ns*i:
                raise ValueError('rebased scan origin')
            if detector:
                if stamp>=row['scan_origin_ns']:raise ValueError('late detector launch')
            else:
                if not pending or pending.pop(0)!=i or any(not k[1] for k in active):
                    raise ValueError('downstream dependency or serialization failure')
            starts[key]=stamp;active[key]=row['pid']
        else:
            if key not in active or row['exit_code']!=0:raise ValueError('missing or failed child')
            del active[key];ends[key]=stamp
            if detector:pending.append(i)
        peak_pending=max(peak_pending,len(pending))
        peak_detectors=max(peak_detectors,sum(k[1] for k in active))
        if peak_pending>1 or peak_detectors>2:raise ValueError('capacity exceeded')
    if active or pending or len(ends)!=count*2 or not memory:raise ValueError('incomplete inventory')
    if (summary['pending_high_water'],summary['detector_process_high_water'],summary['sampled_peak_process_tree_rss_kib'])!=(peak_pending,peak_detectors,max(memory)):
        raise ValueError('summary does not match events')
    scans=[]
    for i,clock in enumerate(clocks):
        origin=header['origin_ns']+period_ns*i
        if clock.get('kind')!='replay_clock' or clock.get('clock')!='CLOCK_MONOTONIC' or not clock.get('external_origin'):
            raise ValueError('missing explicit detector clock')
        if clock['origin_ns']!=origin or not starts[i,True]<=clock['ready_ns']<origin:
            raise ValueError('detector shifted origin or initialized late')
        scans.append({'scan':i,'origin_ns':origin,
                      'detector_finish_after_origin_s':(ends[i,True]-origin)/1e9,
                      'downstream_wait_s':(starts[i,False]-ends[i,True])/1e9,
                      'downstream_wall_s':(ends[i,False]-starts[i,False])/1e9,
                      'downstream_finished_before_next_scan_ready':ends[i,False]<=ends[i+1,True] if i+1<count else None})
    return {'fixed_cadence_and_capacity_passed':True,'scans':scans,
            'pending_high_water':peak_pending,'detector_process_high_water':peak_detectors,
            'sampled_peak_process_tree_rss_kib':max(memory),
            'scope':'Finite repeated-recording scheduling evidence only; cold first scan and final downstream drain have different contention; scientific checks required separately'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path);a=p.parse_args()
    protocol=json.loads((a.report/'protocol.json').read_text())
    rows=[json.loads(x) for x in (a.report/'controller.stdout').read_text().splitlines()]
    clocks=[]
    for i in range(len(protocol['scans'])):
        lines=(a.report/f'scan-{i}/detector.stderr').read_text().splitlines()
        clocks.append(next(json.loads(x) for x in lines if x.startswith('{') and json.loads(x).get('kind')=='replay_clock'))
    result=evaluate(rows,clocks,protocol['period_ms']*1_000_000,len(protocol['scans']))
    with (a.report/'schedule-evaluation.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main()
