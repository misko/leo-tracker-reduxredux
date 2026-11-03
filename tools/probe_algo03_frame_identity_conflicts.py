"""Audit simultaneous native GLRT epochs against old/new family hypotheses.

No CFO, epoch or polynomial is fitted here. Labels only stratify existing
winning radio measurements; evaluation coordinates are never read.
"""

from collections import defaultdict
from pathlib import Path
import numpy as np

from ds23_frame_registration import wrap,PERIOD
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full/DS23-0268'
PARENT=ROOT/'reports/2026_10_20_algo03_feasible_hybrids'
OUT=ROOT/'reports/2026_10_20_algo03_frame_identity_conflicts'


def main():
    if OUT.exists():raise FileExistsError('preserve frame-identity audit')
    OUT.mkdir();document=read(SOURCE/'tracking.json');source=document.get('source',document)
    fs=source['sample_rate_hz'];anchor=document['clock_anchor']['sample_counter'] if 'clock_anchor' in document else source['timing']['session_start_device_sample_counter']
    observations=read(SOURCE/'observations.json');old=read(SOURCE/'algo02_result.json');base=read(SOURCE/'result.json')['final_node']
    chosen=read(PARENT/'execution.json')['best_qualified_trial'];new=read(PARENT/f"trial_{chosen['index']:02d}.json")
    ownership={}
    newlabels={r['component']:r['candidate_norad'] for r in new['node']['seed']['rows']}
    for row in old['policy_arms']['c0']['gates']['tracks']:
        for oid in row['observation_ids']:
            ownership[oid]=dict(component=row['component'],old_norad=row['norad'],new_norad=newlabels[row['component']])
    bytime={(o['receiver']-1,round(o['time_s']*fs)):o for o in observations}
    probes={(p['visit_index'],p['receiver_id']):p for p in source['probes']};rows=[]
    for (visit,rx),a in probes.items():
        if rx!=0:continue
        b=probes.get((visit,1))
        if b is None or (a['valid_start_counter'],a['channel'],a['actual_rf_hz'])!=(b['valid_start_counter'],b['channel'],b['actual_rf_hz']):continue
        time_s=(a['valid_start_counter']-anchor)/fs+.01
        oa,ob=bytime.get((0,round(time_s*fs))),bytime.get((1,round(time_s*fs)))
        if oa is None or ob is None or oa['observation_id'] not in ownership or ob['observation_id'] not in ownership:continue
        winners=[]
        for probe,observation in ((a,oa),(b,ob)):
            passing=[c for c in probe['candidates'] if c['passed_fractional_margin_gate']]
            winner=max(passing,key=lambda c:(c['fractional_margin'],-c['candidate_rank']),default=None)
            if winner is None or abs(wrap(winner['fractional_tracking_cfo_hz']-observation['measured_cfo_hz']))>1:
                winners=[];break
            winners.append(winner)
        if not winners:continue
        epochs=[p['integer_epoch_sample']+p['fractional_epoch_offset_samples'] for p in winners]
        difference=float(wrap(epochs[1]-epochs[0],fs/750)/fs)
        first,second=ownership[oa['observation_id']],ownership[ob['observation_id']]
        rows.append(dict(visit=visit,time_s=time_s,channel=a['channel'],band=int(a['channel']>4),
            rf_hz=a['actual_rf_hz'],first=first,second=second,epoch_difference_s=difference,
            original_same_family=first['old_norad']==second['old_norad'],
            new_same_family=first['new_norad']==second['new_norad'],
            distinct_observation_ids=[oa['observation_id'],ob['observation_id']]))
    groups={}
    for kind in ('original_same_family','new_same_family'):
        for band in (0,1):
            selected=[r for r in rows if r[kind] and r['band']==band]
            diff=np.array([r['epoch_difference_s'] for r in selected])
            groups[f'{kind}_band{band}']=dict(count=len(diff),median_epoch_difference_ns=float(np.median(diff)*1e9) if len(diff) else None,
                within80ns_of_zero=int(np.sum(abs(diff)<=80e-9)),within800ns_of_zero=int(np.sum(abs(diff)<=800e-9)))
    write(OUT/'results.json',dict(case='DS23-0268',rows=rows,summary=groups,
        original_winning_measurements_replayed_modulo_alias=True,
        same_exact_RF_and_simultaneous_hardware_sample_support=True,
        unknown_RX_group_delay_and_epoch_ambiguities_not_calibrated=True,
        no_GPS_TLE_fit_position_fit_or_new_RF_input=True,
        source_sha256=sha(Path(__file__)),tracking_sha256=sha(SOURCE/'tracking.json'),
        selected_hypothesis_sha256=sha(PARENT/f"trial_{chosen['index']:02d}.json")))
    print(groups)


if __name__=='__main__':main()
