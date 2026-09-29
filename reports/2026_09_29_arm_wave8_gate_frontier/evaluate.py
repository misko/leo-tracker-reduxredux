"""Use the sealed fused runner while declaring the actual radius-one geometry."""
import hashlib
import runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'2026_09_29_arm_fused_pipeline/evaluate.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='86b8a678ade31a8aaee0e402686937d54fc1bd9cba154e270a1cfc8ccfb75cd1'
source=runpy.run_path(str(SOURCE))['adapted_source']()
old="assert args.top == 4 and args.radius == 2, 'Fused default is top4/radius2'"
assert source.count(old)==1
source=source.replace(old,"assert args.top == 4 and args.radius == 1, 'This experiment is top4/radius1'")
if __name__=='__main__':
    exec(compile(source,str(SOURCE),'exec'),{'__name__':'__main__','__file__':str(Path(__file__).resolve())})
