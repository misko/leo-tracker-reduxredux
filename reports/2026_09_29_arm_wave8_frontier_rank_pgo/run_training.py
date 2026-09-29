"""Root-only serialized combined-PGO training and disjoint target evaluation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parent;REPORTS=ROOT.parent;REPO=REPORTS.parent
sys.path.insert(0,str(REPORTS/'2026_09_28_arm_full_optimization'))
import arm_cohort as a
PY=str(REPO/'.venv/bin/python')

def run(cmd):subprocess.run(cmd,cwd=REPO,check=True)
def evaluate(mode,reference,output):
    build=ROOT/'builds'/mode
    run([PY,str(ROOT/'evaluate.py'),
         '--binary',str(build/'fused_wave8_frontier_rank_pgo_arm'),
         '--receipt',str(build/'build-receipt.json'),'--reference',str(reference),
         '--output','../'+ROOT.name+'/'+output,
         '--features',str(REPORTS/'2026_09_29_arm_proposal_features/host704-omit-power-v1/rows.jsonl'),
         '--radius','1','--allow-proposal-changes','--arm'])

def main():
    profile=Path('/var/tmp/leo-wave8-frontier-rank-pgo-profile')
    if profile.exists():raise RuntimeError('Refusing to overwrite existing profiles')
    a.remote('mkdir '+str(profile))
    evaluate('generate',REPORTS/'2026_09_29_arm_wave5_final/arm4-v2','training4')
    run([*a.SSH_BASE,'scp','-r','-O',*a.SSH_OPTIONS,a.TARGET+':'+str(profile),str(profile.parent)])
    run(['sudo','-n','chown','-R',f'{os.getuid()}:{os.getgid()}',str(profile)])
    files=sorted(profile.glob('*.gcda'))
    assert {p.name for p in files}=={'proposal_core.gcda','proposal_tracking.gcda','conditioned_czt.gcda','fft_full.gcda','fused_probe.gcda'}
    with tarfile.open(ROOT/'profile-data.tar.gz','w:gz') as archive:
        for p in files:archive.add(p,arcname=p.name)
    (ROOT/'profile-retrieval.json').write_text(json.dumps({
        'training_only':True,'profile_files':{p.name:a.sha(p) for p in files},
        'training_manifest_sha256':a.sha(ROOT/'training4/manifest.json'),
        'archive_sha256':a.sha(ROOT/'profile-data.tar.gz')},indent=2)+'\n')
    run([PY,str(ROOT/'build_pgo.py'),'use'])
    results=[]
    for unit in sorted((ROOT/'builds/use').glob('test_*_arm')):
        dest='/tmp/wave8-frontier-rank-pgo-'+unit.name;a.upload(unit,dest)
        stdout=a.remote('chmod +x '+dest+' && '+dest,timeout=120)
        results.append({'binary':unit.name,'sha256':a.sha(unit),'stdout':stdout})
    (ROOT/'arm-units-use.json').write_text(json.dumps(results,indent=2)+'\n')
    evaluate('use',REPORTS/'2026_09_29_arm_wave6_pgo/heldout32-reference','arm-heldout32')
    run([PY,str(REPORTS/'2026_09_29_arm_rate_coarse_gate/audit.py'),'--cohort',str(ROOT/'arm-heldout32')])

if __name__=='__main__':main()
