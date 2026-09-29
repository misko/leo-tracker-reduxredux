#!/usr/bin/env python3
"""Compare gated-quadratic matched reference-hit identities with the .312 gate."""
import importlib.util,json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent/'2026_09_29_arm_rate_gate_transfer'
spec=importlib.util.spec_from_file_location('transfer_audit',ROOT/'audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
mspec=importlib.util.spec_from_file_location('matcher',audit.MATCHER)
matcher=importlib.util.module_from_spec(mspec);mspec.loader.exec_module(matcher)


def matched_indices(reference,actual):
    indexed=[(i,x) for i,x in enumerate(reference) if x['margin']>=matcher.MARGIN_GATE]
    native=[x for x in actual if x['margin']>=matcher.MARGIN_GATE]
    adjacency=[[j for j,a in enumerate(native)
        if abs(int(e['epoch_sample'])-int(a['epoch']))<=matcher.EPOCH_TOLERANCE
        and abs(float(e['tracking_cfo_hz'])-float(a['tracking_cfo_hz']))<=matcher.HIT_CFO_TOLERANCE_HZ]
        for _,e in indexed]
    owner=[-1]*len(native)
    def augment(i,seen):
        for j in adjacency[i]:
            if j in seen:continue
            seen.add(j)
            if owner[j]<0 or augment(owner[j],seen):owner[j]=i;return True
        return False
    for i in range(len(indexed)):augment(i,set())
    return {indexed[i][0] for i in owner if i>=0}


def compare(dataset):
    control=ROOT/f'host-{dataset}-gate-312';candidate=ROOT/f'host-{dataset}-gate-quadratic'
    manifest=json.loads((candidate/'manifest.json').read_text())
    baseline=matcher.load_baseline(audit.BASELINE)
    left=audit.load_gated(control/'rows.jsonl',matcher.WINDOW_KEYS)
    right=audit.load_gated(candidate/'rows.jsonl',matcher.WINDOW_KEYS)
    sets=[];details={}
    for native in (left,right):
        found=set()
        for context in manifest['selected']:
            case=(context['session_id'],context['visit_index']);rate=context['rate_hz']
            for window in sorted(matcher.WINDOW_KEYS):
                reference=baseline[case][window]['candidates']
                for index in matched_indices(reference,native[case][window]['candidates']):
                    identity=(case[0],case[1],window[0],window[1],index);found.add(identity)
                    details[identity]={'rate_hz':rate,'session_id':case[0],'visit_index':case[1],
                        'receiver_id':window[0],'probe_index':window[1],'reference_candidate_rank':index,
                        'epoch_sample':reference[index]['epoch_sample'],
                        'tracking_cfo_hz':reference[index]['tracking_cfo_hz'],'margin':reference[index]['margin']}
        sets.append(found)
    lost=sorted(sets[0]-sets[1]);gained=sorted(sets[1]-sets[0])
    result={'schema':'arm-rate-gate-transfer-quadratic-hit-diff/v1','dataset':dataset.upper(),
        'control_matched':len(sets[0]),'candidate_matched':len(sets[1]),
        'lost_count':len(lost),'gained_count':len(gained),
        'lost_by_rate':dict(sorted(Counter(str(details[x]['rate_hz']) for x in lost).items())),
        'gained_by_rate':dict(sorted(Counter(str(details[x]['rate_hz']) for x in gained).items())),
        'lost':[details[x] for x in lost],'gained':[details[x] for x in gained]}
    (candidate/'hit-identity-diff-vs-gate-312.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    compare('ds8');compare('ds9')
