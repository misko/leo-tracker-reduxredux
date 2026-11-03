"""CI16 scorer controls: zero, full-scale alternating and random, all rates."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def main():
    out=HERE/'controls-v3';out.mkdir(exist_ok=False)
    old=HERE.parent/'2026_09_29_arm_scoring_budget/run-v4'
    cmd=json.loads((old/'build-receipt.json').read_text())['command']
    cmd=[x for x in cmd if x not in ('-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-Werror')]
    cmd[0]='gcc';cmd[-1]=str(out/'reference')
    cmd=['-lfftw3f' if x.endswith('/libfftw3f.a') else x for x in cmd]
    compiled=subprocess.run(cmd,check=True,capture_output=True,text=True)
    (out/'compiler.stderr').write_text(compiled.stderr)
    oracle=json.loads((a.ORACLE/'oracle.json').read_text())
    ts={(c['context']['rate_hz'],c['context']['target']['edge']):c['templates'] for c in oracle['cases']}
    results=[]
    for rate in (2500000,5000000,7500000,10000000):
        n=round(rate/750);dwell=rate*120//1000
        for edge in ('lower','upper'):
            templates=ts[(rate,edge)]
            seeds=out/'seeds.txt'
            cfos=(-400000.,-200000.,0.,200000.,400000.,113636.363636,123.456,-123.456)
            seeds.write_text(''.join(f'{w} {rx} {k} {(0,n//2,n-1)[k%3]} {cfo:.17g}\n'
                for w in range(11) for rx in range(2) for k,cfo in enumerate(cfos)))
            for kind in ('zero','fullscale','random'):
                if kind=='zero':iq=np.zeros((dwell,4),dtype=np.int16)
                elif kind=='fullscale':iq=np.tile(np.array([-32768,32767,32767,-32768],dtype=np.int16),(dwell,1))
                else:iq=np.random.default_rng(731).integers(-32768,32768,(dwell,4),dtype=np.int16)
                data=out/'input.ci16';iq.tofile(data)
                args=[str(rate),str(a.ORACLE/templates['exact']['file']),str(a.ORACLE/templates['control']['file']),str(data),str(seeds)]
                sets=[]
                for binary,label in ((out/'reference','reference'),(HERE/'host704-v4/probe','candidate')):
                    raw=subprocess.check_output([str(binary),*args],text=True)
                    (out/f'{rate}-{edge}-{kind}-{label}.jsonl').write_text(raw)
                    sets.append([json.loads(x) for x in raw.splitlines()])
                assert len(sets[0])==len(sets[1])==176
                delta=0.;cfo_delta=0.
                for ref,new in zip(*sets):
                    assert (ref['window'],ref['rx'],ref['rank'])==(new['window'],new['rx'],new['rank'])
                    delta=max(delta,abs(ref['exact']-new['exact']),abs(ref['control']-new['control']))
                    cfo_delta=max(cfo_delta,abs(ref['tracking_cfo']-new['tracking_cfo']))
                    assert (ref['exact']-ref['control']>=.025)==(new['exact']-new['control']>=.025)
                assert delta<2e-9 and cfo_delta<2e-6
                results.append({'rate_hz':rate,'edge':edge,'kind':kind,'candidate_entries':176,
                                'max_score_delta':delta,'max_cfo_delta_hz':cfo_delta})
                print(rate,edge,kind,'pass',flush=True)
    data.unlink();seeds.unlink()
    (out/'summary.json').write_text(json.dumps({'complete':True,'reference_command':cmd,
        'candidate_binary_sha256':a.sha(HERE/'host704-v4/probe'),'reference_binary_sha256':a.sha(out/'reference'),
        'rows':results},indent=2)+'\n')

if __name__=='__main__':main()
