"""Seal a one-scan radix histogram experiment from exact Wave6."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_wave6_combined'
SOURCE=ROOT/'sources'
if SOURCE.exists():raise SystemExit('Refusing to overwrite source snapshot')
shutil.copytree(BASE/'sources',SOURCE)
p=SOURCE/'proposal_core.c';s=p.read_text()
start=s.index('static ranked *rank_radix(')
end=s.index('\nstatic int descending(',start)
original=s[start:end].replace('rank_radix(', 'rank_radix_reference(',1)
original=original.replace('static ranked *rank_radix_reference','static __attribute__((unused)) ranked *rank_radix_reference',1)
s=s[:start]+original+'\n'+(ROOT/'rank_histograms.h').read_text()+s[end:]
p.write_text(s)
shutil.copy2(ROOT/'test_rank_histograms.c',SOURCE)
s=(BASE/'build.py').read_text()
s=s.replace("('test_dwell_input.c','test_dwell_input')", "('test_rank_histograms.c','test_rank_histograms'),('test_dwell_input.c','test_dwell_input')")
s=s.replace('fused_wave6_combined_', 'fused_wave7_rank_histograms_')
s=s.replace('arm-wave6-combined-build/v1','arm-wave7-rank-histograms-build/v1')
s=s.replace('exact stable 11/11/10-bit radix rank', 'exact stable 11/11/10-bit radix rank with all histograms in one input scan')
(ROOT/'build.py').write_text(s)
