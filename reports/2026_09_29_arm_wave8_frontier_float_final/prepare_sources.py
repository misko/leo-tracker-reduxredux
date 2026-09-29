#!/usr/bin/env python3
"""Deterministically transplant the qualified float-final V2 block."""
from pathlib import Path
R=Path(__file__).resolve().parent
dst=R/'sources/full_search.c'; src=R.parent/'2026_09_29_arm_wave7_float_final/sources-v2/full_search.c'
text=dst.read_text(); donor=src.read_text()
begin=donor.index('typedef struct {\n    size_t template_count;'); end=donor.index('static int final_cached_glrt(',begin)
block=donor[begin:end]; anchor='static int final_cached_glrt('
assert 'float_final_workspace' not in text and text.count(anchor)==1
text=text.replace(anchor,block+anchor)
old='if(glrt(w,count,epoch,cfo,0,16,1,result))return -1;'; assert text.count(old)==1
dst.write_text(text.replace(old,'if(glrt_float_final(w,count,epoch,cfo,result))return -1;'))
probe=R/'sources/fused_probe.c'; p=probe.read_text(); old='final_scorer\\\":\\\"fp64'; assert p.count(old)==1
probe.write_text(p.replace(old,'final_scorer\\\":\\\"fp32'))
