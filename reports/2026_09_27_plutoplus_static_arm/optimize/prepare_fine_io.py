"""Exact FFT input/output traffic reduction for the private fine-CFO stage."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/fineio';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/coarseclean/src',root/'src')
n=root/'src/native_presence';p=n/'fft32_fftw.c';s=p.read_text()
s+='''
/* Private fine-stage entry: omitted input cells are zero, and only the requested
 * circular output interval is consumed. The FFT and its FP32 inputs are identical. */
void leo_fft_forward_range(leo_fft *fft,const double complex *input,size_t used,
    size_t first,size_t count)
{
    float_fftw_plan *p=fft->backend_plan;
    for(size_t k=0;k<used;++k) p->input[k]=(float complex)input[k];
    memset(p->input+used,0,(fft->size-used)*sizeof(*p->input));
    fftwf_execute(p->plan);
    size_t bin=first;
    for(size_t k=0;k<count;++k){
        fft->output[bin]=(double complex)p->output[bin];
        if(++bin==fft->size)bin=0;
    }
}
''';p.write_text(s)
p=n/'presence.c';s=p.read_text()
s=replace(s,'static void fine_scores(',
    'void leo_fft_forward_range(leo_fft *,const double complex *,size_t,size_t,size_t);\n\nstatic void fine_scores(')
s=replace(s,'        memset(w->input, 0, w->fine_fft.size * sizeof(*w->input));',
    '        memset(w->input, 0, w->n * sizeof(*w->input));')
s=replace(s,'        leo_fft_forward(&w->fine_fft, w->input);',
    '        leo_fft_forward_range(&w->fine_fft,w->input,w->n,(size_t)first_bin,(size_t)frequency_count);')
p.write_text(s);build('fineio',root);build('fineio',root,host=True,sanitize=True)
