"""Isolate a radius-one proposal experiment from the exact rank-v2 source."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_wave7_rank_histograms'
if (ROOT/'sources').exists():raise SystemExit('Refusing to replace source snapshot')
shutil.copytree(BASE/'sources-v2',ROOT/'sources')
p=ROOT/'sources/fused_probe.c';s=p.read_text()
old='int first=centers[c]-2,last=centers[c]+2;'
assert s.count(old)==1;s=s.replace(old,'int first=centers[c]-1,last=centers[c]+1;');p.write_text(s)
s=(BASE/'build_v2.py').read_text().replace("SOURCE=ROOT/'sources-v2'", "SOURCE=ROOT/'sources'").replace("ROOT/'builds-v2'", "ROOT/'builds'")
s=s.replace('fused_wave7_rank_histograms_', 'fused_wave7_radius1_').replace('arm-wave7-rank-histograms-build/v2','arm-wave7-radius1-build/v1')
s=s.replace("ROOT/'build-manifest-v2.json'", "ROOT/'build-manifest.json'")
s=s.replace("'selection':'", "'proposal_radius':1,'selection':'Approximate radius1 plus ")
(ROOT/'build.py').write_text(s)
