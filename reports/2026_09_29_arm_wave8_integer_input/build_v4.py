"""Isolate blocked NEON conversion from scalar VFP prefix accumulation."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
s=(ROOT/'build_v2.py').read_text().replace("ROOT/'builds-v3'", "ROOT/'builds-v4'")
s=s.replace("shutil.copy2(ROOT/'neon_widen.h',out/'neon_widen.h')", "(out/'neon_widen.h').write_text(blocked_header)")
h=(ROOT/'neon_widen.h').read_text()
h=h.replace('for(;k+4<=count;k+=4){', 'for(;k+4<=count;){\n        size_t first=k,stop=k+256;if(stop>count)stop=count-(count-k)%4;\n        uint32_t block_energy[256];\n        for(;k<stop;k+=4){')
old='''        uint32_t words[4];vst1q_u32(words,energy);
        for(int j=0;j<4;++j){*sum+=(double)words[j]*(1.0/1073741824.0);d->prefix[rx][k+j+1]=*sum;}
    }'''
new='''        vst1q_u32(block_energy+k-first,energy);
        }
        for(size_t j=first;j<stop;++j){*sum+=(double)block_energy[j-first]*(1.0/1073741824.0);d->prefix[rx][j+1]=*sum;}
    }'''
assert h.count(old)==1;h=h.replace(old,new)
exec(compile(s,__file__,'exec'),{'__file__':__file__,'__name__':'__main__','blocked_header':h})
