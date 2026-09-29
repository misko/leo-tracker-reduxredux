#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_direct_ci16_prefix/sources';NEW=HERE/'sources'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
def function(text,name,next_name):return text[text.index(name):text.index(next_name,text.index(name))]
def main():
    base,new=files(BASE),files(NEW);changed=sorted(k for k in base.keys()|new.keys() if base.get(k)!=new.get(k))
    if changed!=['full_search.c','test_sparse_peak_scan.c']:raise ValueError(changed)
    left=(BASE/'full_search.c').read_text();right=(NEW/'full_search.c').read_text()
    stable='size_t leo_full_search_retain_peaks';after='static int full_frame_support'
    if function(left,stable,after)!=function(right,stable,after):raise ValueError('stable top8 retention changed')
    required=('static size_t collect_active_peaks','size_t capacity=11*(size_t)regional_count','collect_active_peaks(w,regional_epochs,regional_count,peaks)')
    if any(right.count(x)!=1 for x in required):raise ValueError('sparse extraction inventory differs')
    result={'schema':'arm-wave5-final-source-inventory/v1','base':str(BASE),'changed_paths':changed,
        'stable_top8_retention_sha256':hashlib.sha256(function(right,stable,after).encode()).hexdigest(),
        'base_hashes':base,'final_hashes':new,'allowed_change':'one active-region extraction helper, its allocation/call-site loop, and its owned test'}
    (HERE/'source-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
