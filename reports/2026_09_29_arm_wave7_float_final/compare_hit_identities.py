#!/usr/bin/env python3
"""Compare deterministically matched sealed-reference hit identities."""
import argparse,hashlib,importlib.util,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPORTS=ROOT.parent
gate_path=REPORTS/'2026_09_29_arm_rate_coarse_gate'/'audit_312.py'
spec=importlib.util.spec_from_file_location('gate_audit',gate_path)
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
frozen=gate.frozen

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def matched_indices(reference,actual):
    indexed=[(i,item) for i,item in enumerate(reference) if item['margin']>=frozen.MARGIN_GATE]
    native=[item for item in actual if item['margin']>=frozen.MARGIN_GATE]
    adjacency=[[j for j,a in enumerate(native)
        if abs(int(e['epoch_sample'])-int(a['epoch']))<=frozen.EPOCH_TOLERANCE
        and abs(float(e['tracking_cfo_hz'])-float(a['tracking_cfo_hz']))<=frozen.HIT_CFO_TOLERANCE_HZ]
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate',default='host704')
    parser.add_argument('--output',default='hit-identity-diff.json')
    args=parser.parse_args()
    control=REPORTS/'2026_09_29_arm_wave5_final'/'host704-v2'
    candidate=ROOT/args.candidate
    manifest=json.loads((candidate/'manifest.json').read_text())
    baseline_path=REPORTS/'2026_09_28_ds7_large_arm'/'baseline-01'/'rows.jsonl'
    baseline=frozen.load_baseline(baseline_path)
    left=gate.load_gated(control/'rows.jsonl');right=gate.load_gated(candidate/'rows.jsonl')
    control_hits=set();candidate_hits=set();details={}
    for context in manifest['selected']:
        case=(context['session_id'],context['visit_index'])
        for window in sorted(frozen.WINDOW_KEYS):
            reference=baseline[case][window]['candidates']
            prefix=(context['session_id'],context['visit_index'],window[0],window[1])
            for label,native,target in [('control',left,control_hits),('candidate',right,candidate_hits)]:
                indices=matched_indices(reference,native[case][window]['candidates'])
                for index in indices:
                    identity=prefix+(index,);target.add(identity)
                    details[identity]={'session_id':identity[0],'visit_index':identity[1],
                        'receiver_id':identity[2],'probe_index':identity[3],
                        'reference_candidate_rank':index,'epoch_sample':reference[index]['epoch_sample'],
                        'tracking_cfo_hz':reference[index]['tracking_cfo_hz'],'margin':reference[index]['margin']}
    lost=sorted(control_hits-candidate_hits);gained=sorted(candidate_hits-control_hits)
    result={'schema':'arm-wave7-float-final-hit-diff/v1','candidate':args.candidate,
        'control_matched':len(control_hits),
        'candidate_matched':len(candidate_hits),'lost_count':len(lost),'gained_count':len(gained),
        'lost':[details[x] for x in lost],'gained':[details[x] for x in gained],
        'input_sha256':{'baseline_rows':sha(baseline_path),
            'control_rows':sha(control/'rows.jsonl'),'candidate_rows':sha(candidate/'rows.jsonl'),
            'candidate_manifest':sha(candidate/'manifest.json')}}
    (ROOT/args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
