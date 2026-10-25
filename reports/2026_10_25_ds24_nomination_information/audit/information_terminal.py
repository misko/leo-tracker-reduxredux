"""Saved-array joint Gaussian/ownership/rank audit. No propagation or fits."""
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
from scipy.linalg import solve_triangular

ROOT = Path(__file__).resolve().parents[1]
INFO = ROOT/'information'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def joint_information(j,u,w,prior):
    # Position-first full triangular factorization, independent of the
    # producer's nuisance-first projection and incremental-gain formula.
    matrix = np.vstack((np.column_stack((j,u))*np.sqrt(w[:,None]),
                        np.column_stack((np.zeros((len(prior),2)),np.diag(np.sqrt(prior))))))
    _, root = np.linalg.qr(matrix,mode='reduced')
    inverse = solve_triangular(root,np.eye(len(root)),lower=False)
    covariance = (inverse@inverse.T)[:2,:2]
    return np.linalg.inv(covariance)


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('90s saved-array audit cap')))
    signal.setitimer(signal.ITIMER_REAL,90.)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    result=read(INFO/'results.json'); protocol=read(INFO/'protocol.json')
    check('complete frozen run',result['status']=='complete')
    check('protocol binding',result['protocol_sha256']==sha(INFO/'protocol.json'))
    for path,digest in read(INFO/'scientific_seal.json')['files'].items():
        check('seal '+path,sha(path)==digest)
    parents={}; maximum_joint_relative=0.;maximum_gain_error=0.
    for parent in result['parents']:
        arrays=dict(np.load(parent['array_path']))
        parents[parent['case'],parent['arm']]=(parent,arrays)
        independent=joint_information(arrays['position_design'],arrays['nuisance_design'],arrays['weights'],arrays['prior'])
        rel=float(np.linalg.norm(independent-arrays['information'])/np.linalg.norm(independent))
        maximum_joint_relative=max(maximum_joint_relative,rel)
        check(parent['case']+parent['arm']+' independent parent full QR',rel<1e-8)
    contexts=0
    for row in result['rows']:
        for arm,record in row['arms'].items():
            if record['status']!='complete':continue
            contexts+=1;parent,old=parents[row['case'],arm];new=dict(np.load(record['array_path']))
            check(row['component']+arm+' whole source shape',len(new['j'])==row['points'])
            check(row['component']+arm+' CFO redaction',record['target_CFO_redaction_maximum_difference']==0.)
            radio_stop=len(parent['role_map']['hardware'])+len(parent['role_map']['receiver_smooth'])
            if not row['family_has_parent_likelihood']:
                check(row['component']+arm+' no dormant family doublecount',np.count_nonzero(new['h'][:,radio_stop:])==0)
                check(row['component']+arm+' phase/full3mode/constant prior',new['extra'].shape[1]==5)
            else:
                check(row['component']+arm+' existing family shares parent slots',new['extra'].shape[1]==1)
            q=new['extra'].shape[1]
            u=np.vstack((np.column_stack((old['nuisance_design'],np.zeros((len(old['weights']),q)))),
                         np.column_stack((new['h'],new['extra']))))
            j=np.vstack((old['position_design'],new['j']))
            w=np.r_[old['weights'],1/new['noise_variance']]
            prior=np.r_[old['prior'],np.ones(q)]
            independent=joint_information(j,u,w,prior)
            expected=old['information']+new['information_gain']
            rel=float(np.linalg.norm(independent-expected)/np.linalg.norm(independent))
            maximum_joint_relative=max(maximum_joint_relative,rel)
            check(row['component']+arm+' independent augmented full QR',rel<1e-8)
            direct=new['effective_j'].T@np.linalg.solve(new['conditional_covariance'],new['effective_j'])
            err=float(np.max(abs(direct-new['information_gain'])))
            maximum_gain_error=max(maximum_gain_error,err)
            check(row['component']+arm+' direct covariance gain',err<1e-9)
            variance=float(old['weak']@np.linalg.solve(independent,old['weak']))
            reduction=1-variance/parent['weak_variance_km2']
            check(row['component']+arm+' unchanged weak-axis reduction',abs(reduction-record['fractional_weak_variance_reduction'])<1e-8)
        if row['status']=='complete':
            check(row['component']+' conservative paired score',row['paired_ranking_score']==min(a['fractional_weak_variance_reduction'] for a in row['arms'].values()))
    winners=[]
    for case in protocol['cases']:
        pool=[r for r in result['rows'] if r['case']==case]
        rules={'count_rank':lambda r:(-r['points'],-r['span_s'],r['component']),
               'duration_rank':lambda r:(-r['span_s'],-r['points'],r['component']),
               'information_rank':lambda r:(-r['paired_ranking_score'],-r['points'],-r['span_s'],r['component'])}
        for field,key in rules.items():
            ranked=sorted([r for r in pool if field!='information_rank' or r['status']=='complete'],key=key)
            for rank,row in enumerate(ranked,1):check(row['component']+field,row[field]==rank)
            winners.append(dict(case=case,ranking=field,component=ranked[0]['component'],candidate_norad=ranked[0]['candidate_norad'],points=ranked[0]['points']))
    signal.setitimer(signal.ITIMER_REAL,0)
    output=dict(all_passed=True,checks=checks,contexts=contexts,owners=len(result['rows']),
                blocked_owners=[dict(case=r['case'],component=r['component'],candidate_norad=r['candidate_norad']) for r in result['rows'] if r['status']!='complete'],
                maximum_joint_relative_error=maximum_joint_relative,maximum_direct_gain_error=maximum_gain_error,
                winners=winners,seconds=time.monotonic()-began,source_sha256=sha(__file__),
                scientific_seal_sha256=sha(INFO/'scientific_seal.json'),protocol_sha256=sha(INFO/'protocol.json'),
                propagation_calls=0,fits=0,position_errors_read=False)
    (ROOT/'audit/information_terminal.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('checks','winners')}))


if __name__=='__main__':main()
