import os
from pathlib import Path
import subprocess


def test_ring_reader_wrap_and_cli_usage(tmp_path):
    root=Path(__file__).resolve().parents[3]
    source=tmp_path/'test.c'
    source.write_text('#define main sampler_main\n#include "'+str(root/'tools/native_cpu_sample.c')+'"\n#undef main\n'
        '#include <assert.h>\nint main(void){char data[16],out[16];'
        'for(int i=0;i<16;++i)data[i]=(char)i;'
        'for(unsigned at=0;at<64;++at)for(unsigned n=0;n<=16;++n){'
        'copy_ring(out,data,16,at,n);for(unsigned j=0;j<n;++j)assert(out[j]==data[(at+j)%16]);}'
        'char *argv[]={"sampler",0};assert(sampler_main(1,argv)==2);return 0;}\n')
    binary=tmp_path/'test'
    subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],
                   env={**os.environ,'TMPDIR':'/var/tmp'},check=True,capture_output=True)
    subprocess.run([str(binary)],check=True,capture_output=True,timeout=5)
