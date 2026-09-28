"""Combine independently qualified ranking/acquisition/GLRT candidates."""
import json
import shutil
import subprocess
from build import HERE,build,sha

root=HERE/'work/goal40a';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/fineio/src',root/'src')
n=root/'src/native_presence'
for name in ['window_rank.c','blind_aligned_v5.c']:
    shutil.copyfile(HERE/'work/rankcombo/src/native_presence'/name,n/name)
base=HERE/'work/rankunroll/src/native_presence/presence.c'
other=HERE/'work/glrtv2/src/native_presence/presence.c'
result=subprocess.run(['git','merge-file','-p',str(n/'presence.c'),str(base),str(other)],capture_output=True,text=True)
if result.returncode:raise RuntimeError('three-way merge requires review:\n'+result.stdout)
(n/'presence.c').write_text(result.stdout)
(root/'composition.json').write_text(json.dumps({
    'base':'fineio','rank':'rankcombo','glrt':'glrtv2',
    'merged_presence_sha256':sha(n/'presence.c'),
    'glrt_base_sha256':sha(base),'glrt_candidate_sha256':sha(other),
},indent=2)+'\n')
build('goal40a',root);build('goal40a',root,host=True,sanitize=True)
