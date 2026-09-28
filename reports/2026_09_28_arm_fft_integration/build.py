"""Build source-receipted host or ARM FFT coarse integration executables."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
HOST=Path("/var/tmp/leo-host-conditioned-czt-v2")
ARM=Path("/var/tmp/leo-arm-conditioned-czt-v3")
CROSS=Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def build(out:Path,arm:bool,sanitize:bool)->None:
    out.mkdir(parents=True,exist_ok=False)
    origin=ARM if arm else HOST
    shutil.copytree(origin/"src",out/"src")
    names=("full_search.c","full_search.h","conditioned_czt.c","conditioned_czt.h",
           "fft_full.c","probe_main.c","cohort_probe.c","coarse_fft_proposal.h",
           "test_fft_integration.c")
    for name in names:shutil.copyfile(HERE/name,out/name)
    cc=str(CROSS) if arm else "gcc"
    flags=["-DLEO_PRESENCE_FFTW=1","-std=c11","-O3","-Wall","-Wextra","-Werror",
           "-fno-fast-math","-DLEO_PRESENCE_COARSE_FP32","-DLEO_FULL_CONDITIONED_SCREEN"]
    if arm:flags += ["-mcpu=cortex-a9","-mfpu=neon","-mfloat-abi=hard","-DLEO_FULL_ARM_AFFINITY"]
    if sanitize:
        if arm:raise ValueError("sanitizers are host-only")
        flags += ["-O1","-g","-fsanitize=address,undefined","-fno-omit-frame-pointer"]
    common=[cc,*flags,"-I",str(out/"src/native_presence"),"-I",str(out),str(out/"full_search.c"),str(out/"conditioned_czt.c")]
    commands=[]
    for main,target in (("probe_main.c","probe"),("cohort_probe.c","cohort"),("test_fft_integration.c","test_fft_integration")):
        fftlibs=(["/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a","-lfftw3"] if arm else ["-lfftw3","-lfftw3f"])
        cmd=[*common,str(out/main),str(out/"fft_full.c"),*fftlibs,"-lm","-o",str(out/target)]
        subprocess.run(cmd,check=True);commands.append(cmd)
    if not arm:subprocess.run([str(out/"test_fft_integration")],check=True)
    receipt={"schema":"arm-fft-coarse-integration-build/v1","arm":arm,"sanitize":sanitize,
      "baseline":str(origin),"compiler":subprocess.check_output([cc,"--version"],text=True).splitlines()[0],
      "commands":commands,"source_sha256":{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob("*")) if p.suffix in (".c",".h")},
      "binary_sha256":{n:sha(out/n) for n in ("probe","cohort","test_fft_integration")},
      "precision":"2.5 MS/s direct FP32; higher-rate FP32 overlap-save proposal with direct epoch repair and conservative fallback"}
    (out/"build.json").write_text(json.dumps(receipt,indent=2)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",required=True,type=Path);p.add_argument("--arm",action="store_true");p.add_argument("--sanitize",action="store_true")
    a=p.parse_args();build(a.output.resolve(),a.arm,a.sanitize)
