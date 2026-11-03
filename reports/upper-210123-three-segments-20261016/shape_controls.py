"""Reuse the orbit-blind continuity and matched shape controls on this scan."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'upper-three-segments-20261016/shape_controls.py'
spec=importlib.util.spec_from_file_location('previous_shape_controls',SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT=ROOT
link_segments=module.link_segments
extend_continuity=module.extend_continuity

if __name__=='__main__':module.main()
