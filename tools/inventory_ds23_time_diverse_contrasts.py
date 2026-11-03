"""Inventory repeated same-pair RF evidence without GPS or new IQ reads."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from itertools import combinations
from pathlib import Path
import signal
import numpy as np

from inventory_ds23_active_differential_pairs import matching_curve
from probe_ds23_same_probe_curves import lanes,SOURCE
from probe_ds23_sign_carrier_position import context_signed
from select_ds23_differential_information import OUT as PARENT
from run_algo01_ds23_sample import read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=PARENT/'time_diverse_inventory_v2'


def triplet(rows,minimum_span_s=20.,minimum_gap_s=5.):
    ordered=sorted(rows,key=lambda r:(r['time_s'],-r['minimum_native_margin'],r['probe']))
    unique={r['probe']:r for r in reversed(ordered)}
    ordered=sorted(unique.values(),key=lambda r:r['time_s'])
    if len(ordered)<3:return None
    first,last=ordered[0],ordered[-1];span=last['time_s']-first['time_s']
    if span<minimum_span_s:return None
    middle=[r for r in ordered[1:-1] if r['time_s']-first['time_s']>=minimum_gap_s and last['time_s']-r['time_s']>=minimum_gap_s]
    if not middle:return None
    midpoint=(first['time_s']+last['time_s'])/2
    center=min(middle,key=lambda r:(abs(r['time_s']-midpoint),-r['minimum_native_margin'],r['probe']))
    return [first,center,last]


def one(case):
    path=OUT/(case+'.json')
    if path.exists():return read(path)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('90s metadata-only time-diversity inventory cap')));signal.alarm(90)
    try:
        scan,node,mask,powers,means,model,entries,signed,signed_path=context_signed(case)
        from ds23_frequency_events import make_event_problem
        p=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,model,[])
        active=[(k,scan.tracks[i]) for k,(i,sl) in enumerate(zip(p.members,p.slices,strict=True)) if np.any(mask[sl])]
        document=read(SOURCE/case/'tracking.json');source=document.get('source',document);groups={}
        for lane in lanes(case):
            rx,ch,rf=lane['lane'];curves=[(k,t) for k,t in active if (t['receiver'],t['channel'])==(rx,ch) and abs(t['rf_hz']-rf)<=10]
            if len(curves)<2:continue
            by_probe={}
            for peak in lane['candidates']:
                if peak['margin']<.1:continue
                matches=[(k,t,m) for k,t in curves if (m:=matching_curve(t,peak['time_s'],peak['cfo_hz'])) is not None]
                if len(matches)==1:by_probe.setdefault(peak['probe'],[]).append((peak,*matches[0]))
            for probe,peaks in by_probe.items():
                for a,b in combinations(peaks,2):
                    if a[1]>b[1]:a,b=b,a
                    pa,ka,ta,ma=a;pb,kb,tb,mb=b
                    if ka==kb or p.rows[ka]['candidate_index']==p.rows[kb]['candidate_index']:continue
                    separation=abs((pa['cfo_hz']-pb['cfo_hz']+PERIOD/2)%PERIOD-PERIOD/2)
                    if separation<5000 or abs(pa['epoch']-pb['epoch'])/lane['sample_rate_hz']<2e-6:continue
                    meta=source['probes'][probe]
                    if source['probe_ms']!=20 or meta['probe_start_ms']!=0:continue
                    key=(rx,ch,rf,ka,kb)
                    groups.setdefault(key,[]).append(dict(case=case,probe=probe,time_s=pa['time_s'],lane=lane['lane'],
                        visit_index=meta['visit_index'],sample_counter=meta['valid_start_counter'],native_receiver_id=meta['receiver_id'],edge=meta['edge'],
                        first=pa,second=pb,first_lifted_value=pa['cfo_hz']+round((ma['polynomial_value_hz']-pa['cfo_hz'])/PERIOD)*PERIOD,
                        second_lifted_value=pb['cfo_hz']+round((mb['polynomial_value_hz']-pb['cfo_hz'])/PERIOD)*PERIOD,
                        curve_rows=[ka,kb],curve_components=[ta['key'],tb['key']],
                        proposed_norads=[p.rows[ka]['candidate_norad'],p.rows[kb]['candidate_norad']],
                        minimum_native_margin=min(pa['margin'],pb['margin'])))
        eligible=[];summaries=[];families={}
        for key,rows in groups.items():
            summaries.append(dict(curve_components=rows[0]['curve_components'],proposed_norads=rows[0]['proposed_norads'],
                probes=len({r['probe'] for r in rows}),span_s=max(r['time_s'] for r in rows)-min(r['time_s'] for r in rows)))
            for row in rows:
                canonical=dict(row)
                if row['proposed_norads'][0]>row['proposed_norads'][1]:
                    for field in ['curve_rows','curve_components','proposed_norads']:canonical[field]=row[field][::-1]
                    canonical['first'],canonical['second']=row['second'],row['first']
                    canonical['first_lifted_value'],canonical['second_lifted_value']=row['second_lifted_value'],row['first_lifted_value']
                family_key=tuple(canonical['lane'])+tuple(canonical['proposed_norads'])
                families.setdefault(family_key,[]).append(canonical)
            chosen=triplet(rows)
            if chosen:eligible.append(dict(curve_components=chosen[0]['curve_components'],proposed_norads=chosen[0]['proposed_norads'],
                native_probes=len({r['probe'] for r in rows}),span_s=chosen[-1]['time_s']-chosen[0]['time_s'],selected=chosen))
        family_proposals=[]
        for key,rows in families.items():
            chosen=triplet(rows)
            if chosen:family_proposals.append(dict(proposed_norads=chosen[0]['proposed_norads'],
                span_s=chosen[-1]['time_s']-chosen[0]['time_s'],selected=chosen,
                original_components_by_role=[sorted({r['curve_components'][k] for r in rows}) for k in [0,1]],
                original_fragment_constants_remain_distinct=True,not_qualified_for_shared_carrier_or_identity=True))
        result=dict(case=case,status='complete',groups_with_native_pairs=len(groups),long_baseline_groups=eligible,
            group_support=summaries,family_pair_long_baselines=family_proposals,
            signed_sha256=sha(signed_path),tracking_sha256=sha(SOURCE/case/'tracking.json'),
            no_IQ_GPS_or_following_TLE_or_position_error_used=True,
            unique_polynomial_ownership_is_not_independently_verified_identity=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    write(path,result);print(case,result['status'],len(result.get('long_baseline_groups',[])),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);cases=read(PARENT/'inventory_protocol.json')['cases']
    protocol=dict(cases=cases,native_margin=.1,alias_aware_separation_hz=5000.,code_epoch_separation_us=2.,
        minimum_span_s=20.,minimum_gap_s=5.,RF_samples_per_group=3,workers=6,per_case_seconds=90,
        no_top96_margin_truncation=True,no_new_IQ_or_GPS_or_future_TLE=True,
        source_sha256=sha(Path(__file__)))
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('time-diversity inventory protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,
        cases_with_long_baselines=sum(bool(r.get('long_baseline_groups')) for r in rows),
        long_baseline_groups=sum(len(r.get('long_baseline_groups',[])) for r in rows),
        family_pair_long_baselines=sum(len(r.get('family_pair_long_baselines',[])) for r in rows),
        family_baselines_do_not_establish_shared_fragment_biases_or_transmitter_identity=True,
        no_RF_precision_or_position_gain_claim=True))


if __name__=='__main__':main()
