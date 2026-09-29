"""Make an isolated proposal arithmetic SIMD experiment from sealed Wave5 v2."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / '2026_09_29_arm_wave5_final'
source = ROOT / 'sources'
if source.exists():
    raise SystemExit('Refusing to replace an existing experiment snapshot')
shutil.copytree(BASE / 'sources-v2', source)
p = source / 'proposal_core.c'
s = p.read_text()
header = (ROOT / 'proposal_simd.h').read_text()
anchor = 'static void correlate(bank *b,float *score,int method)'
s = s.replace(anchor, header + '\n' + anchor)
old = 'for(size_t k=0;k<z;k++){float ar=b->freq[k][0],ai=b->freq[k][1],br=b->reference_fft[method][k][0],bi=b->reference_fft[method][k][1];b->product[k][0]=ar*br+ai*bi;b->product[k][1]=ai*br-ar*bi;}'
assert s.count(old) == 1
s = s.replace(old, 'proposal_product(b->freq,b->reference_fft[method],b->product,z);')
old = 'for(size_t k=0;k<z;k++)score[k]=method<3?rank_squared_magnitude(b->corr[k][0],b->corr[k][1],scale):b->corr[k][0]*scale;'
assert s.count(old) == 1
s = s.replace(old, 'proposal_scores(b->corr,score,z,scale,method);')
p.write_text(s)
shutil.copy2(ROOT / 'test_proposal_simd.c', source)
s = (BASE / 'build_v2.py').read_text().replace("SOURCE=ROOT/'sources-v2'", "SOURCE=ROOT/'sources'").replace("ROOT/'builds-v2'", "ROOT/'builds'")
s = s.replace("('test_direct_ci16_ingest.c','test_direct_ci16_ingest')", "('test_proposal_simd.c','test_proposal_simd'),('test_direct_ci16_ingest.c','test_direct_ci16_ingest')")
s = s.replace("'arm-wave5-final-build/v2'", "'arm-wave6-proposal-simd-build/v1'")
s = s.replace('prepared CI16 coarse input plus active-region peak extraction; null-result preflight fix', 'Wave5 final v2 plus lane-wise NEON proposal products and score magnitudes')
s = s.replace("ROOT/'build-manifest-v2.json'", "ROOT/'build-manifest.json'")
(ROOT / 'build.py').write_text(s)
