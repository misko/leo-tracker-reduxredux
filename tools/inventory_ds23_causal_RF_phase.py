"""Inventory earlier RF observations of identical causal satellite elements.

No positions or geographic truth are read. This is preparation for a separate
sequential variant with independent scan positions, not a stationary-site fit.
"""

from collections import defaultdict
from pathlib import Path
import hashlib
import numpy as np
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_causal_RF_phase'


def main():
    OUT.mkdir(exist_ok=True)
    source=ROOT/'reports/2026_10_20_ds23_combined_recovery_full/protocol.json'
    roots=read(source)['input_roots'];scans=[]
    for case,root in sorted(roots.items()):
        directory=Path(root)/case;receipt=read(Path(root)/'causal_prior'/case/'receipt.json')
        original=read(directory/'result.json');saved=read(directory/'algo02_result.json')
        mask=np.asarray(saved['mask'],bool);tracks={r['key']:r for r in read(directory/'tracks.json')}
        elements=read(directory/'nominal_elements.json');offset=0;families=defaultdict(lambda:dict(points=0,channels=set(),receivers=set()))
        for row in original['final_node']['seed']['rows']:
            if not row['active_curvature']:continue
            t=tracks[row['component']];n=len(t['times']);active=int(mask[offset:offset+n].sum());offset+=n
            if not active:continue
            number=int(row['candidate_norad']);element=elements[str(number)]
            if max(element['provenance']['element_epoch_utc_ns'],element['provenance']['collected_utc_ns'])>receipt['cutoff_utc_ns']:
                raise ValueError('post-scan elements in RF phase inventory')
            record=families[number];record['points']+=active;record['channels'].add(t['channel']);record['receivers'].add(t['receiver'])
            record['TLE_sha256']=hashlib.sha256('\n'.join(element['lines']).encode()).hexdigest()
        if offset!=len(mask):raise ValueError('original curved mask length differs from inventory track rows')
        support={str(n):dict(r,channels=sorted(r['channels']),receivers=sorted(r['receivers'])) for n,r in families.items() if r['points']>=24 and len(r['channels'])>=2}
        end=receipt['origin_utc_ns']+int(max(max(t['times']) for t in tracks.values())*1e9)
        scans.append(dict(case=case,origin_utc_ns=receipt['origin_utc_ns'],cutoff_utc_ns=receipt['cutoff_utc_ns'],
            RF_observations_end_utc_ns=end,supported_families=support,
            result_sha256=sha(directory/'result.json'),algo02_result_sha256=sha(directory/'algo02_result.json'),
            nominal_elements_sha256=sha(directory/'nominal_elements.json')))
    scans.sort(key=lambda r:r['origin_utc_ns']);pairs=[]
    for k,target in enumerate(scans):
        candidates=[]
        for previous in reversed(scans[:k]):
            age=(target['origin_utc_ns']-previous['origin_utc_ns'])/1e9
            if age>1800:break
            if previous['RF_observations_end_utc_ns']>=target['cutoff_utc_ns']:continue
            shared=[]
            for n,row in target['supported_families'].items():
                old=previous['supported_families'].get(n)
                if old and old['TLE_sha256']==row['TLE_sha256']:
                    shared.append(dict(norad=int(n),TLE_sha256=row['TLE_sha256'],previous_points=old['points'],target_points=row['points']))
            if len(shared)>=2:candidates.append(dict(previous_case=previous['case'],target_case=target['case'],age_s=age,
                shared=shared,score=sum(min(r['previous_points'],r['target_points']) for r in shared)))
        if candidates:pairs.append(max(candidates,key=lambda r:(len(r['shared']),r['score'],-r['age_s'])))
    protocol=dict(source_protocol_sha256=sha(source),minimum_curved_points_per_family=24,minimum_distinct_channels=2,
        minimum_shared_families=2,maximum_start_gap_s=1800,previous_RF_must_end_before_target_cutoff=True,
        require_identical_TLE_lines_and_causal_provenance=True,
        pair_selection='maximum shared family count, then shared original point support, then nearest earlier scan',
        geographic_positions_and_errors_not_read=True,stationarity_not_assumed=True,
        sequential_RF_history_variant_not_single_scan_algorithm=True,source_sha256=sha(Path(__file__)))
    write(OUT/'inventory_protocol.json',protocol)
    write(OUT/'inventory.json',dict(scans=scans,pairs=pairs,available_scans=len(scans),targets_with_eligible_previous_RF=len(pairs),
        prior_RF_scans_not_new_RF_collection=True,no_position_algorithm_or_gain_established=True))
    print(dict(available=len(scans),eligible_targets=len(pairs),shared_family_counts=[len(r['shared']) for r in pairs[:20]]),flush=True)


if __name__=='__main__':main()
