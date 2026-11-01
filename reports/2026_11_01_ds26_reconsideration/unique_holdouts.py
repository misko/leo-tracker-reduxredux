"""Supplementary confidence audit: require five distinct held-block subsets.

The frozen rule allowed random draws with replacement across folds. This audit
does not change that recorded rule or choose settings from position error.
"""
import reconsider as r

def run():
    case='DS26-0034';n=53852;original=r.masks
    r.masks=lambda times,groups:original(times,groups,unique=True)
    z=r.read(r.INPUT/(case+'.json'));d=r.reconstruct(z);ledger=r.causal_records(case,z)
    nums,bank,_=r.bank_for(ledger,z['scan_receipt']['origin_utc_ns'])
    out=r.OUT/case/'unique_holdouts';out.mkdir(exist_ok=True)
    result=r.screen(d,z,n,nums,bank,out);r.write(out/'screen.json',result)
    print([(h['name'],h['predictive']) for h in result.get('proposals',[])])

if __name__=='__main__':run()
