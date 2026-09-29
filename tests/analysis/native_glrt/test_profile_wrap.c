#include "native_glrt_profile_wrap.h"

#include <assert.h>
#include <fftw3.h>
#include <stdlib.h>

int main(void)
{
    leo_native_glrt_wrap_profile_reset();
    void *allocation=malloc(97);assert(allocation);free(allocation);
    fftwf_complex *input=fftwf_alloc_complex(16);
    fftwf_complex *output=fftwf_alloc_complex(16);
    assert(input&&output);
    fftwf_plan plan=fftwf_plan_dft_1d(16,input,output,FFTW_FORWARD,FFTW_ESTIMATE);
    assert(plan);fftwf_execute(plan);fftwf_execute_dft(plan,input,output);
    fftwf_destroy_plan(plan);fftwf_free(output);fftwf_free(input);
    leo_native_glrt_wrap_profile measured=leo_native_glrt_wrap_profile_snapshot();
    assert(measured.malloc_calls>=1&&measured.free_calls>=1);
    assert(measured.allocation_requested_bytes>=97);
    assert(measured.fftf_plan_calls==1);
    assert(measured.fftf_execute_calls==2);
    assert(measured.allocation_cpu_ms>=0&&measured.allocation_wall_ms>=0);
    assert(measured.fftf_plan_cpu_ms>=0&&measured.fftf_plan_wall_ms>=0);
    assert(measured.fftf_execute_cpu_ms>=0&&measured.fftf_execute_wall_ms>=0);
    leo_native_glrt_wrap_profile_reset();
    measured=leo_native_glrt_wrap_profile_snapshot();
    assert(!measured.malloc_calls&&!measured.fftf_plan_calls&&!measured.fftf_execute_calls);
    return 0;
}
