"""Render an immutable repeated-recording load plan from a qualified overlap."""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

from render_arm_chain import render


def prepare(base, remote, count, detector_sha, controller_sha):
    path=PurePosixPath(remote)
    if not remote.startswith('/mnt/glrtbench/') or '..' in path.parts or any(c.isspace() for c in remote):
        raise ValueError('invalid diagnostic directory')
    if type(count) is not int or not 2<=count<=4:
        raise ValueError('two to four repeated scans required')
    for sha in (detector_sha,controller_sha):
        if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('invalid executable digest')
    payloads=copy.deepcopy(base['payloads'])
    payloads.pop(base['jobs']['detector']['argv'][0])
    payloads.pop(base['jobs']['search']['argv'][0])
    detector=remote+'/detector';controller=remote+'/controller'
    payloads[detector]=detector_sha;payloads[controller]=controller_sha
    # The qualified chain must consume one prior observation/graph pair.
    old_obs=base['chain']['stages'][0]['argv'][1]
    position=base['chain']['stages'][-1]['argv']
    if position[1]!=old_obs:raise ValueError('chain observation inputs disagree')
    old_graph=position[2]
    payloads.pop(old_obs);payloads.pop(old_graph)
    files={};rows=[];scans=[]
    for i in range(count):
        root=remote+f'/scan-{i}'
        obs=root+'/observations.tsv';graph=root+'/graph.tsv'
        args=copy.deepcopy(base['jobs']['detector']['argv']);args[0]=detector
        for flag,value in [('--observations',obs),('--graph',graph)]:args[args.index(flag)+1]=value
        plan=copy.deepcopy(base['chain']);previous=plan['output_directory'];plan['output_directory']=root+'/results'
        for stage in plan['stages']:
            stage['argv']=[obs if a==old_obs else graph if a==old_graph else
                           a.replace(previous,plan['output_directory']) for a in stage['argv']]
        script=render(plan,payloads);name=f'scan-{i}/chain.sh';files[name]=script
        payloads[root+'/chain.sh']=hashlib.sha256(script.encode()).hexdigest()
        measure='/mnt/glrtbench/native-adaptive/current/measure-run'
        for kind,argv in [('detector',[measure,'420',*args]),('downstream',[measure,'420',root+'/chain.sh'])]:
            fields=[kind,str(i),root+'/'+kind,*argv]
            if any(any(c in value for c in '\t\r\n\0') for value in fields):raise ValueError('unsafe plan field')
            rows.append('\t'.join(fields))
        scans.append({'directory':root,'observations':obs,'graph':graph,'chain':plan})
    files['plan.tsv']='\n'.join(rows)+'\n'
    payloads[remote+'/plan.tsv']=hashlib.sha256(files['plan.tsv'].encode()).hexdigest()
    return files,{'scope':'Repeated 300-second recorded-IQ load test; independent scan products; no new RF or longer scientific history',
                  'period_ms':300000,'initialization_lead_ms':5000,'scans':scans,
                  'controller_argv':[controller,remote+'/plan.tsv','300000','5000'],
                  'payloads':payloads,'absolute_score_tolerance_hz':base['absolute_score_tolerance_hz']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('base',type=Path);p.add_argument('output',type=Path);p.add_argument('remote')
    p.add_argument('detector',type=Path);p.add_argument('controller',type=Path)
    p.add_argument('--scans',type=int,default=3);a=p.parse_args()
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    files,protocol=prepare(json.loads(a.base.read_text()),a.remote,a.scans,digest(a.detector),digest(a.controller))
    a.output.mkdir()
    for name,content in files.items():
        target=a.output/name;target.parent.mkdir(exist_ok=True)
        target.write_text(content)
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for name,source in [('detector',a.detector),('controller',a.controller)]:
        (a.output/name).write_bytes(source.read_bytes())


if __name__=='__main__':main()
