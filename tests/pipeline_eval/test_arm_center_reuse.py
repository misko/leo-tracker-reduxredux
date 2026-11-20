import subprocess

from tools.pipeline_eval.qualification import arm_center_reuse_results as report
from tools.pipeline_eval.variants.arm_center_pair import HEADER

C_WITNESS = r"""
#include <assert.h>
#include <complex.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#define LEO_PRESENCE_PRECOMPUTE 1
#define LEO_PRESENCE_EPOCH_FRAMES 16
#define LEO_PRESENCE_ENERGY_SYMBOL_SUPPORT 0
#define LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY 0

typedef struct {
    int wide_regional, rate, n, acquisition_first_frame;
    const double complex *samples, *glrt_exact_rotated, *glrt_control_rotated;
} leo_presence_workspace;

static int symbol_start(const leo_presence_workspace *w, int s) { (void)w; return 44*s; }
static int frame_start(const leo_presence_workspace *w, int e, int f)
{ (void)w; return e+(40000*f+1)/3; }
static double regional_cfo_limit(const leo_presence_workspace *w) { (void)w; return 800000; }
static void glrt_prepare_rotations(leo_presence_workspace *w, double c, double o, int late)
{ (void)w; assert(isfinite(c) && o==0 && late==0); }

/* This witness checks the dot reductions independently of the real FFTs. */
static void glrt_add_frame(leo_presence_workspace *w, const double complex corr[2][64],
    double spectra[2][128], double ceilings[2])
{
    (void)w;
    for (int i=0; i<2; ++i) {
        for (int s=0; s<64; ++s) {
            spectra[i][2*s]+=creal(corr[i][s]);
            spectra[i][2*s+1]+=cimag(corr[i][s]);
        }
        ceilings[i] += 1.0;
    }
}
static void glrt_finish(leo_presence_workspace *w, double spectra[2][128],
    const double ceilings[2], double output[3])
{
    (void)w;
    output[0]=0;
    output[1]=0;
    output[2]=ceilings[0];
    for (int i=0; i<2; ++i) for (int s=0; s<128; ++s)
        output[i]+=spectra[i][s]/(s+1);
}

#include "arm_center_pair.h"

static void scalar(leo_presence_workspace *w, int e, double output[3])
{
    double spectra[2][128]={{0}}, ceilings[2]={0};
    for(int f=0; f<16; ++f) {
        const double complex *x=w->samples+frame_start(w,e,f);
        if (frame_start(w,e,f)+2904>200000) break;
        double complex corr[2][64]={{0}};
        for (int i=0; i<2; ++i) {
            const double complex *t=i ? w->glrt_control_rotated : w->glrt_exact_rotated;
            for (int s=0; s<64; ++s) for (int k=44*(s+2); k<44*(s+3); ++k) {
                corr[i][s]+=x[k]*t[k];
            }
        }
        glrt_add_frame(w,corr,spectra,ceilings);
    }
    glrt_finish(w,spectra,ceilings,output);
}

int main(void)
{
    static double complex samples[200000], exact[2904], control[2904];
    for (int k=0; k<200000; ++k) samples[k]=(k*521%65536-32768)+I*(k*823%65536-32768);
    for (int k=0; k<2904; ++k) {
        exact[k]=(k*7%121-61)/9.0+I*(k*53%121-61)/13.0;
        control[k]=(k*29%119-61)/51.0+I*(k*23%119-61)/119.0;
    }
    leo_presence_workspace w={1,10000000,13333,0,samples,exact,control};
    unsigned frames;
    double score[2][3], expected[2][3];
    assert(!leo_center_pair(&w,200000,13332,0,score,&frames));
    assert(!leo_center_pair(&w,200000,10429,0,score,&frames));
    assert(!leo_center_pair(&w,200000,735,INFINITY,score,&frames));
    for(int e=735; e<=11000; e+=10265) {
        assert(leo_center_pair(&w,200000,e,-193450,score,&frames));
        assert(frames==(e==735 ? 15u : 14u));
        scalar(&w,e,expected[0]);
        scalar(&w,e+1,expected[1]);
        assert(memcmp(score,expected,sizeof(score))==0);
    }
    w.acquisition_first_frame=1;
    assert(!leo_center_pair(&w,200000,735,0,score,&frames));
    return 0;
}
"""


def test_portable_outer_pair_preserves_independent_reductions_and_fallback(tmp_path):
    source, exe = tmp_path / "pair.c", tmp_path / "pair"
    source.write_text(C_WITNESS)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-ffp-contract=off",
            "-fcx-limited-range",
            "-I",
            str(HEADER.parent),
            str(source),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)


def test_trace_conserves_a_wrap_fallback_and_detects_missing_outer_cell():
    assert report.conserved([10, 0, 0, 0], [8, 2, 0, 0], [2, 2, 3, 44])
    assert not report.conserved([10, 0, 0, 0], [8, 2, 0, 0], [1, 2, 3, 44])
    assert not report.conserved([10, 0, 0, 0], [8, 2, 0, 0], [2, 2, 3, 49])
