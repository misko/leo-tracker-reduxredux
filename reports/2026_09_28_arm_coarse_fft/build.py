"""Build source-receipted host and Cortex-A9 FFT-bank microbenchmarks."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
CROSS=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc')
FFTW=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main(output,arm,sanitize):
    output.mkdir(parents=True,exist_ok=False);origin=HERE/'coarse_fft_bench.c'
    source=output/'coarse_fft_bench.c';shutil.copyfile(origin,source)
    compiler=str(CROSS) if arm else 'gcc'
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math']
    if arm: flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
    if sanitize: flags+=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    target=output/'coarse_fft_bench'
    command=[compiler,*flags,str(source),str(FFTW) if arm else '-lfftw3f','-lm','-o',str(target)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    receipt={'schema':'arm-coarse-fft-build/v1','arm':arm,'sanitize':sanitize,
      'fixture':'deterministic synthetic complex float, seed 0x67e21a95',
      'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
      'command':command,'source_sha256':{'coarse_fft_bench.c':sha(source)},
      'binary_sha256':{'coarse_fft_bench':sha(target)},
      'static_arm_fftw3f_sha256':sha(FFTW) if arm else None}
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true')
    a=p.parse_args();main(a.output.resolve(),a.arm,a.sanitize)
