"""Preserve circular correlation using padded linear correlations and wrap-fold."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '2026_09_29_arm_float_proposal'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def transform(text):
    text = text.replace('size_t n; double rate;', 'size_t n, fft_n; double rate;')
    text = text.replace('b->n=n;b->rate=rate;', 'b->n=n;b->rate=rate;b->fft_n=1;while(b->fft_n<2*n-1)b->fft_n*=2;')
    text = text.replace('fftwf_alloc_complex(n)', 'fftwf_alloc_complex(b->fft_n)')
    # The template allocation in main is not part of the bank.
    text = text.replace('fftwf_complex *t=fftwf_alloc_complex(b->fft_n)', 'fftwf_complex *t=fftwf_alloc_complex(n)')
    text = text.replace('fftwf_plan_dft_1d((int)n,', 'fftwf_plan_dft_1d((int)b->fft_n,')
    text = text.replace('fftwf_execute(b->forward);', 'memset(b->time+n,0,(b->fft_n-n)*sizeof(*b->time));fftwf_execute(b->forward);')
    # correlate uses b->n, whereas initialization has a local n.
    text = text.replace('static void correlate(bank *b,float *score,int method){', 'static void correlate(bank *b,float *score,int method){size_t n=b->n;')
    text = text.replace('memcpy(b->reference_fft[m],b->freq,n*sizeof(*b->freq))', 'memcpy(b->reference_fft[m],b->freq,b->fft_n*sizeof(*b->freq))')
    text = text.replace('memcpy(b->reference_fft[3],b->freq,n*sizeof(*b->freq))', 'memcpy(b->reference_fft[3],b->freq,b->fft_n*sizeof(*b->freq))')
    text = text.replace('for(size_t k=0;k<b->n;k++){float ar=b->freq', 'for(size_t k=0;k<b->fft_n;k++){float ar=b->freq')
    text = text.replace('((float)b->n*onorm*', '((float)b->fft_n*onorm*')
    old='for(size_t k=0;k<b->n;k++)score[k]=method<3?hypotf(b->corr[k][0],b->corr[k][1])*scale:b->corr[k][0]*scale;'
    new='for(size_t k=0;k<b->n;k++){float re=b->corr[k][0],im=b->corr[k][1];if(k){re+=b->corr[b->fft_n-b->n+k][0];im+=b->corr[b->fft_n-b->n+k][1];}score[k]=method<3?hypotf(re,im)*scale:re*scale;}'
    assert old in text
    return text.replace(old,new)


def main():
    for name in ('host-v1','arm-v1'):
        out=HERE/'builds'/name
        out.mkdir(parents=True,exist_ok=False)
        source=out/'proposal_probe.c'
        source.write_text(transform((BASE/'proposal_probe.c').read_text()))
        base=json.loads((BASE/'builds'/name/'build.json').read_text())
        command=[s.replace(str(BASE/'builds'/name),str(out)) for s in base['command']]
        run=subprocess.run(command,check=True,capture_output=True,text=True)
        receipt={'command':command,'source_sha256':sha(source),'binary_sha256':sha(out/'proposal_probe'),'compiler_stderr':run.stderr,'base_source_sha256':sha(BASE/'proposal_probe.c')}
        (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    main()
