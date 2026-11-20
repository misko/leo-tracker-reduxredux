"""Add a guarded signed CFO prediction to the frozen sixteen-center scout."""

from pathlib import Path

from .wide_regional import replace

HEADER = Path(__file__).with_name("phase_scout_mask.h")


def proposal(code):
    code = replace(
        code,
        '#include "proposal_core.h"',
        '#include "proposal_core.h"\n#include "phase_scout_mask.h"',
    )
    code = replace(
        code,
        "    float reference_norm[METHODS]",
        "    fftwf_complex *phase_scout[3];\n    int phase_active;\n"
        "    float reference_norm[METHODS]",
    )
    code = replace(
        code,
        "    for(size_t rank=0;rank<z;rank++)b->scores[3]",
        """    if(rate==10000000.0)for(int m=0;m<3;++m){
        b->phase_scout[m]=fftwf_alloc_complex(z);
        if(!b->phase_scout[m]){bank_free(b);return -1;}
    }
    for(size_t rank=0;rank<z;rank++)b->scores[3]""",
    )
    code = replace(
        code, "static int bank_init(", "static void bank_free(bank *b);\nstatic int bank_init("
    )
    code = replace(
        code,
        "static void bank_free(bank *b){",
        "static void bank_free(bank *b){for(int m=0;m<3;++m)fftwf_free(b->phase_scout[m]);",
    )
    code = replace(
        code,
        "memset(score,0,z*sizeof(*score));return;",
        """memset(score,0,z*sizeof(*score));
    if(b->phase_active&&method<3)memset(b->phase_scout[method],0,z*sizeof(*b->corr));
    return;""",
    )
    code = replace(
        code,
        "for(size_t k=0;k<z;k++)score[k]=method<3?",
        """if(b->phase_active&&method<3)
        for(size_t k=0;k<z;++k){
            b->phase_scout[method][k][0]=b->corr[k][0]*scale;
            b->phase_scout[method][k][1]=b->corr[k][1]*scale;
        }
    for(size_t k=0;k<z;k++)score[k]=method<3?""",
    )
    code = replace(
        code,
        "    bank *b=&w->bank;size_t n=b->n,z=b->fft_n;",
        "    bank *b=&w->bank;size_t n=b->n,z=b->fft_n;\n"
        "    b->phase_active=budget==16&&b->rate==10000000.0;",
        count=2,
    )
    marker = "int leo_proposal_top4(leo_proposal_workspace *w"
    return replace(
        code,
        marker,
        """void leo_proposal_phase_masks(leo_proposal_workspace *w,
    const int *centers,int count,uint32_t *masks,int receiver)
{
    bank *b=&w->bank;
    const int trace=getenv("LEO_PHASE_SCOUT_TRACE")!=NULL;
    for(int j=0;j<count;++j){
        masks[j]=PHASE_SCOUT_ALL;
        if(!b->phase_active)continue;
        size_t k=((size_t)centers[j]*b->fft_n+b->n/2)/b->n%b->fft_n;
        float values[3][2];
        for(int m=0;m<3;++m){
            values[m][0]=b->phase_scout[m][k][0];
            values[m][1]=b->phase_scout[m][k][1];
        }
        double hz[3],rho[3];
        masks[j]=phase_scout_mask(values,b->rate,hz,rho);
        if(trace)fprintf(stderr,"phase-scout %d %d %d %u %.6f %.6f %.6f %.9g %.9g %.9g\\n",
            receiver,j,centers[j],(unsigned)masks[j],
            hz[0],hz[1],hz[2],rho[0],rho[1],rho[2]);
    }
}
"""
        + marker,
    )


def native(code):
    code = replace(
        code,
        "    const int budget=wide&&context->refinement_mode==3 ? 16 : 4;",
        """    const int budget=wide&&context->refinement_mode==3 ? 16 : 4;
    const int phase_active=budget==16&&dwell_ms==20&&stride_ms==20;
    uint32_t phase_masks[2][16]={{0}};
    context->search->phase_active=phase_active;""",
    )
    code = replace(
        code,
        "        for(int rx=0;rx<context->receiver_count;++rx)\n"
        "            if((context->receiver_count==1",
        "        for(int rx=0;rx<context->receiver_count;++rx){\n"
        "            if((context->receiver_count==1",
    )
    boundary = (
        "    if(profile_clock(&end_cpu,&end_wall)){\n"
        "        status=LEO_NATIVE_GLRT_KERNEL;goto done;\n"
        "    }\n"
        "    measured.proposals_cpu_ms"
    )
    code = replace(
        code,
        "                status=LEO_NATIVE_GLRT_KERNEL;goto done;\n            }\n    }\n"
        + boundary,
        """                status=LEO_NATIVE_GLRT_KERNEL;goto done;
            }
            if(phase_active)leo_proposal_phase_masks(context->proposal,centers[anchor][rx],
                counts[anchor][rx],phase_masks[rx],rx);
        }
    }
"""
        + boundary,
    )
    return replace(
        code,
        "            for(int epoch=first;epoch<=last;++epoch)selected[epoch]=1;",
        """            for(int epoch=first;epoch<=last;++epoch){
                if(phase_active) context->search->phase_masks[epoch]=
                    selected[epoch] ? context->search->phase_masks[epoch]|phase_masks[rx][c]
                                    : phase_masks[rx][c];
                selected[epoch]=1;
            }""",
    )


