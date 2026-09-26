"""Phase-blind support census for the bounded real multitrack experiment."""
import csv
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORT=HERE.parents[1]

def main():
    spec=importlib.util.spec_from_file_location('support_shared',REPORT/'dual-rx/run_shared_extractor.py')
    shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
    visits={int(r['visit_index']):r for r in csv.DictReader((REPORT/'acquisition/visit-inventory.csv').open())}
    admitted=shared._admitted(set(visits))
    groups=[]
    for i,pairs in admitted.items():
        v=visits[i]
        modes=[]
        for left,right,f in pairs:
            modes.append(dict(canonical_cfo_hz=f,rx0_epoch_sample=shared._epoch(left),rx1_epoch_sample=shared._epoch(right),
                relative_raw_cfo_hz=float(right['tracking_absolute_baseband_cfo_hz'])-float(left['tracking_absolute_baseband_cfo_hz']),
                minimum_margin=min(float(left['fractional_margin']),float(right['fractional_margin']))))
        groups.append(dict(visit_index=i,target_index=int(v['target_index']),channel=int(v['channel']),start_counter=int(v['valid_start_counter']),modes=modes))
    edges=[]
    for a,b in zip(groups,groups[1:]):
        if b['visit_index']==a['visit_index']+1:
            edges.append(dict(left=a['visit_index'],right=b['visit_index'],same_target=a['target_index']==b['target_index'],
                gap_samples=b['start_counter']-(a['start_counter']+1200000),
                phase_connection_established=False,emitter_association_established=False))
    payload=dict(schema='multitrack-support-audit/v1',total_visits=len(visits),multimode_visit_count=len(groups),
        policy='Prior phase-blind admission: RX pair epoch difference<=3samples, canonical CFO difference<=2kHz; keep modes separated>=10kHz canonical CFO. At most2 modes retained pervisit. Not an exhaustive emitter census.',
        groups=groups,consecutive_multimode_edges=edges,
        bounded_selection=[14,52,73,74,1074,1711,1734,1735],
        limits=['Existing 45 tracklets have summary metadata but no established joint electrical phase identity in this experiment.',
        'Same target/frequency does not prove same emitter across visits.',
        'Only simultaneous common-phase transfer is directly tested; retune continuity must be separately qualified.',
        'Baseline orientation79deg does not provide baseline length, candidate direction, or differential oscillator authority.'])
    (HERE/'support-audit.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps({'multimode_visits':len(groups),'consecutive_edges':edges},indent=2))

if __name__=='__main__':main()
