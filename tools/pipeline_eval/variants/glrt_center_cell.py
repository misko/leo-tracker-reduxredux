"""Reuse the completed final integer GLRT at the middle of the same lattice."""

_ORIGINAL = """        if(glrt(w,count,epoch,candidate->candidate.acquired_cfo_hz,0,
            LEO_PRESENCE_EPOCH_FRAMES,0,score))return -1;
"""
_REUSE = """#if LEO_PRESENCE_EPOCH_FRAMES == 16 && !LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY && \\
    !LEO_PRESENCE_ENERGY_SYMBOL_SUPPORT
        if(k==2 && w->acquisition_first_frame==0 && candidate->glrt_complete){
            /* The final scorer used this epoch, acquired CFO, and the same rows. */
            score[0]=candidate->candidate.exact_score;
            score[1]=candidate->candidate.control_score;
        } else
#endif
"""


def overlay(source):
    if source.count(_ORIGINAL) != 1:
        raise ValueError("the frozen five-cell GLRT source binding changed")
    return source.replace(_ORIGINAL, _REUSE + _ORIGINAL)
