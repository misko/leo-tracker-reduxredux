"""Report capture contention separately from original-D numerical qualification."""
import argparse
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'concurrent'))
from summarize import summarize_phase

def summarize_candidate_phase(phase, candidate, here=HERE):
    reference=here/'persistent/references'/candidate
    qualification=json.loads((reference/'qualification.json').read_text())
    if qualification.get('candidate')!=candidate or not qualification.get('original_D_scientific_gate_passed'):
        raise ValueError('reference qualification')
    summary=summarize_phase(phase,reference)
    if summary.get('run',{}).get('candidate')!=candidate:raise ValueError('wrong phase candidate')
    if not summary.get('validity',{}).get('passed'):raise RuntimeError('invalid phase')
    cores=summary.get('cpu',{}).get('capture_overlap',{}).get('cores')
    if not isinstance(cores,dict) or '0' not in cores:raise ValueError('capture overlap CPU0')
    busy={}
    for core,ticks in cores.items():
        if not isinstance(ticks,dict):raise ValueError('CPU ticks')
        total=sum(v for k,v in ticks.items() if k not in ('guest','guest_nice'))
        if total<=0 or any(k not in ticks for k in ('idle','iowait')):raise ValueError('CPU ticks')
        busy[core]=100*(total-ticks['idle']-ticks['iowait'])/total
    result={'scientific_reference':qualification,'phase_validity':summary['validity'],
        'capture_overlap_busy_percent':busy,'cpu0_headroom_percent':100-busy['0'],
        'at_least_40_percent_headroom':busy['0']<=60,
        'candidate_repeatability':summary['glrt']['parity'],
        'capture_overlap':summary['glrt']['capture_overlap']}
    (phase/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (phase/'qualification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',type=Path);p.add_argument('--candidate',required=True);a=p.parse_args()
    print(json.dumps(summarize_candidate_phase(a.phase,a.candidate),indent=2))

if __name__=='__main__':main()
