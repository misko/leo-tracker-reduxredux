"""Find unused opposite-RX curved evidence from frozen unique native pairs.

Group on the current curved family rather than a particular graph fragment.
Every new fragment must independently exhibit curvature in native CFO values.
No linear partner or duplicate active winner enters calibration.
"""

from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from ds23_frame_registration import wrap,PERIOD
from ds23_frame_peak_recovery import polynomial_screen,measurement_id
from ds23_frequency_events import make_event_problem
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_cross_RX_curves_v2'
SOURCE=ROOT/'reports/2026_10_21_ds23_reception_anchor_ratio/evaluation.json'
TRACKING=ROOT/'reports/2026_10_19_algo02_ds23_full'
BULK=Path('/srv/bulk/leo/research/ds23-cross-RX-curves-v2-20261021')


def identify_peak(case,rx,row,peak,original,occupied):
    if original is not None:
        separation=abs(float(wrap(peak['cfo']-original['measured_cfo_hz'])))
        if separation<=1.:
            if original['observation_id'] in occupied:return None,'already_active'
            return original['observation_id'],'unretained_original'
        if separation<1500.:return None,'unresolved_neighboring_peak'
    return measurement_id(case,rx,row['channel'],row['rf_hz'],row['time_s'],peak),'additional_native_peak'


def native_fragments(rows,sigma_hz):
    rows=sorted(rows,key=lambda r:r['time_s'])
    times=np.array([r['time_s'] for r in rows]);values=np.array([r['native_CFO_hz'] for r in rows])
    fragments=[]
    for ix in np.split(np.arange(len(rows)),np.flatnonzero(np.diff(times)>10.)+1):
        if not len(ix):continue
        t=times[ix];y=np.unwrap(values[ix]*2*np.pi/PERIOD)*PERIOD/(2*np.pi)
        evidence=polynomial_screen(t,y,np.full(len(t),sigma_hz))
        if evidence is not None:fragments.append(dict(points=[dict(rows[i],value=float(v)) for i,v in zip(ix,y,strict=True)],curvature=evidence))
    return fragments


def one(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
    p=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,hyper,[])
    occupied={o for i,sl in zip(p.members,p.slices,strict=True) for o,use in zip(scan.tracks[i]['observation_ids'],mask[sl],strict=True) if use}
    occupied.update(o for e in entries for o in e['observation_ids'])
    observations=read(TRACKING/case/'observations.json')
    lookup={(o['receiver'],round(o['time_s'],6),o['channel'],o['actual_rf_hz']):o for o in observations}
    frequencies=defaultdict(set)
    for o in observations:frequencies[round(o['time_s'],6),o['channel']].add(o['actual_rf_hz'])
    rf=next(r for r in read(SOURCE)['rows'] if r['case']==case);proposals=[];rejected=Counter()
    for row in rf['paired_points']:
        if row['candidate_index'] not in p.supported:rejected['family_would_instantiate_new_orbit_modes']+=1;continue
        available=frequencies[round(row['time_s'],6),row['channel']]
        if len(available)!=1:raise ValueError('native anchor timestamp/channel has ambiguous RF identity')
        row=dict(row,rf_hz=next(iter(available)))
        for rx,peak in enumerate(row['native_peaks'],1):
            key=(rx,round(row['time_s'],6),row['channel'],row['rf_hz'])
            oid,kind=identify_peak(case,rx,row,peak,lookup.get(key),occupied)
            if oid is None:rejected[kind]+=1;continue
            proposals.append(dict(observation_id=oid,kind=kind,receiver=rx,channel=row['channel'],rf_hz=row['rf_hz'],time_s=row['time_s'],
                native_CFO_hz=peak['cfo'],native_peak=peak,candidate_index=row['candidate_index'],norad=row['norad']))
    owners=defaultdict(set)
    for r in proposals:owners[r['observation_id']].add(r['candidate_index'])
    unique={r['observation_id']:r for r in proposals if len(owners[r['observation_id']])==1}
    groups=defaultdict(list)
    for r in unique.values():groups[r['candidate_index'],r['receiver'],r['channel'],r['rf_hz']].append(r)
    fragments=[]
    for key,rows in sorted(groups.items()):
        fragments.extend(dict(f,group=key,sigma_hz=max(150.,scan.radio_sigma_hz)) for f in native_fragments(rows,max(150.,scan.radio_sigma_hz)))
    result=dict(case=case,status='complete',fragments=fragments,rejected=dict(rejected),unused_native_points=len(unique),
        qualifying_curved_points=sum(len(f['points']) for f in fragments),
        qualifying_original_points=sum(r['kind']=='unretained_original' for f in fragments for r in f['points']),
        source_pairs_sha256=sha(SOURCE),signed_incumbent_sha256=sha(binding),original_occupied_ids=sorted(occupied),
        source_pair_labels_are_existing_curved_anchor_nominations_not_independent_satellite_proof=True,
        no_new_orbit_shape_support_or_linear_calibration=True,no_GPS_or_new_RF_collection=True)
    write(target,result);print(case,len(fragments),result['qualifying_curved_points'],flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    cases=sorted(r['case'] for r in read(SOURCE)['rows'] if r['status']=='complete')
    protocol=dict(cases=cases,workers=6,source_pairs_sha256=sha(SOURCE),
        native_pair_selection='unique80ns epoch /750Hz curved-only calibrated CFO match from frozen reception inventory',
        grouping='same existing supported curved family, receiver, channel and RF; split gaps>10s',
        unused_canonical_winner_match_hz=1.,minimum_distinct_secondary_peak_separation_hz=1500.,
        minimum_points=8,minimum_span_s=20.,linear_RMS_hz=250.,curvature_BIC_gain=10.,maximum_order=4,
        sigma_floor_hz=150.,independent_native_curvature_required=True,
        no_new_satellite_label_or_orbit_shape_prior_or_new_RF_or_GPS=True,
        source_sha256=sha(Path(__file__)))
    path=OUT/'inventory_protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('cross RX curved inventory changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    write(OUT/'inventory.json',dict(rows=rows,all_terminal=True,cases=len(rows),offering_cases=sum(bool(r['fragments']) for r in rows),
        qualifying_curved_points=sum(r['qualifying_curved_points'] for r in rows),
        qualifying_original_points=sum(r['qualifying_original_points'] for r in rows),
        no_new_localization_estimate_or_gain_established=True))


if __name__=='__main__':main()
