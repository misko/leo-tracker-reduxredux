"""Independent exact-rank optimization, using original unpadded FFTs."""
import json
import subprocess
from build import HERE, BASE, sha

def main():
    for target in ('host','arm'):
        out=HERE/'builds'/f'{target}-radix-v1'
        out.mkdir(parents=True,exist_ok=False)
        text=(BASE/'proposal_probe.c').read_text()
        text=text.replace('ranked *ranking;', 'ranked *ranking,*rank_scratch;')
        text=text.replace('b->ranking=malloc(n*sizeof(*b->ranking));','b->ranking=malloc(n*sizeof(*b->ranking));b->rank_scratch=malloc(n*sizeof(*b->rank_scratch));')
        text=text.replace('||!b->ranking)', '||!b->ranking||!b->rank_scratch)')
        text=text.replace('free(b->ranking);','free(b->ranking);free(b->rank_scratch);')
        start=text.index('static int ascending(');end=text.index('static int descending(',start)
        text=text[:start]+(HERE/'radix.h').read_text()+'\n'+text[end:]
        text=text.replace('qsort(ranking,n,sizeof(*ranking),ascending);','rank_radix(ranking,b->rank_scratch,n);')
        source=out/'proposal_probe.c';source.write_text(text)
        base=BASE/'builds'/f'{target}-v1'
        command=[s.replace(str(base),str(out)) for s in json.loads((base/'build.json').read_text())['command']]
        run=subprocess.run(command,check=True,capture_output=True,text=True)
        (out/'build.json').write_text(json.dumps({'command':command,'source_sha256':sha(source),'binary_sha256':sha(out/'proposal_probe'),'compiler_stderr':run.stderr,'base_source_sha256':sha(BASE/'proposal_probe.c')},indent=2)+'\n')

if __name__=='__main__':main()
