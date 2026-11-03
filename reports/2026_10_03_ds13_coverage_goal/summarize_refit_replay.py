"""Compare fresh post-refit decoding against the original identical-fold replay."""
import csv,json
import numpy as np
from benchmark import ROOT,digest
import summarize_heldout_decoders as summary


def changes(before,after):
    left={(r['row_index'],r['catalog_number']):r['residual_native_hz'] for r in before}
    right={(r['row_index'],r['catalog_number']):r['residual_native_hz'] for r in after}
    common=left.keys()&right.keys();rms=lambda a:float(np.sqrt(np.mean(np.square(a)))) if a else None
    return dict(unchanged_peak_identity=len(common),added_peak_identity=len(right.keys()-left.keys()),
        removed_peak_identity=len(left.keys()-right.keys()),matched_before_rms_hz=rms([left[k] for k in common]),
        matched_after_rms_hz=rms([right[k] for k in common]))


def main():
    namespace=ROOT/'refit-replay';oldroot=summary.ROOT
    try:summary.ROOT=namespace;summary.main()
    finally:summary.ROOT=oldroot
    rows=[];sources={}
    for scan in ('A','B'):
        before=[];after=[]
        for fold in range(5):
            op=ROOT/'heldout-decoding'/f'fold-{fold}'/f'{scan}.json';npth=namespace/'heldout-decoding'/f'fold-{fold}'/f'{scan}.json'
            b=json.loads(op.read_text());a=json.loads(npth.read_text())
            assert b['original_test_rows']==a['original_test_rows']
            before.append(b);after.append(a);sources.update({str(p):digest(p) for p in (op,npth)})
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:denominator=len(a['canonical_rows'])
        for arm in ('fitted-c','zero-c'):
            for method in ('activity','history','tracklet'):
                old=[r for a in before for r in a['arms'][arm]['methods'][method]['assignments']]
                new=[r for a in after for r in a['arms'][arm]['methods'][method]['assignments']]
                rows.append(dict(scan=scan,arm=arm,method=method,denominator=denominator,before=len(old),after=len(new),
                    change=len(new)-len(old),before_fraction=len(old)/denominator,after_fraction=len(new)/denominator,**changes(old,new)))
    with (namespace/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (namespace/'comparison.json').write_text(json.dumps(dict(rows=rows,sources=sources,
        warning='Fresh coherent held-out decoding after training-only refit, not identity-certified or false-positive-controlled coverage. No new full-bank discovery after calibration changes. Shared tracklet candidate selection and calibration convergence caveats remain.'),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
