"""Reuse the verified carrier search on a separate saved scan context."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'new-three-segments-20261016/search.py'
spec=importlib.util.spec_from_file_location('previous_carrier_search',SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT=ROOT
offset_fit=module.offset_fit
observations=module.observations
ALIAS_HZ=module.ALIAS_HZ

if __name__=='__main__':module.main()
