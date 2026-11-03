"""Rebuild frozen ungated detector recipe for x86 scalar control and system FFTW."""
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    root=Path(__file__).resolve().parents[1]
    recipe=root/'reports/2026_10_01_arm_glrt_missing_diagnosis/build.json'
    original=root/'reports/2026_10_01_arm_glrt_missing_diagnosis/ungated-build'
    out=Path('/var/tmp/leo-three-host-glrt-v2');(out/'objects').mkdir(parents=True)
    remove=('-mcpu=', '-mfpu=', '-mfloat-abi=', '-DLEO_PROPOSAL_NEON_FOLD',
            '-DLEO_NEON_CONDITIONED_MOMENTS=', '-DLEO_NATIVE_GLRT_CLI_AFFINITY=', '-DLEO_NATIVE_GLRT_BENCH_AFFINITY=')
    commands=[]
    for command in json.loads(recipe.read_text())['commands']:
        old=command['argv'];argv=['gcc-ar' if old[0].endswith('gcc-ar') else 'gcc']
        # The frozen scalar fallback leaves a NEON-only helper unreferenced.
        if argv[0] == 'gcc': argv.append('-Wno-error=unused-function')
        for arg in old[1:]:
            if arg.startswith(remove):continue
            arg=arg.replace(str(original),str(out))
            if arg=='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a':arg='-lfftw3f'
            if arg.endswith('/sysroot/usr/lib/libfftw3.so'):arg='-lfftw3'
            argv.append(arg)
        r=subprocess.run(argv,capture_output=True,text=True,timeout=180)
        commands.append({'argv':argv,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        (out/'build.json').write_text(json.dumps({'parent_recipe_sha256':hashlib.sha256(recipe.read_bytes()).hexdigest(),
            'scope':'Same frozen detector algorithm; scalar x86 and host FFTW replace ARM NEON/FFTW arithmetic',
            'commands':commands},indent=2)+'\n')
        r.check_returncode()
    print(out,flush=True)


if __name__=='__main__':main()
