#define _POSIX_C_SOURCE 200809L

#include "native_glrt_profile_wrap.h"

#include <fftw3.h>
#include <stdint.h>
#include <time.h>

static leo_native_glrt_wrap_profile profile;

typedef struct { double cpu,wall; } stamp;

static void requested(uint64_t bytes)
{
    profile.allocation_requested_bytes=UINT64_MAX-profile.allocation_requested_bytes<bytes
        ? UINT64_MAX : profile.allocation_requested_bytes+bytes;
}

static double milliseconds(clockid_t clock)
{
    struct timespec value;
    return clock_gettime(clock,&value) ? 0.0
        : 1000.0*(double)value.tv_sec+1e-6*(double)value.tv_nsec;
}

static stamp started(void)
{
    return (stamp){milliseconds(CLOCK_PROCESS_CPUTIME_ID),
        milliseconds(CLOCK_MONOTONIC)};
}

static void elapsed(stamp begin,double *cpu,double *wall)
{
    *cpu+=milliseconds(CLOCK_PROCESS_CPUTIME_ID)-begin.cpu;
    *wall+=milliseconds(CLOCK_MONOTONIC)-begin.wall;
}

void leo_native_glrt_wrap_profile_reset(void)
{
    profile=(leo_native_glrt_wrap_profile){0};
}

leo_native_glrt_wrap_profile leo_native_glrt_wrap_profile_snapshot(void)
{
    return profile;
}

void *__real_malloc(size_t size);
void *__real_calloc(size_t count,size_t size);
void *__real_realloc(void *pointer,size_t size);
void __real_free(void *pointer);

void *__wrap_malloc(size_t size)
{
    stamp begin=started();void *result=__real_malloc(size);
    ++profile.malloc_calls;requested(size);
    elapsed(begin,&profile.allocation_cpu_ms,&profile.allocation_wall_ms);return result;
}

void *__wrap_calloc(size_t count,size_t size)
{
    stamp begin=started();void *result=__real_calloc(count,size);
    ++profile.calloc_calls;
    if(!count||size<=UINT64_MAX/count)requested((uint64_t)count*size);
    else profile.allocation_requested_bytes=UINT64_MAX;
    elapsed(begin,&profile.allocation_cpu_ms,&profile.allocation_wall_ms);return result;
}

void *__wrap_realloc(void *pointer,size_t size)
{
    stamp begin=started();void *result=__real_realloc(pointer,size);
    ++profile.realloc_calls;requested(size);
    elapsed(begin,&profile.allocation_cpu_ms,&profile.allocation_wall_ms);return result;
}

void __wrap_free(void *pointer)
{
    stamp begin=started();__real_free(pointer);++profile.free_calls;
    elapsed(begin,&profile.allocation_cpu_ms,&profile.allocation_wall_ms);
}

fftw_plan __real_fftw_plan_dft_1d(int,fftw_complex *,fftw_complex *,int,unsigned);
fftwf_plan __real_fftwf_plan_dft_1d(int,fftwf_complex *,fftwf_complex *,int,unsigned);
void __real_fftw_execute(const fftw_plan);
void __real_fftwf_execute(const fftwf_plan);
void __real_fftw_execute_dft(const fftw_plan,fftw_complex *,fftw_complex *);
void __real_fftwf_execute_dft(const fftwf_plan,fftwf_complex *,fftwf_complex *);

fftw_plan __wrap_fftw_plan_dft_1d(int n,fftw_complex *in,fftw_complex *out,
    int sign,unsigned flags)
{
    stamp begin=started();fftw_plan result=__real_fftw_plan_dft_1d(n,in,out,sign,flags);
    ++profile.fft_plan_calls;
    elapsed(begin,&profile.fft_plan_cpu_ms,&profile.fft_plan_wall_ms);return result;
}

fftwf_plan __wrap_fftwf_plan_dft_1d(int n,fftwf_complex *in,fftwf_complex *out,
    int sign,unsigned flags)
{
    stamp begin=started();fftwf_plan result=__real_fftwf_plan_dft_1d(n,in,out,sign,flags);
    ++profile.fftf_plan_calls;
    elapsed(begin,&profile.fftf_plan_cpu_ms,&profile.fftf_plan_wall_ms);return result;
}

void __wrap_fftw_execute(const fftw_plan plan)
{
    stamp begin=started();__real_fftw_execute(plan);++profile.fft_execute_calls;
    elapsed(begin,&profile.fft_execute_cpu_ms,&profile.fft_execute_wall_ms);
}

void __wrap_fftwf_execute(const fftwf_plan plan)
{
    stamp begin=started();__real_fftwf_execute(plan);++profile.fftf_execute_calls;
    elapsed(begin,&profile.fftf_execute_cpu_ms,&profile.fftf_execute_wall_ms);
}

void __wrap_fftw_execute_dft(const fftw_plan plan,fftw_complex *in,fftw_complex *out)
{
    stamp begin=started();__real_fftw_execute_dft(plan,in,out);++profile.fft_execute_calls;
    elapsed(begin,&profile.fft_execute_cpu_ms,&profile.fft_execute_wall_ms);
}

void __wrap_fftwf_execute_dft(const fftwf_plan plan,fftwf_complex *in,fftwf_complex *out)
{
    stamp begin=started();__real_fftwf_execute_dft(plan,in,out);++profile.fftf_execute_calls;
    elapsed(begin,&profile.fftf_execute_cpu_ms,&profile.fftf_execute_wall_ms);
}
