/* FP64 matched dots and reductions are unchanged. Only these transforms
 * narrow to FP32. Workspace-local plans are lazily created inside timing. */
static int glrt_float_fft_forward(leo_presence_workspace *w,leo_fft *fft,
    const double complex *input,size_t n,int final)
{
    int slot=final?1:0;
    if(!w->glrt_f32_plan[slot]) {
        w->glrt_f32_input[slot]=fftwf_alloc_complex(n);
        w->glrt_f32_output[slot]=fftwf_alloc_complex(n);
        if(w->glrt_f32_input[slot]&&w->glrt_f32_output[slot])
            w->glrt_f32_plan[slot]=fftwf_plan_dft_1d((int)n,
                w->glrt_f32_input[slot],w->glrt_f32_output[slot],
                FFTW_FORWARD,FFTW_ESTIMATE);
        if(!w->glrt_f32_plan[slot])return -1;
    }
    for(size_t k=0;k<n;++k)
        w->glrt_f32_input[slot][k]=(float)creal(input[k])+I*(float)cimag(input[k]);
    fftwf_execute(w->glrt_f32_plan[slot]);
    for(size_t k=0;k<n;++k)
        fft->output[k]=(double)crealf(w->glrt_f32_output[slot][k])+I*(double)cimagf(w->glrt_f32_output[slot][k]);
    return 0;
}
