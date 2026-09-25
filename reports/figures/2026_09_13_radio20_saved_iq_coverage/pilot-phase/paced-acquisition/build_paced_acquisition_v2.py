"""Build paced acquisition harness and execute bounded host signal/control runs."""
import json,subprocess,hashlib
from pathlib import Path
BASE=Path(__file__).parent;FW=Path('/home/mouse9911/gits/plutosdr-fw-radio20-tracking')
manifest=json.loads((BASE/'live-scan64-build-v1.json').read_text())
sources=[Path(p) for p in manifest['sources'] if not p.endswith('glrt_cpu_live_probe.c')]
sources.insert(0,BASE/'paced_acquisition_bench.c')
out=BASE/'paced-acquisition-host-v2-results';out.mkdir(exist_ok=False)
header=FW/'tests/starlink_glrt/iio_probe_fixture/iio.h'
(out/'iio.h').write_text(header.read_text()+'\nconst char *iio_device_get_id(const struct iio_device *);\nint iio_channel_attr_read_longlong(const struct iio_channel *,const char *,long long *);\n')
prefix=BASE.parent/'fftw-host-v1/install'
for arch,cc,flags in [('host','cc',['-I',str(out),'-I',str(prefix/'include'),'-L',str(prefix/'lib'),'-Wl,-rpath,'+str(prefix/'lib')]),('arm','/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc',['-mcpu=cortex-a9','-mfpu=neon'])]:
    subprocess.run([cc,'-O3','-std=c99','-Wall','-Wextra','-Werror','-pthread','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',*flags,*map(str,sources),'-lfftw3','-lm','-o',str(BASE/f'paced-acquisition-{arch}-v2.bin')],check=True)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=dict(new_rf_samples=0,sources={str(p):digest(p) for p in [*sources,FW/'tools/glrt_cpu_live_probe.c']},
    arm_sha256=digest(BASE/'paced-acquisition-arm-v2.bin'),runner_sha256=digest(Path(__file__)),cases=[])
for label,cut in [('positive',0),('positive',3),('control',0)]:
    directory=out/f'{label}-{cut}';directory.mkdir()
    iq=BASE/f'paced-original-seed-input-v1/{label}.ci16'
    run=subprocess.run([str(BASE/'paced-acquisition-host-v2.bin'),str(iq),str(BASE/'coarse-bank.ci16'),str(BASE/'direct-references.ci16'),str(cut),str(directory)],capture_output=True,check=True,timeout=10)
    assert not run.stderr
    (directory/'stdout.json').write_bytes(run.stdout)
    row=json.loads(run.stdout);result['cases'].append(dict(label=label,input_sha256=digest(iq),**row));print(result['cases'][-1],flush=True)
with (out/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
