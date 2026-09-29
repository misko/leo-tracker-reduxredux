#!/usr/bin/env python3
"""Compare deterministic maximum-matching standard-hit identities."""
import importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
score_path=ROOT/'reports/2026_09_28_arm_sparse_proposal/score_cohort.py'
spec=importlib.util.spec_from_file_location('score_cohort',score_path);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);a=s.audit
BASE=ROOT/'reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
CONTROL=ROOT/'reports/2026_09_29_arm_wave6_combined/host704';TRACKED=HERE/'host704'
def matched_ids(folder):
    manifest=json.loads((folder/'manifest.json').read_text());selected=manifest['selected'];native=s.load_native(folder/'rows.jsonl',selected);baseline=a.load_baseline(BASE);result=set()
    for context in selected:
        case=(context['session_id'],context['visit_index'])
        for window in sorted(a.WINDOW_KEYS):
            refs=[(i,x) for i,x in enumerate(baseline[case][window]['candidates']) if x['margin']>=a.MARGIN_GATE]
            actual=[x for x in native[case][window]['candidates'] if x['margin']>=a.MARGIN_GATE];owner=[-1]*len(actual)
            adjacency=[[j for j,x in enumerate(actual) if abs(int(ref['epoch_sample'])-int(x['epoch']))<=a.EPOCH_TOLERANCE and abs(float(ref['tracking_cfo_hz'])-float(x['tracking_cfo_hz']))<=a.HIT_CFO_TOLERANCE_HZ] for _,ref in refs]
            def augment(i,seen):
                for j in adjacency[i]:
                    if j in seen:continue
                    seen.add(j)
                    if owner[j]<0 or augment(owner[j],seen):owner[j]=i;return True
                return False
            for i in range(len(refs)):augment(i,set())
            for i in owner:
                if i>=0:result.add((case[0],case[1],window[0],window[1],refs[i][0]))
    return result
control=matched_ids(CONTROL);tracked=matched_ids(TRACKED);lost=sorted(control-tracked);gained=sorted(tracked-control)
out={'schema':'arm-wave7-proposal-tracking-hit-identities/v1','identity':'session,visit,receiver,window,baseline_candidate_index under deterministic maximum matching','control_recovered':len(control),'tracked_recovered':len(tracked),'lost_count':len(lost),'gained_count':len(gained),'net':len(tracked)-len(control),'lost':[list(x) for x in lost],'gained':[list(x) for x in gained]}
(HERE/'host704-hit-identities.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ('control_recovered','tracked_recovered','lost_count','gained_count','net')}))
