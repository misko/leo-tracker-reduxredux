import ctypes
import subprocess

from tools.pipeline_eval.qualification import fractional_cost_build as build
from tools.pipeline_eval.qualification import fractional_cost_eval as evaluate
from tools.pipeline_eval.qualification import fractional_cost_results as report

C_WITNESS = r"""
#include <complex.h>
#include <stddef.h>
#include <string.h>
#define LEO_PRESENCE_PRECOMPUTE 1
#define LEO_PRESENCE_ENERGY_SYMBOL_SUPPORT 0
#define LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY 0
#define LEO_PRESENCE_EPOCH_FRAMES 16
typedef struct {
  int wide_regional,rate,n,acquisition_first_frame;
  double complex *samples, *glrt_exact_rotated, *glrt_control_rotated;
} leo_presence_workspace;
static int symbol_start(const leo_presence_workspace *w,int s) {(void)w; return 44*s;}
static int frame_start(const leo_presence_workspace *w,int epoch,int f) {
  (void)w; return epoch+(40000*f+1)/3;
}
static void glrt_prepare_rotations(leo_presence_workspace *w,double cfo,double offset,int late) {
  (void)w; (void)cfo; (void)offset; (void)late;
}
static void glrt_add_frame(leo_presence_workspace *w,const double complex corr[2][64],
    double spectra[2][128],double ceilings[2]) {
  (void)w; (void)corr; (void)spectra; (void)ceilings;
}
static void glrt_finish(leo_presence_workspace *w,double spectra[2][128],
    const double ceilings[2],double result[3]) {
  (void)w; (void)spectra; (void)ceilings; (void)result;
}
#include "fractional_cost_integer.h"

int witness(void) {
  leo_presence_workspace w={.wide_regional=1,.rate=10000000,.n=13333};
  double score[5][3];
  if (leo_grid_four(&w,200000,0,0,0,0,score) ||
      leo_grid_four(&w,200000,10429,0,0,0,score) ||
      leo_grid_four(&w,200000,13332,0,0,0,score)) return -1;
#if defined(__x86_64__) && (defined(__GNUC__) || defined(__clang__))
  if (!__builtin_cpu_supports("avx2")) return 1;
  double complex samples[4100], exact[3000], control[3000];
  w.samples=samples; w.glrt_exact_rotated=exact; w.glrt_control_rotated=control;
  for (int k=0; k<4100; ++k) samples[k]=(k*k%513-256)+I*(k*823%65536-32768);
  for (int k=0; k<3000; ++k) {
    exact[k]=(k*7%121-61)/9.0+I*(k*53%121-61)/13.0;
    control[k]=(k*29%119-61)/51.0+I*(k*23%119-61)/119.0;
  }
  double complex actual[4][2][64], ref[4][2][64]={{{0}}};
  const int start=735, shift[4]={0,1,3,4};
  leo_grid_correlate(&w,start,actual);
  for (int epoch=0; epoch<4; ++epoch) for (int s=0; s<64; ++s) {
    for (int k=44*(s+2); k<44*(s+3); ++k) {
      double complex a=samples[start+shift[epoch]+k];
      ref[epoch][0][s]+=a*exact[k];
      ref[epoch][1][s]+=a*control[k];
    }
  }
  if (memcmp(actual,ref,sizeof(actual))) return 0;
#endif
  return 1;
}
"""


def test_grouped_complex_dot_is_bit_exact_and_respects_circular_fallback(tmp_path):
    witness = tmp_path / "witness.c"
    library = tmp_path / "witness.so"
    witness.write_text(C_WITNESS)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-fno-fast-math",
            "-ffp-contract=off",
            "-fcx-limited-range",
            "-fPIC",
            "-shared",
            "-I",
            str(build.HEADER.parent),
            str(witness),
            "-o",
            str(library),
        ],
        check=True,
    )
    assert ctypes.CDLL(str(library)).witness() == 1


def test_work_audit_never_counts_wrap_or_changed_terminal_support():
    assert report.group_geometry(1) is None
    assert report.group_geometry(10429) is None
    assert report.group_geometry(13331) is None
    assert report.group_geometry(2) == 15
    assert report.group_geometry(11000) == 14
    receipt = dict(candidate_counts=[2, 1], grid_calls=[[2, 5.0], [2, 5.0], [2, 5.0]])
    assert report.grid_work(receipt) == dict(
        calls=2, grouped=2, saved_grid_hypotheses=2, saved_frame_ffts=60, saved_final_ffts=8
    )


def test_grouped_results_reject_gate_or_support_drift():
    source = dict(sha256="same", hints=[4, 8], trace=["prefix"], gates=["passed"])
    assert evaluate.validate(dict(typed=source, grouped=source))
    assert not evaluate.validate(dict(typed=source, grouped=source | {"gates": []}))
    assert not evaluate.validate(dict(typed=source, grouped=source | {"trace": []}))
