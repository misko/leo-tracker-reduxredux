"""Summarize all shuffled bootstrap trials; not full adaptive null validation."""
import json
from benchmark import ROOT,digest,PROTOCOL


def main():
    manifest=json.loads((ROOT/'validation-inputs/manifest.json').read_text());scans={};sources={}
    for scan in ('A','B'):
        outcomes=[]
        for replicate in range(PROTOCOL['negative_controls']['replicates']):
            path=ROOT/'control-coherent-bootstrap'/f'replicate-{replicate:02d}'/'fold-0'/f'{scan}-checked.json'
            d=json.loads(path.read_text())
            assert d['scan']==scan and d['control']==replicate and d['fold']==0
            assert d['source_sha256']==manifest['scans'][scan]['controls'][replicate]['sha256']
            outcomes.append(dict(replicate=replicate,proposals=len(d['proposals']),status=d['status'],receiver_has_support=d['receiver_has_support']))
            sources[str(path)]=digest(path)
        scans[scan]=dict(replicates=len(outcomes),abstentions=sum(r['status']=='abstain_no_coherent_seed' for r in outcomes),outcomes=outcomes)
    result=dict(scope=__doc__,scans=scans,sources=sources,
        limitations=['Training fold-0 initialization stage only, not twenty full adaptive searches or end-to-end nuisance refits.',
            'Separately, replicate 0 completed full adaptive search with real-data calibration fixed; zero proposals in both scans and both RF arms.',
            'Does not certify 90% coverage, satellite identities, or the complete false-positive-control requirement.'])
    (ROOT/'conditional-controls/bootstrap-summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({s:{k:v for k,v in d.items() if k!='outcomes'} for s,d in scans.items()},indent=2))


if __name__=='__main__':main()
