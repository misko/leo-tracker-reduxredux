"""Add one opt-in isolated-region search to the stock wide capsule."""

from pathlib import Path

from .wide_regional import replace

ENTRY = "leo_native_glrt_analyze_incremental_v1"
SCOUT_ENTRY = "leo_differential_scout_one_v1"
HEADER = Path(__file__).with_name("incremental_rescue.h")


def native(source):
    source = replace(
        source,
        '#include "short_window_glrt.h"',
        '#include "short_window_glrt.h"\n#include "incremental_rescue.h"',
    )
    source = replace(
        source,
        "static int analyze_profiled(",
        """static int fractional_gate(const leo_full_search_result *search)
{
    for(int i=0;i<search->candidate_count;++i){
        const leo_full_search_candidate *candidate=&search->candidates[i];
        if(candidate->fractional_epoch_status==1 && candidate->fractional_margin>=0.025)
            return 1;
    }
    return 0;
}

static int analyze_profiled(""",
    )
    source = replace(
        source,
        "leo_native_glrt_result *result,leo_native_glrt_profile *profile,int short_window)",
        "leo_native_glrt_result *result,leo_native_glrt_profile *profile,int short_window,\n"
        "    leo_incremental_proposal propose,leo_incremental_trace *trace)",
    )
    source = replace(
        source,
        "        copy_row(&temporary.rows[temporary.row_count++],rx,(int)window,",
        """        if(propose){
            leo_incremental_lane *lane=&trace->lanes[rx];
            *lane=(leo_incremental_lane){.count=count,.hint=-1};
            memcpy(lane->ordinary,current,(size_t)count*sizeof(*current));
            if(!fractional_gate(&search)){
                double start_cpu,start_wall,stop_cpu,stop_wall;
                if(profile_clock(&start_cpu,&start_wall)){
                    status=LEO_NATIVE_GLRT_KERNEL;goto done;
                }
                const int hint=propose(rx);
                if(profile_clock(&stop_cpu,&stop_wall)){
                    status=LEO_NATIVE_GLRT_KERNEL;goto done;
                }
                lane->hint=hint;
                lane->scout_cpu_ms=stop_cpu-start_cpu;
                lane->scout_wall_ms=stop_wall-start_wall;
                lane->decision=LEO_RESCUE_NO_HINT;
                if(hint < -1 || hint >= (int)context->frame){
                    status=LEO_NATIVE_GLRT_INVALID;goto done;
                }
                if(hint>=0){
                    const int first=hint>0 ? hint-1 : 0;
                    const int last=hint+1<(int)context->frame ? hint+1 : hint;
                    lane->requested=last-first+1;
                    int overlap=0;
                    for(int e=first;e<=last;++e)overlap|=selected[e];
                    lane->decision=LEO_RESCUE_OVERLAP;
                    if(!overlap){
                        lane->evaluated=lane->requested;
                        context->search->regional_count=lane->evaluated;
                        for(int j=0;j<lane->evaluated;++j)
                            context->search->regional_epochs[j]=first+j;
                        leo_full_search_result donor;
                        if(profile_clock(&start_cpu,&start_wall) ||
                           leo_full_search_run_prepared_with_fine_workspace_mode(context->search,
                            prepared_view->raw[rx]+offset,
                            prepared_view->normalized[rx]+2*offset,prepared_view->prefix[rx]+offset,
                            context->rate/50u,&donor,&context->fine_workspace,
                            context->refinement_mode,context->search->regional_epochs,
                            context->search->regional_count) ||
                           profile_clock(&stop_cpu,&stop_wall)){
                            status=LEO_NATIVE_GLRT_KERNEL;goto done;
                        }
                        lane->rescue_cpu_ms=stop_cpu-start_cpu;
                        lane->rescue_wall_ms=stop_wall-start_wall;
                        lane->decision=LEO_RESCUE_NEGATIVE;
                        if(fractional_gate(&donor)){
                            search=donor;
                            lane->decision=LEO_RESCUE_ACCEPTED;
                        }
                    }
                }
            }
        }
        copy_row(&temporary.rows[temporary.row_count++],rx,(int)window,""",
    )
    for before, after, count in (
        ("stride_ms,result,profile,0);", "stride_ms,result,profile,0,NULL,NULL);", 1),
        ("\n        result,profile,0);", "\n        result,profile,0,NULL,NULL);", 1),
        (
            "complex_times,20,20,result,profile,1);",
            "complex_times,20,20,result,profile,1,NULL,NULL);",
            2,
        ),
    ):
        source = replace(source, before, after, count=count)
    return replace(
        source,
        "int leo_native_glrt_analyze_short_window(leo_native_glrt *context,",
        f"""int {ENTRY}(leo_native_glrt *context,
    const int16_t *ci16,size_t complex_times,leo_incremental_proposal propose,
    leo_native_glrt_result *result,leo_incremental_trace *trace)
{{
    if(!context || context->magic!=LEO_NATIVE_GLRT_CONTEXT_MAGIC || !propose || !trace ||
       context->rate!=10000000u || context->receiver_count!=2 || context->refinement_mode!=3)
        return LEO_NATIVE_GLRT_INVALID;
    return analyze_profiled(context,ci16,complex_times,20,20,result,NULL,1,propose,trace);
}}

int leo_native_glrt_analyze_short_window(leo_native_glrt *context,""",
    )


def scout(source):
    declaration = "void leo_differential_scout(scout_context *s, const int16_t *data,"
    split = source.index(declaration)
    function = replace(
        source[split:], declaration, f"void {SCOUT_ENTRY}(scout_context *s, const int16_t *data,"
    )
    function = replace(function, "double *scores)", "double *scores, int lane)")
    function = replace(
        function,
        "    for (int lane = 0; lane < receivers; ++lane) {",
        "    if (lane >= 0 && lane < receivers) {",
    )
    function = replace(
        function, "double *lane_scores = scores + lane * frame;", "double *lane_scores = scores;"
    )
    return source + "\n" + function
