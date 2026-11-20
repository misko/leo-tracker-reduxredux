"""Add a dual-RX short-window epoch-union control to an authenticated wide build."""

from pathlib import Path

HEADER = Path(__file__).with_name("paired_epoch_union.h")


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError("unrecognized wide regional source boundary")
    return source.replace(old, new)


def overlay(source):
    source = replace(
        source,
        '#include "short_window_glrt.h"',
        '#include "short_window_glrt.h"\n#include "paired_epoch_union.h"',
    )
    source = replace(
        source,
        "    int receiver_count;\n};",
        """    int receiver_count;
    int paired_epoch_disabled, paired_epoch_valid;
    paired_epoch_trace paired_epoch;
};""",
    )
    source = replace(
        source,
        "static int cpu_ms(double *result)",
        """int leo_native_glrt_paired_epoch_mode(leo_native_glrt *context,int enabled)
{
    if(!context||context->magic!=LEO_NATIVE_GLRT_CONTEXT_MAGIC||
       (enabled!=0&&enabled!=1))return LEO_NATIVE_GLRT_INVALID;
    int status=context_enter(context);if(status)return status;
    context->paired_epoch_disabled=!enabled;
    context->paired_epoch_valid=0;
    context_leave(context);
    return LEO_NATIVE_GLRT_OK;
}

int leo_native_glrt_paired_epoch_trace(leo_native_glrt *context,
    paired_epoch_trace *out)
{
    if(!context||context->magic!=LEO_NATIVE_GLRT_CONTEXT_MAGIC||!out)
        return LEO_NATIVE_GLRT_INVALID;
    int status=context_enter(context);if(status)return status;
    if(context->paired_epoch_valid)*out=context->paired_epoch;
    else status=LEO_NATIVE_GLRT_INVALID;
    context_leave(context);
    return status;
}

static int cpu_ms(double *result)""",
    )
    source = replace(
        source,
        "    int wide=short_window&&context->rate==10000000u;",
        """    int wide=short_window&&context->rate==10000000u;
    int paired=wide&&context->receiver_count==2;
    context->paired_epoch_valid=0;
    if(paired)memset(&context->paired_epoch,0,sizeof(context->paired_epoch));""",
    )
    source = replace(
        source,
        """        for(int c=0;c<count;++c){
            int first=current[c]-1,last=current[c]+1;
            if(first<0)first=0;
            if(last>=(int)context->frame)last=(int)context->frame-1;
            for(int epoch=first;epoch<=last;++epoch)selected[epoch]=1;
        }""",
        """        paired_epoch_mark(selected,(int)context->frame,current,count);
        if(paired){
            paired_epoch_trace *trace=&context->paired_epoch;
            trace->own_counts[rx]=count;
            for(int i=0;i<count;++i)trace->own_centers[rx][i]=current[i];
            trace->union_enabled=!context->paired_epoch_disabled;
            if(trace->union_enabled)
                paired_epoch_mark(selected,(int)context->frame,
                    centers[0][1-rx],counts[0][1-rx]);
        }""",
    )
    source = replace(
        source,
        "        size_t offset=(size_t)start_ms*context->rate/1000u;",
        """        if(paired){
            paired_epoch_trace *trace=&context->paired_epoch;
            int n=context->search->regional_count;
            if(n>PAIRED_EPOCH_MAX_ACTIVE){status=LEO_NATIVE_GLRT_KERNEL;goto done;}
            trace->active_counts[rx]=n;
            for(int i=0;i<n;++i)trace->active[rx][i]=context->search->regional_epochs[i];
        }
        size_t offset=(size_t)start_ms*context->rate/1000u;""",
    )
    return replace(
        source,
        "                if(profile)*profile=measured;",
        "                if(profile)*profile=measured;\n"
        "                context->paired_epoch_valid=paired;",
    )
