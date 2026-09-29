"""Root-only serial CPU0 evaluation of compiler variants; no RF operations."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT.parent
sys.path.insert(0, str(REPORTS/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def run():
    cases = [
        (ROOT/'builds-thumb', ROOT/'arm4-thumb'),
        (ROOT/'builds-o2', ROOT/'arm4-o2'),
        (REPORTS/'2026_09_29_arm_wave7_compile_review/builds-restrict/arm',
         REPORTS/'2026_09_29_arm_wave7_compile_review/arm4-restrict'),
    ]
    for build, output in cases:
        if output.exists():
            raise RuntimeError(f'Refusing to overwrite {output}')
        units = []
        for unit in sorted(build.glob('test_*_arm')):
            dest = '/tmp/wave7-codegen-'+unit.name
            a.upload(unit, dest)
            stdout = a.remote('chmod +x '+dest+' && '+dest, timeout=120)
            units.append({'binary': unit.name, 'sha256': a.sha(unit), 'stdout': stdout})
        (output.parent/(output.name+'-units.json')).write_text(json.dumps(units, indent=2)+'\n')
        binaries = [p for p in build.glob('fused_*_arm') if p.is_file()]
        assert len(binaries) == 1
        subprocess.run([sys.executable, str(REPORTS/'2026_09_29_arm_fused_pipeline/evaluate.py'),
            '--binary', str(binaries[0]), '--receipt', str(build/'build-receipt.json'),
            '--reference', str(REPORTS/'2026_09_29_arm_wave7_rank_histograms/arm4-v2'),
            '--output', '../'+str(output.relative_to(REPORTS)),
            '--features', str(REPORTS/'2026_09_29_arm_proposal_features/host704-omit-power-v1/rows.jsonl'),
            '--radius', '2', '--arm'], check=True)
        subprocess.run([sys.executable, str(REPORTS/'2026_09_29_arm_rate_coarse_gate/audit.py'),
            '--cohort', str(output)], check=True)

if __name__ == '__main__':
    run()