def coarse(code):
    code = replace(
        code,
        "        if (w->wide_regional) "
        "wide_regional_float_add(samples,real,imag,taps,inverse,sum);",
        """        if (w->wide_regional) {
            uint32_t mask=w->phase_active?w->phase_masks[epoch]:PHASE_SCOUT_ALL;
            if(mask==PHASE_SCOUT_ALL)wide_regional_float_add(samples,real,imag,taps,inverse,sum);
            else phase_scout_float_add(samples,real,imag,taps,inverse,sum,mask);
        }""",
    )
    return replace(
        code,
        "w->grid[f*w->n+epoch]=w->support[epoch]>0 ?",
        "w->grid[f*w->n+epoch]=w->support[epoch]>0 && (!w->phase_active ||\n"
        "            (w->phase_masks[epoch] & (UINT32_C(1)<<f))) ?",
        count=2,
    )


def float_coarse(code):
    end = code.rfind("#endif")
    return (
        code[:end]
        + """
static void phase_scout_float_add(const float *samples,const float *real,
    const float *imag,int taps,float inverse,float *sum,uint32_t mask)
{
#if defined(__ARM_NEON)
    for(int f=0;f<WIDE_REGIONAL_BINS;f+=4){
        if(!(mask&(UINT32_C(15)<<f)))continue;
        float32x4_t r=vdupq_n_f32(0.0f),i=r;
        for(int k=0;k<taps;++k){
            float32x4_t xr=vdupq_n_f32(samples[2*k]);
            float32x4_t xi=vdupq_n_f32(samples[2*k+1]);
            float32x4_t rr=vld1q_f32(real+CFO_COUNT*k+f);
            float32x4_t ri=vld1q_f32(imag+CFO_COUNT*k+f);
            r=vaddq_f32(r,vaddq_f32(vmulq_f32(xr,rr),vmulq_f32(xi,ri)));
            i=vaddq_f32(i,vsubq_f32(vmulq_f32(xi,rr),vmulq_f32(xr,ri)));
        }
        vst1q_f32(sum+f,vaddq_f32(vld1q_f32(sum+f),
            vmulq_n_f32(coarse_magnitude(r,i),inverse)));
    }
#else
    while(mask){
        int f=__builtin_ctz(mask);
        mask &= mask-1;
        float r=0,i=0;
        for(int k=0;k<taps;++k){
            r+=samples[2*k]*real[CFO_COUNT*k+f]+samples[2*k+1]*imag[CFO_COUNT*k+f];
            i+=samples[2*k+1]*real[CFO_COUNT*k+f]-samples[2*k]*imag[CFO_COUNT*k+f];
        }
        sum[f]+=sqrtf(r*r+i*i)*inverse;
    }
#endif
}

"""
        + code[end:]
    )


def apply(source):
    private = source / "kernel/private"
    edits = {
        source / "native_glrt.c": native,
        private / "proposal_core.c": proposal,
        private / "proposal_core.h": lambda x: replace(
            x,
            "#endif",
            '__attribute__((visibility("hidden")))\n'
            "void leo_proposal_phase_masks(leo_proposal_workspace *w,const int *centers,"
            "int count,uint32_t *masks,int receiver);\n#endif",
        ),
        source / "kernel/private_namespace.h": lambda x: replace(
            x,
            "#define leo_proposal_create",
            "#define leo_proposal_phase_masks leo_native_glrt_private_proposal_phase_masks\n"
            "#define leo_proposal_create",
        ),
        private / "native_presence/presence.c": lambda x: replace(
            replace(
                x,
                "    int regional_count, wide_regional;",
                "    int regional_count, wide_regional, phase_active;\n"
                "    uint32_t phase_masks[13334];",
            ),
            "#define WIDE_REGIONAL_BINS 21",
            "#define WIDE_REGIONAL_BINS 21\n#define PHASE_SCOUT_ALL ((UINT32_C(1)<<21)-1)",
        ),
        private / "native_presence/coarse_fp32.h": coarse,
        private / "native_presence/wide_regional_cfo.h": float_coarse,
    }
    for path, edit in edits.items():
        path.write_text(edit(path.read_text()))
    (private / HEADER.name).write_bytes(HEADER.read_bytes())
