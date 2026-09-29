"""Second sealed rank variant: canonicalize zero using integer bits only."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'sources-v2'
if SOURCE.exists():raise SystemExit('Refusing to overwrite snapshot')
shutil.copytree(ROOT/'sources',SOURCE)
p=SOURCE/'proposal_core.c';s=p.read_text()
old='''static uint32_t score_key(float value) {
    uint32_t bits; if(value==0) value=0;
    memcpy(&bits,&value,sizeof(bits));
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}'''
new='''static uint32_t score_key(float value) {
    uint32_t bits;memcpy(&bits,&value,sizeof(bits));
    if((bits&0x7fffffffu)==0)bits=0;
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}
static uint32_t score_key_reference(float value) {
    uint32_t bits; if(value==0) value=0;
    memcpy(&bits,&value,sizeof(bits));
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}'''
assert s.count(old)==1;s=s.replace(old,new)
start=s.index('static __attribute__((unused)) ranked *rank_radix_reference(')
end=s.index('/* A permutation',start)
s=s[:start]+s[start:end].replace('score_key(', 'score_key_reference(')+s[end:]
p.write_text(s)
s=(ROOT/'build.py').read_text().replace("SOURCE=ROOT/'sources'", "SOURCE=ROOT/'sources-v2'").replace("ROOT/'builds'", "ROOT/'builds-v2'")
s=s.replace('arm-wave7-rank-histograms-build/v1','arm-wave7-rank-histograms-build/v2').replace('histograms in one input scan','histograms in one input scan and integer-only key canonicalization')
s=s.replace("ROOT/'build-manifest.json'", "ROOT/'build-manifest-v2.json'")
(ROOT/'build_v2.py').write_text(s)
