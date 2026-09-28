"""Combine qualified block rotations with the small differential-dot saving."""
import json
import shutil
import subprocess
from build import HERE,build,sha
root=HERE/'work/goal40b';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/goal40diff/src',root/'src')
n=root/'src/native_presence';base=HERE/'work/goal40a/src/native_presence/presence.c'
other=HERE/'work/goal40rot/src/native_presence/presence.c'
r=subprocess.run(['git','merge-file','-p',str(n/'presence.c'),str(base),str(other)],capture_output=True,text=True)
if r.returncode:raise RuntimeError(r.stdout)
(n/'presence.c').write_text(r.stdout)
(root/'composition.json').write_text(json.dumps({'base':'goal40diff','rotation':'goal40rot',
    'rotation_source_sha256':sha(other),'presence_sha256':sha(n/'presence.c')},indent=2)+'\n')
build('goal40b',root);build('goal40b',root,host=True,sanitize=True)
