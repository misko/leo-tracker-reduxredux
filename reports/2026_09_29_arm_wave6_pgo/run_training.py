"""Root-owned serial target training, profile retrieval, and held-out PGO check."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT.parent
REPO = REPORTS.parent
sys.path.insert(0, str(REPORTS/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def run(command):
    subprocess.run(command, cwd=REPO, check=True)

def evaluate(mode, reference, output):
    build = ROOT/'builds'/mode
    run([str(REPO/'.venv/bin/python'), str(REPORTS/'2026_09_29_arm_fused_pipeline/evaluate.py'),
         '--binary', str(build/'fused_rate_coarse_gate_arm'),
         '--receipt', str(build/'build-receipt.json'), '--reference', str(reference),
         '--output', '../2026_09_29_arm_wave6_pgo/'+output,
         '--features', str(REPORTS/'2026_09_29_arm_proposal_features/host704-omit-power-v1/rows.jsonl'),
         '--radius', '2', '--arm'])

def main():
    # The root hardware queue has exactly one predecessor. Fail rather than
    # overlap it if its completion receipt does not arrive within this bound.
    predecessor = REPORTS/'2026_09_29_arm_wave6_combined/arm152/manifest.json'
    deadline = time.monotonic()+1200
    while not json.loads(predecessor.read_text()).get('complete'):
        if time.monotonic()>deadline: raise RuntimeError('ARM predecessor incomplete')
        time.sleep(5)
    profile = Path('/var/tmp/leo-wave6-pgo-profile-v2')
    if profile.exists(): raise RuntimeError('Refusing to overwrite existing host profiles')
    a.remote('mkdir /var/tmp/leo-wave6-pgo-profile-v2')
    evaluate('generate-v2', REPORTS/'2026_09_29_arm_wave5_final/arm4-v2', 'training4-v2')
    subprocess.run([*a.SSH_BASE,'scp','-r','-O',*a.SSH_OPTIONS,
                    a.TARGET+':'+str(profile), str(profile.parent)],check=True,timeout=60)
    # The deployment helper uses sudo scp; restored root-only profile modes
    # must be made readable by the local compiler user before enumeration.
    subprocess.run(['sudo','-n','chown','-R',f'{os.getuid()}:{os.getgid()}',str(profile)],check=True)
    paths=sorted(profile.rglob('*.gcda'))
    assert {p.name for p in paths}=={'proposal_core.gcda','conditioned_czt.gcda','fft_full.gcda','fused_probe.gcda'}
    receipt={'training_only':True,'profile_files':{str(p.relative_to(profile)):a.sha(p) for p in paths},
             'training_manifest_sha256':a.sha(ROOT/'training4-v2/manifest.json')}
    (ROOT/'profile-retrieval-v2.json').write_text(json.dumps(receipt,indent=2)+'\n')
    run([str(REPO/'.venv/bin/python'),str(ROOT/'build_pgo_v2.py'),'use'])
    unit_results=[]
    for unit in sorted((ROOT/'builds/use-v2').glob('test_*_arm')):
        dest='/tmp/wave6-pgo-'+unit.name;a.upload(unit,dest)
        stdout=a.remote('chmod +x '+dest+' && '+dest,timeout=120)
        unit_results.append({'binary':unit.name,'sha256':a.sha(unit),'stdout':stdout})
    (ROOT/'arm-units-use-v2.json').write_text(json.dumps(unit_results,indent=2)+'\n')
    evaluate('use-v2',ROOT/'heldout32-reference','arm-heldout32-v2')
    run([str(REPO/'.venv/bin/python'),str(REPORTS/'2026_09_29_arm_rate_coarse_gate/audit.py'),
         '--cohort',str(ROOT/'arm-heldout32-v2')])

if __name__=='__main__':main()
