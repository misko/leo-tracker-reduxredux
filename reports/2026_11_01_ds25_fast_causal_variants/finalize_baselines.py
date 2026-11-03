"""Account for every requested acquisition before preparing numerical recovery inputs."""
from prepare import *
def main(partial=False):
    old=read(ROOT/'roster.json');execution=read(ROOT/'baseline-execution.json')
    if not partial:assert {r['case'] for r in execution}=={r['case'] for r in old['cases']}
    by={r['case']:r for r in execution};rows=[]
    for row in old['cases']:
        p=WORK/'cases'/row['case']/'receipt.json'
        e=read(p) if p.exists() else by.get(row['case'],dict(case=row['case'],state='pending'))
        rows.append(dict(row,state='ready' if e['state']=='complete' else e['state'],execution=e))
    write(ROOT/'baseline-roster.json',dict(cases=rows,original_roster_sha256=digest(ROOT/'roster.json'),no_GPS=True))
    print('Baseline accounting',len(rows),sum(r['state']=='ready' for r in rows),'ready')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--partial',action='store_true');main(p.parse_args().partial)
